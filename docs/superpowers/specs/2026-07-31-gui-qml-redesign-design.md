# Rediseño de la GUI en Qt Quick — Diseño

**Fecha:** 2026-07-31
**Estado:** aprobado para planificar
**Supersede:** las secciones de arquitectura de UI (§3, §4, §9), flujo (§6) y la parte de
widgets de la estrategia de pruebas (§11) de
[`2026-07-30-gui-design.md`](2026-07-30-gui-design.md). Las decisiones de producto de
aquel diseño (layout local por máquina, formato de `ui_layout.json`, drag & drop sobre
celdas vacías, bandeja, atajos globales con `pynput`, CLI intacta) siguen vigentes; lo
que cambia es la capa de presentación y la instrumentación del motor que la alimenta.

## 1. Objetivo

Reemplazar la UI actual de QWidgets (botones planos sin estilo, `str(metrics)` en la
barra de estado) por una interfaz Qt Quick de aspecto profesional, estilo «dark studio»
(Elgato Stream Deck / OBS), con mejoras de UX que la UI actual no puede expresar:

- **Header** con usuario logueado, dispositivos activos, acceso a ajustes en caliente y
  botón «Detener todo» prominente.
- **Feedback de reproducción por celda**: la celda se resalta mientras su clip suena,
  con barra de progreso; estado de carga con spinner.
- **VU meter** del mix en tiempo real, reemplazando el volcado crudo de métricas.
- **Color por celda**, asignable desde el menú contextual y persistido en el layout.

### No objetivos (esta fase)

- Ventana *frameless* con barra de título propia — frame estándar del OS.
- Reordenar celdas, editor de forma de onda, *trim* visual, *ducking* desde UI — siguen
  fuera, igual que en el diseño anterior.
- Cambios de esquema en Supabase — el color de celda es local (`ui_layout.json`), no de
  la cuenta.
- Captura de atajos por tecla presionada — se mantiene la entrada de texto en formato
  pynput, con mejor presentación.
- Tema claro o temas intercambiables — un solo tema oscuro.

## 2. Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Toolkit | Qt Quick (QML) para toda la UI, incluidos login/dispositivos/biblioteca | Máximo pulido visual y animaciones; un solo stack coherente en vez de mezclar QWidgets y QML |
| Reparto de responsabilidades | QML = vista tonta; toda decisión en Python (`QObject`/`QAbstractListModel`) | Preserva la testabilidad headless actual: los modelos se prueban sin renderizar |
| Diálogos | Vistas apiladas (`StackView`) y popups QML dentro de la única ventana | Más moderno que diálogos flotantes; login y setup de dispositivos son estados de la ventana, no ventanas aparte |
| Identidad de voz en el motor | `AudioEngine.play()` devuelve `voice_id` monotónico | Sin identidad no hay feedback por celda; el id se asigna en el hilo llamante, nunca en el callback |
| Nivel de señal | `Mixer` guarda el pico del bloque mezclado en un atributo | Reducción numpy por bloque, coste trivial, cero I/O — compatible con la restricción del callback |
| Lectura de estado desde UI | `QTimer` a ~30 Hz en `engine_bridge.py` lee snapshot de voces y pico | Mismo patrón del `QTimer` de métricas actual; el GIL basta para lecturas consistentes a nivel de UI |
| Color de celda | Campo `color` (hex) opcional en `Cell`; `.get("color")` al deserializar | Layouts existentes cargan sin migración |
| Errores no fatales | Toasts no bloqueantes en QML | Los `QMessageBox` modales interrumpen; el principio «ningún fallo en silencio» se mantiene con el toast |
| Errores fatales de arranque | Diálogo nativo (`QMessageBox`) antes de cargar QML | Si la configuración o el engine QML fallan, no hay escena donde pintar un toast |
| Workers | `download_worker.py` / `upload_worker.py` se reutilizan tal cual | `QRunnable` + señales funciona igual con QML; no hay motivo para tocarlos |
| Bandeja | `tray.py` (`QSystemTrayIcon`) se queda | Compatible con apps QML; sin lógica propia que migrar |

## 3. Arquitectura

