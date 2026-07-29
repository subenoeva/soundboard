# Biblioteca de sonidos con Supabase — Diseño

**Fecha:** 2026-07-29
**Estado:** aprobado para planificar
**Supersede:** la sección 5 («Biblioteca y datos») de
[`2026-07-29-soundboard-design.md`](2026-07-29-soundboard-design.md), que proponía
persistencia local en SQLite de un único perfil. Este documento la reemplaza para la
biblioteca de sonidos; el resto del diseño original (motor de audio, enrutado, atajos,
UI) no cambia.

## 1. Objetivo

Convertir la biblioteca de sonidos en multiusuario: cualquier usuario autenticado puede
añadir sonidos a una biblioteca compartida, verlos y reproducirlos todos, pero solo puede
editar o borrar los que subió él mismo. Persistencia y autenticación viven en Supabase
(Postgres + Auth + Storage); el disco local se usa solo como caché de reproducción, no
como origen de verdad.

### No objetivos (esta fase)

- Interfaz gráfica. Se sigue trabajando por CLI, igual que la fase 1 (núcleo de audio).
- Modo sin conexión. El login es obligatorio; sin sesión válida no hay acceso a la
  biblioteca. La reproducción de sonidos ya cacheados con `--sound <ruta-local>` (fase 1)
  sigue funcionando sin red, porque no toca `remote/`.
- Conservar el fichero original en Supabase Storage. Se sube el PCM ya preprocesado; ver
  §6.
- Limpieza de blobs huérfanos en Storage cuando el último `sounds` que los referencia se
  borra. Se documenta como limitación conocida (§11).
- Categorías o perfiles locales del diseño original (`profiles` local, `categories` por
  perfil). Quedan reemplazados por el modelo de esta fase.

## 2. Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Origen de verdad | Supabase (Postgres + Storage), no SQLite local | Multiusuario real, no solo multi-perfil en una máquina |
| Caché local | Sí, por SHA-256, descarga bajo demanda | Reproducción de baja latencia sin re-descargar en cada `play` |
| Autenticación | Email + contraseña (Supabase Auth) | Simple, sin dependencias OAuth externas |
| Visibilidad | Biblioteca compartida global | Todos ven todos los sonidos; RLS restringe solo escritura |
| Categorías | Tabla global compartida, edición restringida al creador | Navegación única de biblioteca; misma filosofía de ownership que `sounds` |
| Conectividad | Login obligatorio, sin modo degradado sin red | Un solo modo de operación, menos casos borde |
| Superficie de esta fase | Extensión de la CLI existente | Consistente con cómo se verificó la fase 1 |
| Qué se sube a Storage | PCM mono float32 48kHz ya preprocesado, no el original | Ningún cliente que descarga necesita decodificar; menos dependencias en el camino de lectura |
| Cliente Supabase | SDK oficial `supabase-py` | Envuelve Auth+PostgREST+Storage con una sesión; RLS se aplica vía el JWT automáticamente |
| Persistencia de sesión | `keyring` (almacén de credenciales del SO) | Evita guardar tokens en texto plano en disco |
| Test de RLS | Stack local de Supabase CLI (Docker) en tests de integración marcados `supabase` | Es el único modo de probar RLS de verdad y no un mock; crítico porque un bug de RLS permite editar sonidos ajenos |

## 3. Arquitectura

Paquete nuevo `remote/` es el único punto de I/O de red del proyecto. Reutiliza
`library/importer.py` (decodificación, mezcla a mono, remuestreo 48kHz, medición de gain)
sin cambios — sigue corriendo antes de tocar la red. `library/cache.py` pasa de
"copiar al importar" a "descargar bajo demanda, cachear por SHA-256". `audio/` no se
toca: sigue sin I/O, sin conocer Supabase ni la red.

```
                    ┌──────────────┐
   soundboard sounds add ─────────►│  importer    │  decodifica, mono, 48kHz, sha256
                    └──────┬───────┘
                           │ PCM f32 + metadata
                    ┌──────▼───────┐        ┌────────────────────┐
                    │  remote/     │───────►│ Supabase            │
                    │  sounds.py   │  HTTP  │ Postgres + Storage  │
                    │  categories.py│ (RLS via JWT)│ + Auth        │
                    └──────────────┘        └────────────────────┘

   soundboard run --sound <id> ──► remote/sounds.py resuelve fila
                                   │
                                   ▼ cache miss
                          library/cache.py descarga <sha256>.f32
                                   │ cache hit o recién descargado
                                   ▼
                            AudioEngine.play(pcm)   ← igual que fase 1, sin decodificar
```

Regla de dependencia (extiende la del diseño original): nada bajo `audio/` importa
`remote/` ni hace I/O de red. `remote/` no importa `audio/`. `cli.py` es quien conecta
`remote/`, `library/` y `audio/`.

