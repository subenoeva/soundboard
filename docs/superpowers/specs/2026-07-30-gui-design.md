# Interfaz gráfica del soundboard — Diseño

**Fecha:** 2026-07-30
**Estado:** aprobado para planificar
**Supersede:** las secciones 6 («Interfaz») y 7 («Atajos globales»), y la parte de UI de
la sección 9 («Estrategia de pruebas»), de
[`2026-07-29-soundboard-design.md`](2026-07-29-soundboard-design.md). Aquel diseño
asumía biblioteca SQLite local con pestañas de categoría, editor de forma de onda,
asistente de primer arranque y perfiles — la biblioteca ya fue reemplazada por
[`2026-07-29-supabase-sounds-design.md`](2026-07-29-supabase-sounds-design.md). Este
documento cubre solo el alcance actual del roadmap: ventana, rejilla de clips, arrastrar
y soltar, bandeja del sistema, atajos globales. El resto de la visión original (editor de
forma de onda, categorías como pestañas visuales, *ducking* configurable desde UI,
asistente de enrutado) queda para las fases futuras ya listadas en el roadmap
(«Enrutado automático», «Efectos»).

## 1. Objetivo

Dar una superficie gráfica al soundboard: una ventana con una rejilla de botones que
dispara los mismos clips que hoy se disparan por `soundboard run` desde stdin, pero con
click, arrastrar-y-soltar y atajos de teclado (in-app y globales, incluso sin foco), más
una bandeja del sistema para minimizar sin perder el motor de audio activo.

### No objetivos (esta fase)

- Reordenar celdas de la rejilla entre sí — solo asignar un clip soltando un archivo
  sobre una celda vacía.
- Rejilla de tamaño dinámico — fijo, definido una vez en `device_dialog`, editable desde
  ajustes.
- Editor de forma de onda, *trim* visual, control de *ducking* desde la UI.
- Asistente de primer arranque / detección o creación del dispositivo virtual — es la
  fase «Enrutado automático» del roadmap, separada.
- Sincronizar el layout de la rejilla entre máquinas vía Supabase — es local a la
  máquina, igual que hoy no hay sincronización de qué `--sound KEY=PATH` usa cada quien.
- Empaquetado (PyInstaller/AppImage) — sigue siendo una fase posterior sin cambios.
- Reemplazar la CLI. `soundboard run`, `auth`, `sounds`, `categories` siguen existiendo
  tal cual, para scripting y verificación sin ventana.

## 2. Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Relación con la CLI | Conviven. Nuevo subcomando `soundboard gui` | Consistente con cómo se verificó cada fase anterior; no descarta el modo headless |
| Comunicación GUI↔motor | El hilo Qt llama directo a `AudioEngine.play()`/`stop_all()` | Ya son *thread-safe* (`deque.append`, documentado en `engine.py`); una capa de hilos/señales extra no aportaría nada |
| Sesión Supabase | Carga la sesión del keyring si existe; si no, diálogo de login inline | El `SessionStore` ya es compartido con la CLI; no obliga a abrir una terminal para usar la app |
| Bandeja y atajos globales | `QSystemTrayIcon` (nativo Qt) + `pynput` | Pure-Python, sin admin en Windows ni root en X11 normal; ya elegido en el diseño original (§7) |
| Fuente de las celdas | Local (ad-hoc, como `--sound KEY=PATH`) y biblioteca remota mezcladas | Misma resolución que ya hace `cli._resolve_sound_pcm`; no fuerza a subir todo a Supabase para tener una rejilla útil |
| Arrastrar y soltar | Soltar un archivo del explorador sobre una celda vacía la asigna | Cubre el caso de uso principal sin la complejidad de *drag* interno entre celdas |
| Persistencia del layout | JSON local en `platformdirs`, no en Supabase | El layout es de la máquina, no de la cuenta — dos PCs del mismo usuario pueden diferir |
| Tamaño de rejilla | Fijo, configurable una vez en `device_dialog` | Evita estado adicional de redimensionado; se ajusta desde ajustes si hace falta |
| Atajos por celda | Configurables, asignados por celda (no fijos por posición) | Misma flexibilidad que el `--sound KEY=PATH` de hoy |
| Descarga de sonido remoto sin caché | Asíncrona (`QRunnable`), celda muestra spinner | Nunca bloquea la ventana ni compite con el callback de audio |
| Nombre de paquete/módulo | `soundboard/ui/` + `soundboard/hotkeys.py` (top-level) | Sigue la tabla de componentes y la regla de dependencia ya escritas en el diseño original (§4.2), no un nombre nuevo |

