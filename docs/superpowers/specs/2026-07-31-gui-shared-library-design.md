# Compartir sonidos desde la GUI — Diseño

**Fecha:** 2026-07-31
**Estado:** aprobado para planificar
**Extiende:** [`2026-07-30-gui-design.md`](2026-07-30-gui-design.md) §6 («Asignar un clip por
*drag & drop*») y la fila «Fuente de las celdas» de su tabla de decisiones (§2). Aquel diseño
ya contemplaba celdas locales y remotas mezcladas, pero nunca definió cómo se sube un sonido
nuevo ni cómo se asigna uno remoto ya existente desde la GUI — ambos caminos solo existían por
CLI (`soundboard sound add` / edición manual de `ui_layout.json`). Este documento cierra ese
hueco. No contradice ni reabre ninguna otra sección de `2026-07-30-gui-design.md`.

## 1. Objetivo

Que soltar un archivo de audio sobre una celda vacía lo comparta automáticamente con todos los
usuarios (se sube a Supabase, no solo a esta máquina), y que cualquier usuario pueda además
traer a una celda vacía un sonido que **otro** usuario ya subió, sin salir de la GUI ni tocar la
CLI.

### No objetivos (esta fase)

- Migrar celdas `LocalSource` que ya existen en instalaciones previas — solo aplica a drops
  nuevos a partir de este cambio.
- Editar/borrar sonidos, categorías o metadatos desde la GUI (nombre, tags, categoría) — sigue
  siendo territorio de la CLI (`soundboard sounds ...`).
- Buscar/filtrar en el navegador de biblioteca — lista simple, sin caja de búsqueda.
- Notificación en vivo (realtime/polling) cuando otro usuario sube un sonido mientras la GUI ya
  está abierta — el navegador de biblioteca recarga solo al abrirse.
- Verificar o desplegar las migraciones de Supabase (`supabase/migrations/`) al proyecto real —
  es un riesgo de despliegue documentado en §9, no una tarea de este plan.

## 2. Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Drop de archivo | Sube a Supabase y asigna `RemoteSource`, nunca `LocalSource` | El usuario pidió compartir automático: todo sonido nuevo soltado en la grilla queda disponible para el resto |
| Fallo de subida | Bloquea la asignación: `QMessageBox` con el error, la celda queda vacía | Decisión explícita del usuario — nunca debe quedar un clip "huérfano" sin compartir por un fallo silencioso |
| UX durante la subida | Estado `LOADING` del botón (deshabilitado, sin aceptar nuevos drops), subida en `QRunnable` sin bloquear la ventana | Mismo patrón ya usado para descargar un `RemoteSource` sin caché (`download_worker.py`) |
| Módulo de subida | `ui/upload_worker.py` nuevo, dedicado, en vez de generalizar `download_worker.py` | Sigue la convención ya usada en el proyecto (un worker por operación, archivos de una sola responsabilidad — mismo motivo por el que `clip_button.py` está separado de `grid.py`) |
| Acceso a la sesión en `MainWindow` | Nuevo parámetro `session: Session` en el constructor | `add_sound` necesita `owner_id`; hoy la `Session` se obtiene en `app.py` (login o `require_session`) y se descarta sin pasarla a la ventana |
| Traer un sonido de otro usuario | Navegador de biblioteca completo (diálogo con lista de todos los sonidos compartidos, nombre + dueño) | Elegido explícitamente sobre las alternativas de "asignar por ID a mano" o "dejarlo para después" — sin esto, subir un sonido no lo hace utilizable por nadie más desde la GUI |
| Carga de la lista de sonidos | Síncrona, al abrir el diálogo | Mismo patrón ya usado por `LoginDialog` (llamada de red bloqueante dentro de un diálogo modal); no introduce un patrón async nuevo para una carga puntual disparada por una acción explícita del usuario |
| Testeo del navegador de biblioteca desde `MainWindow` | Callable inyectable `pick_library_sound`, mismo patrón que `prompt_shortcut` | Permite testear la lógica de asignación sin abrir un diálogo Qt modal real |

## 3. Arquitectura

Extiende el diagrama de `2026-07-30-gui-design.md` §3. Dos caminos nuevos hacia una celda vacía:

```
Camino 1 — compartir un archivo local nuevo:

ClipButton.file_dropped(index, path)
        │
        ▼
MainWindow._assign_local_file(index, path)
        │  1. valida con audioio.load_mono_48k(path) (falla rápido si no es audio decodificable)
        │  2. button.set_state(LOADING)
        ▼
UploadWorker(QRunnable)  ──background thread──▶  sounds.add_sound(client, session, path, name=stem)
        │                                              (import_sound + storage_upload + insert)
        │ signals.finished(Sound) / signals.failed(str)
        ▼
MainWindow._on_upload_ready / _on_upload_failed  (hilo Qt)
        ├─ éxito → Cell(source=RemoteSource(id=sound.id)) → _set_cell() → guarda ui_layout.json
        └─ fallo → button.set_state(EMPTY) + QMessageBox con el error → celda sin asignar

Camino 2 — traer un sonido que ya subió otro usuario:

Menú contextual (celda vacía) → "Asignar desde biblioteca"
        │
        ▼
MainWindow._open_library_dialog(index)
        │  pick_library_sound(self, client)  (por defecto abre ui/library_dialog.py)
        │    └─ LibraryDialog carga sounds.list_sounds(client) + auth.display_names(...)
        │       lista "{name} — {owner}", usuario elige una fila y confirma
        ▼
        (selected_id, selected_name) o None (canceló)
        │
        ▼
        Cell(source=RemoteSource(id=selected_id)) → _set_cell() → guarda ui_layout.json
```

Misma regla de dependencias ya vigente en `2026-07-30-gui-design.md` §3: solo `ui/` importa
PySide6; `sounds.add_sound` / `sounds.list_sounds` / `auth.display_names` ya viven en `remote/`
y no cambian.

## 4. Componentes

| Módulo | Cambio |
|---|---|
| `ui/upload_worker.py` (nuevo) | `UploadWorker(QRunnable)`: envuelve `Callable[[], Sound]`, señales `finished(object)` / `failed(str)` — copia estructural de `download_worker.py` |
| `ui/library_dialog.py` (nuevo) | `LibraryDialog(QDialog)`: carga y lista sonidos compartidos, expone `selected_id` / `selected_name` tras aceptar |
| `ui/grid.py` | Nueva señal `assign_from_library_requested(index)`; `_show_context_menu` añade la opción "Asignar desde biblioteca" solo cuando la celda está vacía |
| `ui/main_window.py` | `__init__` recibe `session: Session` y `pick_library_sound` (nuevo, opcional); `_assign_local_file` reescrito para subir en vez de asignar local directo; nuevos métodos `_on_upload_ready`, `_on_upload_failed`, `_open_library_dialog`; nuevo set `self._active_uploads` (mismo motivo que `_active_downloads`: mantener vivo el worker/sus señales durante el salto de hilo) |
| `ui/app.py` | Captura la `Session` que hoy se descarta en ambas ramas (`LoginDialog.session` / retorno de `auth.require_session`) y la pasa a `MainWindow(...)` |
| `tests/unit/test_main_window.py` | Los ~11 sitios que instancian `MainWindow(...)` pasan `session` (vía `client.sign_in_as_new_user(...)` de `FakeRemoteClient`, patrón ya usado en el test de celda remota existente) |

## 5. Flujo de datos — casos

- **Drop válido, subida OK:** botón pasa a `LOADING` (deshabilitado, sin aceptar nuevos drops —
  ya es el comportamiento de `ClipButton.dragEnterEvent`), sube en background, al terminar pasa
  a `IDLE` con `RemoteSource`, se persiste `ui_layout.json`.
- **Drop de archivo no decodificable:** igual que hoy — `QMessageBox`, celda queda `EMPTY`. No
  llega a intentar subir.
- **Subida falla** (sin red, sesión expirada, error del bucket/RLS): `QMessageBox` con el
  mensaje de la excepción, celda vuelve a `EMPTY`. El usuario puede reintentar soltando de
  nuevo.
- **Contenido duplicado** (mismo `sha256` que un sonido que el mismo usuario ya subió):
  `add_sound` ya es idempotente — reutiliza la fila existente, no falla ni duplica.