## 4. Esquema de datos y RLS

```sql
profiles(
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  created_at timestamptz not null default now()
)

categories(
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  color text,
  position int not null default 0,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
)

sounds(
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  category_id uuid references categories(id) on delete set null,
  name text not null,
  sha256 text not null,
  storage_path text not null,
  source_filename text not null,
  duration_frames int not null,
  orig_samplerate int not null,
  orig_channels int not null,
  gain_db real not null default 0,
  trim_start_frames int not null default 0,
  trim_end_frames int,
  loop boolean not null default false,
  color text,
  tags text[],
  created_at timestamptz not null default now(),
  unique (owner_id, sha256)
)
```

`profiles.display_name` existe para no exponer emails en los listados compartidos (p.
ej. "subido por Pablo" en vez de "subido por pcostaoubina@gmail.com"). Se crea en el
primer `auth login` si no existe fila para ese usuario, pidiendo el nombre por prompt —
sin trigger de Postgres, para mantener la lógica en la capa de aplicación y poder
probarla con el fake client.

### RLS

| Tabla | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| `profiles` | todos los autenticados | `id = auth.uid()` | `id = auth.uid()` | — |
| `categories` | todos los autenticados | todos los autenticados, `with check (created_by = auth.uid())` | `created_by = auth.uid()` | `created_by = auth.uid()` |
| `sounds` | todos los autenticados | `with check (owner_id = auth.uid())` | `owner_id = auth.uid()` | `owner_id = auth.uid()` |

Bucket de Storage `sounds`: política SELECT e INSERT para autenticados; sin UPDATE ni
DELETE, porque el contenido es inmutable (direccionado por hash, ver §6).

## 5. Almacenamiento y deduplicación

Se sube a `sounds/<sha256>.f32` en Storage el PCM **ya preprocesado**: mono, float32,
48kHz — los mismos bytes que hoy vive en la caché local del diseño original. No se
decodifica en ningún otro punto del sistema salvo al importar. Trade-off aceptado: el
fichero original no se conserva remotamente; si en el futuro hace falta re-transcodificar
(p. ej. cambiar la tasa interna), habrá que re-importar desde el original local de cada
usuario. Documentado como no objetivo (§1), no como omisión accidental.

Deduplicación por contenido: la ruta en Storage es el hash, así que si dos usuarios
suben el mismo audio, el blob se sube una sola vez (subida es upsert-seguro por ser
content-addressed); cada usuario tiene igualmente su propia fila en `sounds`, porque la
fila —no el blob— es lo que tiene dueño y metadata editable (nombre, gain, trim, loop,
categoría).

## 6. Flujo de datos

**Autenticación.** `signup` crea el usuario en Supabase Auth (envía email de
confirmación); `login` autentica y guarda la sesión (access + refresh token) en el
keyring del SO; `logout` la borra; `whoami` la muestra. Cualquier operación de
`remote/` sin sesión válida falla con un mensaje explícito pidiendo `auth login` — nunca
en silencio. El refresh token permite que la sesión sobreviva entre ejecuciones de la
CLI sin volver a pedir contraseña.

**Añadir un sonido (`sounds add`).** Decodifica localmente con `library/importer.py` →
calcula SHA-256 → si ya existe una fila propia con ese hash, la operación es idempotente
y resuelve a ella sin error → si no, sube el blob (si el hash no existe ya en Storage) e
inserta la fila en `sounds`. Orden importante: Storage primero, fila en Postgres después
— si el INSERT falla, el blob queda huérfano pero inofensivo, y el reintento es seguro
por ser content-addressed.

**Listar (`sounds list`).** `SELECT` sobre `sounds`, con join a `profiles.display_name`
y `categories.name` para mostrar quién subió cada sonido y en qué categoría está.
Filtros `--mine` y `--category`.

**Reproducir (`run --sound <id-o-nombre-o-ruta>`).** Si el valor es una ruta de fichero
local existente, comportamiento de la fase 1 sin cambios, sin tocar `remote/`. Si no, se
resuelve como id/nombre contra `sounds`: si `<cache>/soundboard/pcm/<sha256>.f32` existe,
se usa directo; si no, se descarga de Storage y se cachea. El motor de audio recibe PCM
ya en RAM, igual que hoy — nunca decodifica ni hace I/O en el callback de tiempo real.

**Editar/borrar (`sounds edit` / `sounds rm`).** `UPDATE`/`DELETE` por id. RLS bloquea si
el usuario no es el dueño. La CLI debe leer las filas afectadas de la respuesta de
PostgREST: si son 0, muestra "no tenés permiso, no es tuyo" — nunca reporta éxito falso
por no verificar el conteo.