## 3. Arquitectura

```
soundboard gui   (subcomando nuevo en cli.py, import perezoso de soundboard.ui.app)
        │
        ▼
  ui/app.py   crea QApplication, carga sesión (keyring) y ui_layout.json
        │
        ├─ sin sesión válida ──► ui/login_dialog.py   (reusa remote/auth + SessionStore)
        ├─ sin devices/rejilla guardados ──► ui/device_dialog.py (backend.list_devices())
        │
        ▼
  ui/main_window.py (QMainWindow)
        ├─ ui/grid.py          rejilla NxM de ClipButton: click, drag&drop, menú contextual
        ├─ ui/tray.py          QSystemTrayIcon: mostrar/ocultar/salir
        ├─ hotkeys.py          HotkeyManager sobre pynput, hilo propio → Qt Signal (queued)
        └─ QTimer               sondea engine.metrics para la barra de estado
                │
                ▼
         AudioEngine (misma instancia que usaría cli._run; play()/stop_all()
         llamados directo desde el hilo Qt — ya son thread-safe)

  Clip remoto sin caché ──► ui/download_worker.py (QRunnable, llama sounds.resolve_pcm
                             en background) ──► señal con PCM listo ──► engine.play(pcm)
```

Regla de dependencia (extiende la del diseño original, §4.2): `ui/` y `hotkeys.py` pueden
importar `audio/`, `remote/` y `library/` — igual que ya hace `cli.py` — pero nada bajo
`audio/` importa `ui/` ni `hotkeys.py`. `ui/` es la única capa que importa PySide6;
`hotkeys.py` es la única que importa `pynput`.

## 4. Componentes

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `ui/app.py` | Entry point: `QApplication`, orquesta login/device dialogs, arranca `main_window` | `remote.auth`, `ui.layout_store` |
| `ui/main_window.py` | `QMainWindow`: conecta grid+tray+hotkeys con `AudioEngine`, barra de estado con métricas | `audio.engine`, `ui.grid`, `ui.tray`, `hotkeys` |
| `ui/grid.py` | `ClipGrid`: rejilla de `ClipButton`, click, drag&drop, menú contextual (asignar atajo, quitar clip) | `ui.clip_button`, `ui.download_worker` |
| `ui/clip_button.py` | `ClipButton` (`QToolButton`): estados idle/loading/playing, nombre y atajo pintados | — |
| `ui/login_dialog.py` | Diálogo de email/password | `remote.auth` |
| `ui/device_dialog.py` | Combos de mic/out (`backend.list_devices()`) + filas/columnas de la rejilla | `audio.portaudio` |
| `hotkeys.py` | `HotkeyManager`: protocolo + implementación `pynput` + `FakeHotkeyManager` para tests, emite Qt Signal por combinación registrada | `pynput` |
| `ui/tray.py` | `QSystemTrayIcon`: mostrar/ocultar/salir | — |
| `ui/download_worker.py` | `QRunnable` que llama `sounds.resolve_pcm` en background, señal con PCM o error | `remote.sounds`, `library.cache` |
| `ui/layout_store.py` | Carga/guarda `ui_layout.json` | `platformdirs` |

Cada archivo se mantiene bajo el límite de ~300 líneas del proyecto; `clip_button.py`
está separado de `grid.py` precisamente para que este último no crezca por acumular
tanto el layout de la rejilla como el estado visual de cada celda.

## 5. Formato de datos: `ui_layout.json`

