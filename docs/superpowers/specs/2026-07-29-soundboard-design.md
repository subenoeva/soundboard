# Soundboard multiplataforma — Diseño

**Fecha:** 2026-07-29
**Estado:** aprobado para planificar

## 1. Objetivo

Aplicación de escritorio en Python que reproduce clips de audio de forma que Discord
(u otra aplicación de voz) los reciba como si vinieran del micrófono, mezclados con la
voz real del usuario. Incluye un panel de gestión de la biblioteca de sonidos con
operaciones CRUD completas y soporte de los formatos de audio habituales.

La aplicación se comporta como **mezclador de micrófono**: captura el micrófono físico,
suma los sonidos disparados, y entrega el resultado a un dispositivo de salida virtual
que Discord tiene seleccionado como entrada. Esa arquitectura es también la que habilita
la futura sección de efectos sobre el micrófono.

### No objetivos (v1)

- macOS. El código se estructura para admitirlo (backend de enrutado intercambiable),
  pero no se prueba ni se empaqueta.
- Efectos de audio implementados. Solo se define la interfaz `Effect` y el punto de
  inserción en la cadena.
- Control remoto desde el móvil, integración con la API de Discord, texto a voz.

## 2. Restricción fundamental

Ningún proceso de usuario puede crear un dispositivo de captura virtual sin un driver de
kernel firmado. Python no puede hacerlo. Por tanto la aplicación **depende de un
dispositivo virtual externo** en Windows, y lo crea mediante el servidor de audio en Linux.

| Plataforma | Dispositivo virtual | Quién lo crea |
|---|---|---|
| Windows | VB-CABLE (gratuito) o VoiceMeeter | El usuario, una vez, con instalador externo |
| Linux | `module-null-sink` + `module-remap-source` | La aplicación, en tiempo de ejecución, vía `pactl` |
| macOS (futuro) | BlackHole | El usuario, una vez |

Consecuencia de diseño: si Discord escucha el cable virtual, deja de oír el micrófono
físico. La aplicación es responsable de capturar ese micrófono y mezclarlo. Esto no es
opcional, es el núcleo del producto.

## 3. Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Papel de la app | Mezclador de micrófono | Habilita efectos y *ducking*; evita configuración externa |
| Plataformas v1 | Windows + Linux | Linux valida que la abstracción sea real, no teórica |
| GUI | PySide6 / Qt 6.11 | Rejilla, arrastrar y soltar, bandeja y temas de fábrica |
| Motor de audio | Dos streams PortAudio + ring buffer + control de drift | Único enfoque predecible entre dispositivos con relojes distintos |
| Decodificación | Previa, al importar | El callback de audio nunca decodifica; evita cortes |
| Distribución | Desde fuente con `uv`; empaquetado como fase final | Iteración rápida sin el impuesto de PyInstaller en cada fase |
| Onboarding | Asistente con autodetección y prueba de lazo | Es el punto donde más usuarios abandonarían |
| Python | 3.13 | Todos los binarios del stack publican wheels abi3 o cp313 |

### Enfoques descartados

- **Stream dúplex único `sd.Stream(device=(in, out))`.** PortAudio hace internamente la
  misma conversión que el enfoque elegido, pero sin control ni instrumentación. Produce
  cortes esporádicos no diagnosticables.
- **Delegar la mezcla al servidor de audio.** Funciona muy bien en Linux con PipeWire,
  pero en Windows exigiría VoiceMeeter obligatorio y rompería la paridad. Queda apuntado
  como optimización opcional de Linux, no como base.

## 4. Arquitectura

```
            ┌──────────────┐         ┌────────────────────────────────┐
  micro ───►│ InputStream  │──────►  │      RingBuffer (SPSC)         │
  físico    └──────────────┘         └───────────────┬────────────────┘
                                                     │
                                     ┌───────────────▼────────────────┐
                                     │  DriftController               │
                                     │  (resample fraccional soxr)    │
                                     └───────────────┬────────────────┘
                                                     │  bus micro
                                     ┌───────────────▼────────────────┐
   biblioteca ──► VoicePool ────────►│  Mixer                         │
   (clips en                         │  suma · ducking · limitador    │
    caché f32)                       └──────┬──────────────────┬──────┘
                                            │                  │
                              ┌─────────────▼──────┐  ┌────────▼─────────┐
                              │ OutputStream cable │  │ OutputStream     │
                              │  → Discord         │  │ monitor local    │
                              └────────────────────┘  └──────────────────┘
```

### 4.1 Formato interno