```
soundboard gui  (cli.py, import perezoso — sin cambios)
        │
        ▼
  ui/app.py        QApplication + QQmlApplicationEngine; resuelve sesión y layout;
        │          registra los tipos Python; carga qml/Main.qml
        ▼
  qml/Main.qml     ApplicationWindow + StackView:
        ├─ LoginView.qml         si no hay sesión válida (remote/auth vía AppController)
        ├─ DeviceSetupView.qml   primera vez o si el engine no arranca (loop de reintento)
        └─ BoardView.qml
             ├─ HeaderBar.qml    usuario, mic/out, ajustes, Detener todo
             ├─ GridView ── ClipPad.qml (delegate)   ◄── GridModel (Python)
             └─ Footer: VUMeter.qml + estado del engine  ◄── EngineBridge (Python)

  Python (ui/):
    controller.py     AppController: login/logout, arranque y reinicio del engine,
                      navegación entre vistas, toasts
    grid_model.py     GridModel(QAbstractListModel): roles name/shortcut/color/state/
                      progress; slots play/assignLocal/assignRemote/clear/setShortcut/
                      setColor; dueño de layout_store y HotkeyManager
    engine_bridge.py  QTimer ~30 Hz: mixer.last_peak y voice_states() → propiedades
                      con señales; mapea voice_id → índice de celda
```

Regla de dependencia intacta: nada bajo `audio/` importa `ui/` ni `hotkeys.py`; `ui/`
sigue siendo el único importador de PySide6.

Mueren: `main_window.py`, `grid.py`, `clip_button.py`, `login_dialog.py`,
`device_dialog.py`, `library_dialog.py`.

## 4. Componentes

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `ui/app.py` | Entry point: sesión, layout, engine QML, tipos registrados, arranque | `remote.auth`, `ui.controller`, `ui.layout_store` |
| `ui/controller.py` | `AppController`: estado de sesión, login, reinicio del engine con nuevos dispositivos, señal de toast | `remote.auth`, `audio.engine`, `ui.layout_store` |
| `ui/grid_model.py` | `GridModel`: celdas como modelo de lista, toda la lógica de asignar/reproducir/atajos/color; workers de descarga/subida | `audio.engine`, `remote.sounds`, `library.cache`, `hotkeys` |
| `ui/engine_bridge.py` | Poll de pico y voces activas, progreso por celda | `audio.engine` |
| `ui/library_model.py` | Modelo de lista de la biblioteca remota con filtro por nombre | `remote.sounds` |
| `ui/qml/Theme.qml` | Singleton de tokens: colores, radios, espaciado, tipografía | — |
| `ui/qml/*.qml` | Vistas y componentes; sin lógica de negocio | modelos Python |

## 5. Tema visual («dark studio»)

Tokens en `Theme.qml` (singleton QML):

- Fondo ventana `#141518`, superficies `#1d1f24`, celdas vacías `#22252b`.
- Acento `#7c5cff` (violeta): botón activo, foco, progreso, glow de reproducción.
- Texto primario `#e8eaed`, secundario `#9aa0a6`.
- Radios 8 px en pads, 6 px en controles; espaciado base 8 px.
- `ClipPad`: nombre + atajo en badge; color de celda como banda superior y tinte del
  fondo; barra de progreso inferior mientras suena; `SequentialAnimation` sutil de glow
  al reproducir; spinner (`BusyIndicator`) en LOADING.
- VU meter horizontal con gradiente verde→ámbar→rojo y *peak hold* breve.

## 6. Cambios en `audio/`

- `Voice` gana `voice_id: int` (asignado por el llamante) y expone `progress` (posición
  actual / duración, 0..1) como propiedad de solo lectura sobre estado que ya mantiene.
- `AudioEngine.play()` devuelve el `voice_id` (contador en el hilo llamante).
- `Mixer.voice_states() -> list[tuple[int, float]]` — pares `(voice_id, progress)` de
  las voces activas, iterando una copia superficial de la lista interna.
- `Mixer.process()` guarda `last_peak: float` del bloque mezclado
  (`float(np.abs(mix).max())`).
- `EngineMetrics` no cambia.

Todo son asignaciones de atributo o reducciones numpy dentro del callback — sin
allocations no triviales, sin locks, sin I/O. Los lectores (hilo UI) toleran ver un
bloque de retraso.