```json
{
  "rows": 4,
  "cols": 6,
  "mic": "substring del micrófono",
  "out": "substring del cable virtual",
  "blocksize": 256,
  "cells": [
    {"index": 0, "source": {"type": "local", "path": "clips/airhorn.wav"}, "name": "airhorn", "shortcut": "ctrl+alt+1"},
    {"index": 1, "source": {"type": "remote", "id": "<uuid>"}, "name": "applause", "shortcut": null}
  ]
}
```

Para `source.type == "remote"`, ganancia/*trim*/bucle viven en la fila `sounds` de
Supabase — ya resueltos por `sounds.resolve_pcm` — la celda no los duplica. Para
`source.type == "local"`, se comporta igual que hoy `--sound KEY=PATH`: se carga con
`audioio.load_mono_48k` sin ganancia/*trim*/bucle propios.

Se guarda en `<config>/soundboard/ui_layout.json` (`platformdirs.user_config_dir`),
separado de `settings.json` (credenciales Supabase) porque tiene un ciclo de vida
distinto: uno es por máquina, el otro por instalación de la app.

## 6. Flujo de datos

**Arranque.** `ui/app.py` intenta cargar la sesión del `SessionStore` (keyring,
compartido con la CLI). Si no hay sesión válida, `login_dialog` bloquea antes de mostrar
nada más — cancelar cierra la aplicación. Después intenta cargar `ui_layout.json`; si no
existe, `device_dialog` pide mic/out/filas/columnas antes de construir la rejilla.

**Reproducir un clip.** Click en una celda o atajo (in-app vía `QShortcut`, global vía
`hotkeys.HotkeyManager`) dispara la reproducción. Si la celda es local, se resuelve el
PCM ya en memoria (cacheado tras la primera carga) y se llama `engine.play(pcm)`
directo. Si es remota y no hay caché en disco, la celda pasa a estado *loading*, el
`download_worker` descarga en background, y al terminar emite una señal que dispara
`engine.play(pcm)` desde el hilo principal — el motor de audio nunca ve el hilo de
descarga.

**Asignar un clip por *drag & drop*.** Soltar un archivo de audio soportado sobre una
celda vacía la asigna como fuente local, se guarda en `ui_layout.json`. Formatos no
soportados o celdas ocupadas se rechazan con `QMessageBox`, no en silencio.

**Asignar un atajo.** Menú contextual de la celda → capturar combinación → `hotkeys`
intenta registrarla; si el sistema operativo o `pynput` la rechazan (ya usada por otra
app), la celda se guarda sin atajo y la barra de estado avisa.

**Bandeja del sistema.** Cerrar la ventana la oculta (no termina el proceso ni detiene
`AudioEngine`); el ícono de bandeja permite mostrarla de nuevo o salir de verdad
(entonces sí se llama `engine.stop()`).

## 7. Superficie CLI

```
soundboard gui
```

Sin flags: la primera vez pide mic/out/rejilla por `device_dialog`; las siguientes reusa
`ui_layout.json`. Un ítem de menú "Ajustes" dentro de la ventana reabre ese mismo
diálogo para cambiar dispositivos o el tamaño de la rejilla.

El subcomando importa `soundboard.ui.app` de forma perezosa (dentro de la función que
maneja `args.command == "gui"`), para que `import PySide6` no ocurra en usos puramente
headless de la CLI (`devices`, `run`, `auth`, `sounds`, `categories`).

## 8. Configuración

Reusa `SOUNDBOARD_SUPABASE_URL` / `SOUNDBOARD_SUPABASE_ANON_KEY` y el `SessionStore`
existentes — no hay configuración nueva de Supabase para la GUI. Lo único nuevo es
`ui_layout.json`, descrito en §5.

## 9. Estructura de ficheros

```
src/soundboard/
├── hotkeys.py            protocolo HotkeyManager + impl. pynput + FakeHotkeyManager
├── ui/
│   ├── app.py
│   ├── main_window.py
│   ├── grid.py
│   ├── clip_button.py
│   ├── login_dialog.py
│   ├── device_dialog.py
│   ├── tray.py
│   ├── download_worker.py
│   └── layout_store.py
└── cli.py                 + subcomando gui
```