**Categorías (`categories add` / `list` / `rm`).** Cualquier autenticado puede crear una;
solo el creador puede borrarla o renombrarla, vía la misma RLS que `sounds`.

## 7. Superficie CLI

```
soundboard auth signup
soundboard auth login
soundboard auth logout
soundboard auth whoami

soundboard sounds add <path> --name NAME [--category NAME]
soundboard sounds list [--mine] [--category NAME]
soundboard sounds edit <id> [--name] [--category] [--gain-db] [--trim-start] [--trim-end] [--loop/--no-loop]
soundboard sounds rm <id>

soundboard categories add <name> [--color]
soundboard categories list
soundboard categories rm <name>

soundboard run --mic "..." --out "CABLE Input" --sound KEY=<ruta-local-o-id-o-nombre>
```

`run --sound` extiende, no reemplaza, la sintaxis de la fase 1: sigue aceptando rutas
locales tal cual.

## 8. Configuración

`SOUNDBOARD_SUPABASE_URL` y `SOUNDBOARD_SUPABASE_ANON_KEY` como variables de entorno,
con fallback a `<config>/soundboard/settings.json`. El anon key es público por diseño de
Supabase — la protección la da RLS, no el secreto del key.

## 9. Estructura de ficheros

```
src/soundboard/
├── remote/
│   ├── client.py       Supabase client factory + carga/guardado de sesión vía keyring
│   ├── auth.py         signup / login / logout / whoami
│   ├── sounds.py       CRUD de sounds + upload/download contra Storage
│   ├── categories.py   CRUD de categories
│   └── models.py       Sound, Category, Profile (dataclasses)
├── library/
│   ├── importer.py     sin cambios
│   └── cache.py         download-on-miss por sha256, en vez de copy-on-import
└── cli.py               + subcomandos auth / sounds / categories
```

## 10. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Sin sesión / token expirado | Falla con mensaje explícito: `soundboard auth login` |
| Sin red al operar sobre la biblioteca | Error explícito, sin fallback silencioso |
| RLS deniega UPDATE/DELETE (no es tuyo) | CLI verifica filas afectadas; si son 0, "no tenés permiso, no es tuyo" |
| Subida falla a mitad | Storage antes que fila en Postgres; blob huérfano es inofensivo, reintento seguro |
| `add` con hash ya existente del mismo owner | Idempotente, resuelve a la fila existente, no es error |
| Nombre de categoría duplicado | Error claro por `unique(name)`, sugiere la existente |
| Caché local corrupta o ausente al reproducir | Re-descarga transparente desde Storage |
| Signup sin confirmar email | Mensaje explícito: confirmar email antes de poder hacer login |

Principio heredado del diseño original: ningún fallo se traga en silencio.

## 11. Estrategia de pruebas

- **Unitarias, sin red.** `remote/*` contra un cliente Supabase fake (protocolo, mismo
  patrón que `AudioBackend`/`FakeBackend` de la fase 1). `library/cache.py` con un
  fetcher fake: hit de caché, descarga en miss, recuperación ante corrupción.
- **Integración de RLS, marcador `supabase` (excluido por defecto, como `hardware`).**
  `supabase start` (Supabase CLI, requiere Docker) levanta Postgres+Auth+PostgREST+Storage
  local; se aplican las migraciones SQL de §4; los tests crean dos usuarios reales y
  verifican que el dueño puede editar lo suyo y que el otro usuario recibe 0 filas
  afectadas al intentarlo. Corre en CI como job aparte (necesita Docker) y a mano en
  desarrollo. Es la única forma de validar RLS de verdad — un mock no puede reproducir el
  comportamiento del motor de políticas de Postgres.
- **Manual.** Checklist con dos cuentas reales antes de cada release: signup, confirmación
  de email, login en dos máquinas, edición cruzada denegada, reproducción con caché fría y
  caliente.

## 12. Limitaciones conocidas

- Blobs huérfanos en Storage no se limpian cuando la última fila que los referencia se
  borra (§1, no objetivo de esta fase).
- El fichero original no se conserva remotamente, solo el PCM preprocesado (§6).
- Sin modo sin conexión para operaciones de biblioteca (§1); solo `run --sound <ruta>`
  con rutas locales funciona sin red, heredado de la fase 1.

## 13. Dependencias nuevas

| Paquete | Uso |
|---|---|
| `supabase` (SDK oficial `supabase-py`) | Cliente único para Auth + PostgREST + Storage |
| `keyring` | Persistencia de sesión en el almacén de credenciales del SO |

Versiones exactas por fijar en el plan de implementación (verificar wheels compatibles
con Python 3.13, igual que se hizo para el resto del stack). Dependencia externa al
ecosistema Python, solo para desarrollo/CI: Supabase CLI + Docker, para el stack local
usado en los tests de integración de RLS (§11).