## 7. Formato de datos

`ui_layout.json` — único cambio, campo opcional en cada celda:

```json
{"index": 0, "source": {"type": "local", "path": "clips/airhorn.wav"},
 "name": "airhorn", "shortcut": "ctrl+alt+1", "color": "#e8590c"}
```

`color` ausente o `null` = celda sin color (estilo neutro del tema). Layouts escritos
por versiones anteriores cargan sin migración.

## 8. Flujo

**Arranque.** `app.py` resuelve sesión y layout igual que hoy (mismo manejo de sesión
expirada → login). Con QML, login y setup de dispositivos son vistas del `StackView`,
no diálogos: cancelar el login cierra la app; completar el setup crea el engine con el
mismo loop de reintento actual (fallo → volver a DeviceSetupView con el error visible).

**Ajustes en caliente.** El botón de ajustes del header empuja DeviceSetupView sobre el
board; al aceptar, `AppController` detiene el engine, lo reconstruye con los nuevos
dispositivos/rejilla y vuelve al board. Si el nuevo engine no arranca, se queda en la
vista de setup con el error — nunca una app sin audio en silencio.

**Reproducir.** Click o atajo → `GridModel.play(index)` → `engine.play(pcm)` devuelve
`voice_id`; el modelo lo asocia a la celda. `EngineBridge` publica progreso por celda a
~30 Hz; cuando la voz desaparece de `voice_states()`, la celda vuelve a IDLE. Remotos
sin caché: LOADING + worker, igual que hoy.

**Errores no fatales** (descarga/subida fallida, atajo inválido, drop no soportado):
toast + la celda vuelve a su estado anterior. **Fatales** (config corrupta, QML no
carga): diálogo nativo y salida con código ≠ 0.

## 9. Estrategia de pruebas

- **Modelos headless (patrón actual):** `GridModel`, `AppController`, `EngineBridge` y
  `library_model` se prueban sin renderizar QML, con `FakeRemoteClient`,
  `FakeHotkeyManager`, `FakeBackend` y un engine fake. Reemplazan `test_main_window.py`,
  `test_grid.py`, `test_clip_button.py`, `test_login_dialog.py`, `test_device_dialog.py`
  y `test_library_dialog.py`.
- **Smoke QML:** un test carga `Main.qml` en `QQmlApplicationEngine` offscreen con
  modelos fake registrados y falla ante cualquier error/warning de QML (sintaxis,
  bindings rotos, imports que faltan).
- **`audio/`:** `play()` devuelve ids crecientes; `voice_states()` refleja progreso y
  desaparición al terminar; `last_peak` correcto ante señal conocida — todo sobre
  `FakeBackend`.
- **`layout_store`:** round-trip con y sin `color`; carga de JSON antiguo sin el campo.
- **Manual antes de release:** checklist del diseño anterior + cambiar dispositivos en
  caliente, color de celda persistido tras reinicio, VU respondiendo al mic.

El patrón de callables inyectables (`message_box`, `prompt_shortcut`,
`pick_library_sound`) desaparece: sus decisiones ahora son slots/señales de modelos,
testeables directamente.

## 10. Packaging

- Los specs de PyInstaller (`packaging/`) añaden `ui/qml/**` como datos y dejan pasar
  los plugins QtQuick/QML de PySide6 (los hooks estándar de PyInstaller los recogen; si
  los specs excluyen módulos Qt explícitamente, se amplía la lista).
- `test_packaging_*_spec.py` se actualizan para exigir la presencia de los QML y de los
  plugins QtQuick en el bundle.

## 11. Limitaciones conocidas

- El progreso por celda se actualiza a ~30 Hz y puede retrasarse un bloque respecto al
  audio — imperceptible a `blocksize=256`.
- Si el mismo clip se dispara dos veces en paralelo, la celda muestra el progreso de la
  voz más reciente.
- `tray.py` sigue sin cobertura automatizada (límite ya documentado).
- Wayland/macOS: mismas limitaciones de atajos globales que antes; sin cambios.

## 12. Dependencias

Ninguna nueva: Qt Quick viene con PySide6. `pytest-qt` (dev) se mantiene para el smoke
QML y los modelos que necesiten un `QCoreApplication`.