- Frecuencia fija **48 000 Hz**, `float32`.
- Bus interno **mono**. Discord transmite mono de todos modos; los clips estéreo se
  mezclan a mono al importar. El monitor local duplica el canal a estéreo.
- Tamaño de bloque **256 frames** (5,33 ms), configurable a 512/1024 si aparecen *xruns*.
  Latencia PortAudio en modo `low`, no `lowest`.

### 4.2 Componentes

Cada componente tiene un propósito único, interfaz explícita y se puede probar aislado.

| Componente | Responsabilidad | Depende de |
|---|---|---|
| `audio.backend.AudioBackend` | Protocolo: abrir/cerrar streams, enumerar dispositivos | — |
| `audio.backend.PortAudioBackend` | Implementación real sobre `sounddevice` | sounddevice |
| `audio.backend.FakeBackend` | Implementación en memoria, reloj simulado, para tests | numpy |
| `audio.ringbuffer.RingBuffer` | Cola SPSC de `float32`, sin reservas de memoria en el camino caliente | numpy |
| `audio.drift.DriftController` | Mide ocupación del buffer, devuelve ratio de lectura | — |
| `audio.drift.DriftResampler` | Lee del ring buffer a tasa fraccionaria con interpolación lineal | numpy |
| `audio.voice.Voice` | Una reproducción en curso: posición, ganancia, bucle, *trim* | numpy |
| `audio.voice.StreamingVoice` | Igual, pero leyendo de disco con hilo lector propio | numpy |
| `audio.mixer.Mixer` | Suma voces + bus de micro, aplica *ducking* y limitador | Voice |
| `audio.effects.Effect` | Protocolo `process(block) -> block`, con estado reiniciable | — |
| `audio.effects.EffectChain` | Cadena ordenada aplicada al bus de micro | Effect |
| `audio.engine.AudioEngine` | Orquesta streams, cola de comandos, métricas, ciclo de vida | todos los anteriores |
| `routing.VirtualDeviceBackend` | Protocolo: detectar/crear/destruir dispositivo virtual | — |
| `routing.windows.WindowsRouting` | Detección de VB-CABLE / VoiceMeeter por nombre | — |
| `routing.linux.LinuxRouting` | Crea y destruye módulos vía `pactl` | subprocess |
| `library.db` | Esquema SQLite, migraciones versionadas | sqlite3 |
| `library.importer` | Decodifica, mezcla a mono, remuestrea, escribe caché | soundfile, av, soxr |
| `library.cache` | Caché LRU en RAM con presupuesto; ficheros `.f32` en disco | numpy |
| `hotkeys.HotkeyManager` | Registro y despacho de atajos globales | pynput |
| `ui.*` | Ventana, rejilla, editor, ajustes, asistente, bandeja | PySide6 |

Regla de dependencia: `ui` depende de `library` y `audio`; `audio` y `library` no conocen
`ui` y se comunican con ella mediante señales Qt emitidas desde una capa adaptadora.
Ningún módulo de `audio` importa PySide6.

### 4.3 Control de drift

Micrófono y cable virtual son dispositivos distintos con osciladores distintos. Una
desviación típica de 10–100 ppm produce una muestra sobrante o faltante cada pocos
segundos, que se manifiesta como chasquidos.

Algoritmo:

1. El callback de salida registra la ocupación del ring buffer en cada bloque.
2. Una media móvil exponencial (constante ~2 s) estima la ocupación real `fill`.
3. `ratio = 1 + k · (fill − target) / target`, con `k` pequeño y `ratio` limitado a ±0,5 %.
   `ratio` se define como frames de entrada consumidos por frame de salida producido.
4. El bus de micro se lee del ring buffer con **posición fraccionaria e interpolación
   lineal** (`DriftResampler`), avanzando `ratio` muestras por muestra de salida y
   conservando la fase entre bloques.

Objetivo de ocupación: 2 bloques. Capacidad: 16 bloques. Si el buffer se vacía se
inserta silencio y se cuenta un *underrun*; si se llena se descartan las muestras más
antiguas y se cuenta un *overrun*. Ambos contadores se exponen en la UI de diagnóstico.

**Por qué interpolación lineal y no `soxr` en tasa variable:** `python-soxr` no expone
`soxr_set_io_ratio`, así que la tasa variable no es accesible desde Python. Y para
desviaciones de ±0,5 % la interpolación lineal equivale a un retardo fraccionario de
menos de una muestra: su distorsión queda muy por debajo del ruido de fondo de cualquier
micrófono. `soxr` se sigue usando donde brilla — el remuestreo de tasa fija y alta
calidad en la importación. Cero dependencias nuevas y un algoritmo que cabe en una
prueba unitaria.