- **Asignar desde biblioteca, celda vacía:** diálogo lista los sonidos, usuario elige uno,
  celda queda `RemoteSource` de inmediato (sin descarga — el PCM se resuelve recién al
  reproducir, igual que cualquier `RemoteSource`).
- **Asignar desde biblioteca, celda ya ocupada:** la acción ni siquiera aparece en el menú
  contextual; si de todos modos se invoca el manejador, no hace nada (guard simétrico al que ya
  usa `_assign_shortcut` con celda vacía).
- **Carga de la biblioteca falla** (sin red, sesión expirada): el diálogo oculta la lista,
  muestra el error inline y un botón "Reintentar" — no se cierra solo, el usuario decide
  reintentar o cancelar.

## 6. Manejo de errores

Mismo principio que el resto del diseño de la GUI: ningún fallo en silencio.

| Situación | Comportamiento |
|---|---|
| Subida falla (red, sesión, RLS) | Excepción capturada dentro de `UploadWorker.run()` (igual que ya hace `DownloadWorker`), emitida como string por `failed`; `QMessageBox` en el hilo Qt, celda vuelve a `EMPTY` |
| Carga de biblioteca falla al abrir el diálogo | Error inline en el propio diálogo + botón "Reintentar", mismo patrón visual que el error de `LoginDialog` |
| Cancelar el diálogo de biblioteca | `pick_library_sound` devuelve `None`, `_open_library_dialog` no toca la celda ni el layout |

## 7. Contrato de datos

Sin cambios en `ui_layout.json` (`2026-07-30-gui-design.md` §5) — un sonido traído del
navegador de biblioteca es un `RemoteSource(id=...)` idéntico en forma al que ya se podía
escribir a mano. No se agregan campos nuevos.

## 8. Estrategia de pruebas

- `tests/unit/test_upload_worker.py` (nuevo, mismo patrón que el test existente de
  `download_worker`): `run()` con callable que devuelve `Sound` → `finished`; callable que
  lanza → `failed(str(exc))`.
- `tests/unit/test_library_dialog.py` (nuevo, `pytest-qt`): la lista se puebla con nombre+dueño
  desde `FakeRemoteClient` con 2+ usuarios; seleccionar una fila y aceptar expone
  `selected_id`/`selected_name` correctos; una falla de carga (cliente que lanza en `select`)
  muestra el error y "Reintentar" vuelve a intentar la carga.
- `tests/unit/test_main_window.py`:
  - Actualizar las ~11 instanciaciones existentes para pasar `session`.
  - Reescribir `test_dropping_a_file_assigns_the_cell_and_persists_the_layout`: ahora debe
    esperar `RemoteSource` (con `qtbot.waitUntil` para el resultado async del worker), no
    `LocalSource`.
  - Nuevo test: drop sobre celda vacía con `FakeRemoteClient` + sesión válida → celda termina
    `IDLE` con `RemoteSource`; `client.select("sounds", ...)` confirma la fila insertada con el
    `owner_id` correcto.
  - Nuevo test: `FakeRemoteClient` que falla en `storage_upload` → celda vuelve a `EMPTY`, se
    llama `message_box` con el error, `ui_layout.json` no gana esa celda.
  - Nuevo test: inyectando `pick_library_sound=lambda *_: ("sound-id", "nombre")`, invocar la
    asignación desde biblioteca sobre celda vacía la deja como `RemoteSource`; sobre celda ya
    ocupada no hace nada.

## 9. Riesgos

- **Migraciones sin confirmar en el proyecto Supabase real.** Ningún workflow de CI
  (`ci.yml`, `release-build.yml`) hace `supabase db push` contra el proyecto de producción — CI
  solo prueba contra una instancia local (`supabase start` + Docker). Si la migración
  `20260729000000_sounds_library.sql` no está aplicada al proyecto real, toda subida y toda
  carga de biblioteca fallarán con un error de Postgres/Storage. El error se verá (nunca en
  silencio, por §6), pero conviene verificarlo aparte antes de considerar esta función lista
  para usuarios reales. Fuera de alcance de este plan por decisión explícita del usuario.

## 10. Dependencias

Ninguna nueva. `PySide6` y `pytest-qt` ya son dependencias del proyecto desde
`2026-07-30-gui-design.md` §13.
