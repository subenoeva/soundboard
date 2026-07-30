# Ejecutables standalone + release automática — diseño

**Fecha:** 2026-07-30
**Estado:** aprobado, pendiente de plan de implementación

## Motivación

El soundboard ya funciona end-to-end (motor de audio, CLI, biblioteca Supabase,
GUI PySide6) y está integrado contra un proyecto Supabase real
(`soundboard-prod`). Para que amigos no técnicos (Windows y Linux — Arch entre
otras distros) puedan correr la app sin instalar Python, `uv` ni clonar el
repo, hace falta:

1. Ejecutables standalone para Windows y Linux, publicados como assets en
   GitHub Releases públicas.
2. Que esas releases se generen solas cuando hay trabajo mergeado a `master`,
   sin bump manual de versión.
3. Que el ejecutable venga configurado para hablar contra el proyecto
   Supabase compartido, sin que cada amigo tenga que setear variables de
   entorno.

## Arquitectura

```
push a master (conventional commits: feat/fix/docs/chore)
        │
        ▼
release-please.yml ──► abre/actualiza un "Release PR" (changelog + bump semver)
        │
        │ (merge manual del Release PR cuando se quiere cortar una release)
        ▼
   crea tag + GitHub Release (evento "release: published")
        │
        ▼
release-build.yml ──► matrix [windows-latest, ubuntu-latest]
        │                 build con PyInstaller
        │                 sube el binario como asset a esa Release
        ▼
   Release pública:
     soundboard-vX.Y.Z-windows.exe
     soundboard-vX.Y.Z-linux-x86_64.AppImage
```

Dos workflows nuevos en `.github/workflows/`, el `ci.yml` existente (tests,
lint, mypy) no cambia.

### 1. Versionado y changelog — `release-please`

- `googleapis/release-please-action@v4`, disparado en push a `master`.
- Lee los commits con formato Conventional Commits que el repo ya usa
  (`feat:`, `fix:`, `docs:`, `chore:`, etc.) para decidir el bump semver y
  generar el changelog.
- El release/tag real **no** se crea en cada push — se crea cuando se
  mergea el "Release PR" que la action mantiene abierto. Esto agrupa varios
  commits en una sola release con changelog prolijo, en vez de generar una
  release por cada commit de `docs:`/`chore:`.
- Config: `release-please-config.json` + `.release-please-manifest.json` en
  la raíz, tipo de release `simple` (no hay paquete a publicar en un
  registry, solo versionar `pyproject.toml`).

### 2. Build y publicación — `release-build.yml`

Disparado por el evento `release: published` (lo dispara release-please al
crear la Release). Matrix `[windows-latest, ubuntu-latest]`.

**Herramienta de empaquetado: PyInstaller.** Es la opción más probada para
PySide6 + `sounddevice` + `pynput` + `keyring`, con hooks mantenidos en
`pyinstaller-hooks-contrib` (se instala junto con PyInstaller). Se descarta
Nuitka (build más lento y frágil con Qt dinámico) y briefcase (pensado para
Toga/Kivy, no es el camino natural para PySide6).

Se agrega un dependency-group nuevo en `pyproject.toml`:

```toml
[dependency-groups]
packaging = ["pyinstaller>=6.0"]
```

separado de `dev` para que el job de tests (`ci.yml`) no lo instale.

**Windows:**
- `pyinstaller --onefile --windowed` → un solo `.exe`, sin ventana de
  consola (para que doble clic no abra una terminal).
- El DLL de PortAudio va embebido solo — el wheel de `sounddevice` para
  Windows ya lo trae en `_sounddevice_data`.
- Riesgo conocido: `keyring` descubre sus backends (Windows Credential
  Locker) vía entry-points, que PyInstaller puede no resolver sin
  hidden-imports explícitos (`keyring.backends.Windows`). Se resuelve en el
  plan de implementación con `--hidden-import` o `--collect-submodules
  keyring.backends` en el `.spec`.

**Linux:**
- `pyinstaller --onedir` (no `--onefile`: un AppImage ya es "un solo
  archivo" a nivel usuario, y `--onedir` hace el empaquetado a AppImage más
  simple y el arranque más rápido).
- Se arma un AppDir mínimo a mano (`AppRun` + `.desktop` + ícono genérico) y
  se empaqueta con `appimagetool` → un solo `.AppImage` que corre en
  cualquier distro (Arch incluido) sin pedir instalar dependencias.