### 4.4 Seguridad en tiempo real

El callback de audio se ejecuta en un hilo de PortAudio y necesita adquirir el GIL. Reglas
obligatorias dentro del callback:

- Solo operaciones vectorizadas de numpy sobre arrays preasignados. Nada de reservas.
- Prohibido: E/S, `logging`, `queue.Queue`, decodificación, creación de objetos.
- El único bloqueo permitido es el `threading.Lock` interno del `RingBuffer`, que protege
  **solo la actualización de índices**, nunca la copia de datos. En CPython el GIL ya
  serializa el bytecode, así que perseguir la ausencia total de bloqueos no aporta nada
  real; una sección crítica de tres asignaciones es más honesta y más correcta que un
  esquema sin bloqueos que se rompe al descartar muestras antiguas en desbordamiento.
- Comunicación desde la UI mediante una `collections.deque` de comandos con objetos
  preasignados de un *pool*. El callback drena la deque con `popleft` hasta vaciarla.
- Las métricas se escriben en un array numpy compartido, no en estructuras Python.

**Riesgo aceptado:** el GIL puede provocar *xruns* si otro hilo hace trabajo pesado sin
soltarlo. Mitigación de primer nivel: bloques de 256–512 frames y trabajo vectorizado.
Mitigación de reserva, si resulta insuficiente: mover el motor a un proceso separado con
prioridad elevada, comunicado por memoria compartida. Se documenta pero no se construye
en la v1.

### 4.5 Ducking

Detector de envolvente sobre el bus de sonidos. Con voces activas, el bus de micrófono se
atenúa `N` dB con tiempos de ataque y liberación configurables (por defecto −12 dB,
ataque 10 ms, liberación 300 ms). Activable por sonido y globalmente.

### 4.6 Limitador de salida

Recorte suave `tanh` con umbral en −1 dBFS tras la suma, más ganancia de salida global.
Evita saturación cuando se disparan varios sonidos a la vez sin necesitar *look-ahead*.

## 5. Biblioteca y datos

### 5.1 Almacenamiento

Rutas vía `platformdirs`:

```
<config>/soundboard/settings.json        ajustes de la aplicación
<data>/soundboard/library.db             SQLite
<data>/soundboard/originals/<sha256>.<ext>   copia del fichero original
<cache>/soundboard/pcm/<sha256>.f32          PCM mono 48 kHz float32 crudo
```

Los originales **se copian** a la biblioteca en lugar de referenciarse en su sitio: evita
enlaces rotos cuando el usuario mueve o borra el fichero de origen. La deduplicación es
por SHA-256. Al borrar un sonido, el original y la caché se eliminan solo si ningún otro
registro los referencia.

### 5.2 Esquema

```sql
schema_version(version INTEGER)
profiles(id, name, created_at, is_active)
categories(id, profile_id, name, position, color)
sounds(
  id, profile_id, category_id, name, position,
  sha256, source_filename, cache_path,
  duration_frames, orig_samplerate, orig_channels,
  gain_db, trim_start_frames, trim_end_frames, loop,
  hotkey, color, tags, created_at
)
settings(key, value)   -- value en JSON
```

Migraciones versionadas y comprobadas al arrancar. Cada cambio de esquema añade un paso
de migración con prueba propia.

### 5.3 Importación

1. Calcular SHA-256. Si ya existe, reutilizar la caché y solo crear el registro.
2. Decodificar. Vía rápida: `soundfile` (libsndfile) para WAV, FLAC, OGG/Vorbis, Opus,
   MP3, AIFF, W64, CAF. Vía de reserva: `av` (PyAV, con FFmpeg incorporado en el wheel)
   para M4A/AAC, WMA, AMR y pistas de audio de ficheros de vídeo.
3. Mezclar a mono, remuestrear a 48 kHz con `soxr` en calidad alta.
4. Medir el pico y guardar en `gain_db` la ganancia que lo llevaría a −1 dBFS. El PCM se
   escribe **sin modificar**; la ganancia se aplica en reproducción y el usuario puede
   cambiarla en el editor. La normalización nunca es destructiva.
5. Escribir `<sha256>.f32` y el registro en SQLite.

La importación ocurre en un hilo trabajador con barra de progreso. Importar una carpeta
entera procesa en lote y reporta los fallos individualmente sin abortar el resto.

### 5.4 Reproducción y caché