## 10. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Sesión inválida/expirada al abrir | `login_dialog` bloqueante; cancelar cierra la app |
| Login falla (credenciales, red) | `QMessageBox` con el error de `remote.auth`; el diálogo se mantiene abierto |
| Dispositivo mic/out guardado ya no existe | El motor falla al iniciar → se reabre `device_dialog` con el nombre que faltó |
| Motor no arranca (error de PortAudio) | `QMessageBox` con el error; la ventana queda abierta, celdas deshabilitadas hasta reintentar |
| Descarga de sonido remoto falla (sin red, 404, sesión expirada) | La celda vuelve a idle, el error se muestra en la barra de estado — nunca en silencio |
| *Drop* de archivo no soportado o celda ocupada | `QMessageBox` de error, la celda no se modifica |
| Atajo choca con el SO u otra aplicación | `pynput` rechaza el registro; la celda queda sin atajo pero sigue funcionando por click, aviso en la barra de estado |
| Wayland (`XDG_SESSION_TYPE=wayland`) | Los atajos globales no funcionan por diseño del protocolo (igual que documenta el diseño original, §7); se avisa una vez al arrancar, bandeja y atajos in-app siguen andando |

Principio heredado del diseño original: ningún fallo se traga en silencio.

## 11. Estrategia de pruebas

- **`pytest-qt`** (nueva dependencia de desarrollo), con `QT_QPA_PLATFORM=offscreen`:
  clicks en celdas, simulación de *drag & drop*, transiciones de estado de
  `ClipButton` (idle → loading → playing → idle).
- **`hotkeys.py` detrás de un protocolo**, mismo patrón que `AudioBackend`/`FakeBackend`:
  `HotkeyManager` real usa `pynput.keyboard.GlobalHotKeys`; `FakeHotkeyManager` invoca el
  callback registrado directamente, sin depender de hooks del sistema operativo. La
  lógica de mapeo combinación→celda se prueba contra el fake.
- **`ui/layout_store.py`**: pruebas unitarias puras de serialización/deserialización de
  `ui_layout.json`, sin Qt.
- **`ui/login_dialog.py` / `ui/device_dialog.py`**: `pytest-qt` simulando entrada en los
  campos, con `remote.auth` y `backend.list_devices` mockeados.
- **`ui/tray.py`**: sin pruebas automatizadas más allá de humo manual — es un wrapper
  delgado sobre `QSystemTrayIcon` sin lógica propia; se documenta como límite conocido,
  mismo criterio que ya usa el proyecto para otras superficies difíciles de automatizar.
- **Manual**, checklist antes de release: login, asignar clip local, asignar clip
  remoto (con y sin caché previa), *drag & drop* de un archivo no soportado, atajo global
  disparando con la ventana sin foco, minimizar y restaurar desde la bandeja.

## 12. Limitaciones conocidas

- Atajos globales no funcionan en Wayland ni en macOS (macOS ya es no-soportado en v1);
  documentado, no resuelto en esta fase (§7 del diseño original ya lo anticipaba).
- El layout de la rejilla es local a la máquina; no viaja entre instalaciones del mismo
  usuario.
- Reordenar celdas entre sí no está soportado; para reorganizar hay que vaciar y volver a
  asignar.
- `ui/tray.py` sin cobertura automatizada (§11).

## 13. Dependencias nuevas

| Paquete | Uso |
|---|---|
| `PySide6` | Ventana, widgets, bandeja del sistema (`QSystemTrayIcon`) |
| `pynput` | Atajos de teclado globales (`HotkeyManager`) |
| `pytest-qt` (dev) | Pruebas de widgets con `QT_QPA_PLATFORM=offscreen` |

Ya elegidas en el diseño original (§3, tabla de decisiones, y §7); esta fase solo las
fija como dependencias reales del proyecto en vez de decisiones sobre papel.