- Hay que copiar `libportaudio.so.2` a mano dentro del AppDir: el wheel de
  Linux de `sounddevice` no lo trae (por eso `ci.yml` lo instala vía
  `apt install libportaudio2` para poder correr los tests) — bundleado una
  vez, corre bien porque solo depende de ALSA (`libasound.so.2`), presente
  en prácticamente cualquier distro Linux con audio.
- Mismo riesgo de `keyring` que en Windows, pero para el backend
  `SecretService` (`keyring.backends.SecretService`, requiere
  `secretstorage`/`jeepney`, ya son dependencias transitivas de `keyring`).

Cada job sube su artefacto a la Release ya creada (`gh release upload` o
`softprops/action-gh-release`), nombrado `soundboard-vX.Y.Z-<plataforma>`.

### 3. Config Supabase horneada en el build

- Secrets del repo (GitHub): `SOUNDBOARD_SUPABASE_URL`,
  `SOUNDBOARD_SUPABASE_ANON_KEY` (la publishable key actual del proyecto
  `soundboard-prod`).
- Antes de invocar PyInstaller, un paso del workflow genera
  `src/soundboard/_baked_defaults.py` (añadido a `.gitignore`, nunca se
  commitea) con esas dos constantes, tomadas de los secrets vía variables de
  entorno del job.
- `resolve_config()` (`src/soundboard/remote/client.py`) gana un tercer nivel
  de fallback, en este orden: **variables de entorno → `settings.json` →
  `_baked_defaults` (import opcional; si el módulo no existe, se comporta
  exactamente igual que hoy)**.
- Esto no cambia nada para desarrollo local ni para los tests (el módulo
  simplemente no existe en el working tree ni en CI de `ci.yml`), y hace que
  el binario horneado arranque sin que cada amigo tenga que setear nada —
  comparten la misma biblioteca de sonidos.
- La publishable key es pública por diseño (la protección real es RLS), así
  que no hay riesgo de seguridad en hornearla en un binario público.

### 4. Cambio de código necesario: default a `gui` sin argumentos

`cli.py` usa `add_subparsers(dest="command", required=True)` — si el
ejecutable se abre con doble clic (sin argv), argparse falla con "the
following arguments are required: command" y, al ser `--windowed`, el
usuario no ve ni el error (la ventana no llega a abrir). Fix: en
`main()`/`__main__.py`, si no se pasó ningún argumento, inyectar
`["gui"]` como default antes de parsear. La CLI real (`run`, `auth`,
`sounds`, etc.) sigue funcionando igual cuando se invoca con argumentos
explícitos, tanto en el ejecutable empaquetado como en `uv run soundboard`.

### 5. Documentación (README)

Sección nueva "Descargar ejecutable" con el link a la página de Releases, y
las limitaciones que ya aplican al proyecto y se heredan al binario:

- **Windows**: sigue haciendo falta instalar VB-CABLE aparte a mano (no se
  puede empaquetar un driver de kernel firmado). El `.exe` no está firmado
  digitalmente — Windows SmartScreen puede mostrar aviso de "editor
  desconocido"; se resuelve con "más información → ejecutar de todas
  formas". No se compra certificado de firma de código para este proyecto.
- **Linux**: sigue haciendo falta configurar un null-sink de
  PipeWire/PulseAudio a mano. Atajos globales no funcionan bajo Wayland (ya
  documentado). Si no hay `gnome-keyring` o `kwalletd` corriendo, `keyring`
  puede fallar al guardar la sesión — anotarlo como prerequisito.

## Fuera de alcance (YAGNI)

- Firma de código / notarización.
- Auto-actualización del binario.
- Ícono de app custom (se usa uno genérico; cambiarlo es trivial después,
  no bloquea nada de este diseño).
- Empaquetado para macOS (nadie del grupo lo pidió).
- Publicar en AUR / winget / Flatpak — GitHub Releases alcanza para
  distribución entre amigos.

## Testing / verificación

No se agregan tests automatizados de "el binario arranca" (correr un
`.exe`/AppImage real no es algo que la suite de `pytest` pueda hacer de forma
útil en CI). La verificación es manual: al cerrar el plan de implementación,
bajar el artefacto generado por el workflow y correrlo en un Windows y un
Linux reales (o al menos uno de los dos) antes de considerar la feature
terminada.