Clips de menos de 60 s se cargan enteros en RAM mediante una caché LRU con presupuesto
configurable (512 MB por defecto). Clips más largos usan `StreamingVoice`, que lee del
fichero `.f32` en un hilo dedicado y alimenta su propio ring buffer. Al abrir un perfil se
precargan los clips visibles en segundo plano.

## 6. Interfaz

- **Ventana principal:** pestañas de categoría, rejilla de botones con color y nombre,
  barra de búsqueda incremental, botón de parada total, medidores de nivel de micro y
  salida, indicador de estado del enrutado.
- **CRUD:** añadir por arrastrar y soltar, por diálogo de ficheros o por carpeta completa;
  renombrar en línea; borrar con confirmación; reordenar arrastrando; duplicar; mover de
  categoría.
- **Editor de sonido:** forma de onda dibujada con QPainter sobre datos submuestreados,
  marcadores de inicio y fin, ganancia, bucle, color, atajo de teclado, categoría,
  activación de *ducking*. Previsualización solo en el monitor local.
- **Ajustes:** dispositivo de micro, dispositivo virtual, dispositivo de monitor, tamaño de
  bloque, ganancia de salida, parámetros de *ducking*, presupuesto de caché, perfiles.
- **Asistente de primer arranque:** detecta el dispositivo virtual; si falta, enlace de
  descarga con instrucciones por plataforma y botón de reintento; en Linux ofrece crear el
  dispositivo automáticamente; **prueba de lazo** que emite un tono en el cable, lo captura
  en la entrada emparejada y confirma que el enrutado funciona; instrucciones finales de
  configuración de Discord.
- **Bandeja del sistema:** mostrar/ocultar, silenciar, parada total, salir.
- **Diagnóstico:** contadores de *underrun*/*overrun*, ocupación del buffer, ratio de drift,
  carga del callback. Imprescindible para depurar informes de cortes.

Los dispositivos se persisten **por nombre**, no por índice: los índices de PortAudio
cambian al conectar o desconectar hardware. Si al arrancar el dispositivo guardado no
existe, se avisa y se abre el selector en lugar de fallar en silencio.

## 7. Atajos globales

`pynput` con `GlobalHotKeys`. Un atajo por sonido, más atajos globales de parada total y
silenciado.

**Limitación conocida:** en Linux con Wayland los atajos globales no funcionan por diseño
del protocolo. La aplicación detecta `XDG_SESSION_TYPE=wayland` y muestra un aviso claro
explicando la limitación y la alternativa (sesión X11). La ruta futura es el portal
`org.freedesktop.portal.GlobalShortcuts`, que se deja apuntada pero fuera de la v1.

En Windows los atajos no llegan a aplicaciones con privilegios elevados salvo que la
aplicación también los tenga. Se documenta, no se soluciona.

## 8. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Dispositivo virtual ausente | Asistente bloqueante, no arranque silencioso sin salida |
| Dispositivo guardado desaparecido | Aviso + selector, nunca fallo mudo |
| Dispositivo desconectado en caliente | Detener streams, avisar, reintentar al reaparecer |
| Formato no soportado tras ambas vías | Error por fichero, el lote continúa, se lista al final |
| Fichero de caché corrupto o ausente | Reimportar desde el original de forma transparente |
| Original perdido y caché válida | Seguir funcionando, marcar el sonido como huérfano |
| `pactl` ausente en Linux | Explicar que se requiere PulseAudio o PipeWire; sin *fallback* silencioso |
| *Underruns* persistentes | Aviso proactivo sugiriendo subir el tamaño de bloque |

Principio: ningún fallo se traga en silencio. Todo error de audio o de biblioteca se
registra y, si afecta a lo que el usuario oye, se muestra.

## 9. Estrategia de pruebas

- **Unitarias, sin hardware.** `RingBuffer` (llenado, vaciado, envolvente, concurrencia),
  `DriftController` (convergencia ante desviaciones sintéticas, saturación del ratio),
  `Mixer` (suma, *ducking*, limitador), `Voice` (*trim*, bucle, ganancia, fin), importador
  (ficheros sintéticos generados en cada formato), base de datos y migraciones.
- **Integración del motor con `FakeBackend`.** Reloj simulado, sin tarjeta de sonido: se
  ejecuta el motor completo miles de bloques y se verifica que la señal de salida contiene
  el micro y los clips esperados, que no hay *underruns* y que el drift converge. Esto es
  posible **solo** porque `sounddevice` está detrás del protocolo `AudioBackend`; es un
  requisito de diseño, no un detalle.
- **UI con `pytest-qt`.** Humo: abrir ventana, crear sonido, renombrar, borrar, buscar.
- **Manual, con lista de verificación.** Lazo real en Windows con VB-CABLE y en Linux con
  PipeWire, y prueba final en una llamada de Discord.

CI en GitHub Actions sobre Windows y Linux, ejecutando todo salvo las pruebas manuales.

## 10. Fases

Cada fase termina en algo verificable.

| Fase | Contenido | Hito verificable |
|---|---|---|
| 0 | `uv`, `pyproject`, ruff, mypy, pytest, CI, esqueleto de paquetes | `uv run pytest` en verde en Windows y Linux |
| 1 | Núcleo de audio: backend, ring buffer, drift, mixer, voces, CLI de prueba | Sin UI, en Discord se te oye a ti **y** un WAV disparado por consola |
| 2 | Biblioteca: SQLite, importador multiformato, caché, API CRUD | Importar una carpeta y disparar por identificador desde la CLI |
| 3 | UI base: rejilla, CRUD, arrastrar y soltar, parada total, monitor, volumen | Aplicación usable con ratón |
| 4 | Enrutado: detección, backend de Linux, asistente, prueba de lazo | Primer arranque limpio en una máquina sin configurar |
| 5 | Atajos globales y bandeja del sistema | Disparar sonidos con el juego en primer plano |
| 6 | Categorías, búsqueda, editor con forma de onda y *trim*, *ducking*, perfiles | Alcance completo acordado |
| 7 | Cadena de efectos: interfaz, UI de cadena, efectos iniciales | Ampliación posterior |
| 8 | Empaquetado: PyInstaller en Windows, AppImage en Linux | Binario distribuible |

## 11. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| *Xruns* por el GIL en el callback | Media | Alto | Trabajo vectorizado, bloque configurable; plan B: motor en proceso aparte |
| Control de drift inestable | Media | Alto | Reserva por duplicado/eliminación de muestra en cruce por cero; pruebas con drift sintético |
| Usuario no instala VB-CABLE | Alta | Alto | Asistente con detección, instrucciones y prueba de lazo |
| Atajos globales rotos en Wayland | Alta en Linux | Medio | Detección y aviso explícito; portal XDG como ruta futura |
| Formatos exóticos no soportados | Baja | Bajo | Doble vía soundfile + PyAV; error por fichero |
| Latencia percibida excesiva | Baja | Medio | 256 frames ≈ 15–20 ms extremo a extremo; ajustable |

## 12. Dependencias

Python 3.13. Todos los binarios publican wheels abi3 o cp313 para `win_amd64` y
`manylinux x86_64`, verificado el 2026-07-29.

| Paquete | Versión | Uso |
|---|---|---|
| sounddevice | 0.5.5 | Streams PortAudio |
| numpy | 2.5.1 | Búferes y DSP |
| soundfile | 0.14.0 | Decodificación vía rápida (libsndfile) |
| av | 18.0.0 | Decodificación de reserva (FFmpeg incorporado) |
| soxr | 1.1.0 | Remuestreo fijo y de tasa variable |
| PySide6 | 6.11.1 | Interfaz |
| pynput | 1.8.2 | Atajos globales |
| platformdirs | 4.11.0 | Rutas de configuración, datos y caché |

Desarrollo: pytest, pytest-qt, ruff, mypy.

Externas al ecosistema Python: VB-CABLE en Windows (instalación manual del usuario);
`pactl` con PulseAudio o PipeWire en Linux (presente por defecto en las distribuciones
habituales).

## 13. Estructura de ficheros

```
soundboard/
├── pyproject.toml
├── README.md
├── docs/superpowers/specs/
├── src/soundboard/
│   ├── __main__.py
│   ├── app.py
│   ├── audio/
│   │   ├── backend.py       AudioBackend, PortAudioBackend, FakeBackend
│   │   ├── ringbuffer.py
│   │   ├── drift.py
│   │   ├── voice.py
│   │   ├── mixer.py
│   │   ├── engine.py
│   │   └── effects/         base.py, chain.py
│   ├── library/
│   │   ├── db.py, migrations.py, models.py
│   │   ├── importer.py, cache.py, service.py
│   ├── routing/
│   │   ├── base.py, detect.py, windows.py, linux.py
│   ├── hotkeys/manager.py
│   ├── config/settings.py, paths.py
│   └── ui/
│       ├── main_window.py, board_view.py, sound_editor.py
│       ├── settings_dialog.py, setup_wizard.py, tray.py, bridge.py
└── tests/
    ├── unit/, integration/, ui/
```

Límite de tamaño por fichero: si un módulo supera aproximadamente 300 líneas, es señal de
que hace más de una cosa y hay que dividirlo.
