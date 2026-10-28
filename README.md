# Stagewire

Stage plot, patch sheet and input-list tooling for live audio, video and lighting
professionals, with first-class sync to **Stockwire Rental** for gear lists and job
assignments.

This is a monorepo:

```text
.
├── api/   FastAPI backend (Python 3.12+, SQLAlchemy 2 async, Alembic)
├── web/   Quasar / Vue 3 PWA frontend (Pinia, Konva.js stage-plot canvas)
└── .github/  CI/CD, release-please, Renovate
```

## Architecture at a glance

- **12-factor**: all configuration via environment variables (pydantic-settings).
  Nothing is hardcoded.
- **Backend**: stateless FastAPI processes; PostgreSQL + Valkey (cache / WebSocket
  sessions) as backing services.
- **Frontend**: Quasar PWA, talks to the backend over REST + async WebSockets.
- **Releases**: `release-please` semantic versioning → GitHub Container Registry
  (`ghcr.io/sj-tech-sweden/stagewire-*`) via GitHub Actions.
- **Dependencies**: bundled & kept current with Renovate.

See [`AGENTS.md`](./AGENTS.md) for contributor / LLM agent guidelines.

## Default dev ports (non-conflicting with stockwire-rental)

| Service   | Stagewire dev | Stockwire-rental (avoid) |
|-----------|---------------|--------------------------|
| API       | `8010`        | `8000`                   |
| Web dev   | `9010`        | `9000`                   |
| Postgres  | `5433`        | `5432`                   |
| Valkey    | `6380`        | `6379`                   |

## Quick start

```bash
# 1. Start backing services
docker compose up -d db valkey

# 2. Backend
cd api
uv sync                 # or: pip install -e .
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8010

# 3. Frontend (separate terminal)
cd web
npm install
npx quasar dev -p 9010
```

Or run the whole stack (api + web + db + valkey) with:

```bash
docker compose up --build
```

## First-time setup & admin account

Stagewire has **no hardcoded credentials**. The first time the API boots against an
empty database it is in *setup mode*; you create the initial admin account via the
`/setup` page in the UI, or by calling the setup endpoint:

```bash
curl -X POST http://localhost:8010/api/v1/auth/setup \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@stagewire.test","password":"Test1234!","first_name":"Admin","last_name":"User"}'
```

For local development the convention is to use `admin@stagewire.test` /
`Test1234!` (this is the account the E2E suite provisions). **Change this password
as soon as you log in.**

After logging in as an admin:

- Change your password or manage users under **Admin Settings → Users**.
- Configure single sign-on (OIDC / SAML) under **Admin Settings → SSO**. SSO
  providers are stored in the database (`AppSetting` key `sso_config`) and only
  appear on the login page when **SSO is enabled** and the individual provider is
  **enabled**. Re-run `/auth/sso/config` (PUT) after editing to persist changes.

The database schema is owned by **Alembic**. On every API container start the
entrypoint runs `alembic upgrade head`, so migrations are applied automatically
when you redeploy. `Base.metadata.create_all` is only used as a fallback by the
SQLite test suite.

## Uploaded images & data persistence

- **Stage plot element images** are uploaded through `POST /api/v1/uploads` (auth
  required, image types only, max `MAX_UPLOAD_BYTES` which defaults to 5 MB). The
  API writes each file to `UPLOAD_DIR` and serves it from `/static/...`; the
  `image_url` column on stage plot elements stores only that URL.
- In the bundled `docker-compose.yml`, `UPLOAD_DIR` is `/app/uploads` and that path
  is a **persistent volume** (`stagewire-uploads`), so uploaded images survive
  container rebuilds and restarts.
- For local (non-Docker) development, set `UPLOAD_DIR` to a writable directory; the
  API auto-creates it and mounts `/static` over it. If the directory is not writable,
  the upload endpoint still validates input and reports the failure when used.
- Uploaded files live on the API's local filesystem (not in the database). For
  multi-node deployments you would swap this for object storage (S3-compatible) and
  serve via its URL; nothing else in the data model would change.
- Application data (**PostgreSQL**) and cache/sessions (**Valkey**) are likewise
  persisted through the `stagewire-db-data` and `stagewire-valkey-data` volumes.

## Venues and speaker coverage

- **Venues** are a shared library (`/venues`): a venue has a size, a stage rectangle
  inside it and an optional floor-plan image. Assigning one to a job copies those
  values onto the job, so later edits to the venue do not change jobs by accident.
  Use the venue's "update jobs" actions to push changes to all jobs or to jobs created
  since the last push.
- The stage plot draws the venue as its canvas. The stage can be dragged within the
  venue, and elements and cables stay positioned relative to the stage.
- Speakers (`speaker_main`, `speaker_sub`, `speaker_delay`, and `monitor`) carry a
  horizontal coverage angle and throw distance, and can link to an output patch point.
- **Sound coverage** on the stage plot draws each speaker's sector and a covered/gap
  overlay. The grid comes from `GET /api/v1/jobs/{job_id}/coverage?cell_cm=25`.
- **Camera coverage** and **Projector coverage** have their own toggles. The choice of
  **Range** (widest and narrowest ends of a zoom) or **Chosen focal** is remembered in
  the browser with the three toggles, so it survives reloads on that browser.

## Cameras and lenses

- A camera device holds its sensor width (mm), focal range (shortest and longest, mm)
  and an optional **recommended** maximum distance (m). A lens device holds only the
  focal range. A camera with an integrated lens takes everything from one product or
  from the camera device itself.
- The sensor width can be calculated from an aspect ratio (for example `16:9`) and a
  diagonal in mm or inches, with fractions accepted (`7/8`, `1 1/2`, `1/4.7`). Common
  sensor sizes are presets; the Panasonic 1/4.7 3MOS preset is an estimate until a
  datasheet value is entered.
- Placing a camera on the plot creates a camera device, or a new one from the element
  editor (named in a dialog). Camera values come from Stockwire when the product has
  them (`cam_sensor_width_mm`, `lens_focal_length_min/max_mm`, `cam_max_distance_m`),
  otherwise from the device. The field of view is horizontal:
  `2 × atan(sensor ÷ (2 × focal))`.
- The view runs to the venue wall. The recommended maximum distance is drawn as a
  dotted outline; it is not a hard limit.

## Projectors and screens

- A projector device holds its throw ratio range (distance ÷ image width, shortest and
  longest, as usually given in specifications) and an optional image aspect ratio
  (16:9 by default).
- A **screen** is a plot object drawn as a thin line; its height is vertical and only
  used for the fit. A projector targets the nearest screen that sits inside its throw
  angle; otherwise it throws to the venue wall.
- The projector cone's image width at the screen is distance ÷ throw ratio. The zone is
  green when the image can fill the screen, amber when the projector is too close or
  too far.
- Projectors take their signal from a **video output chain** (for example from a
  switcher or computer), never from an input chain.

## Video inputs, outputs and chains

- Video inputs and outputs are lists per job, edited inline or in a dialog. Each has a
  **patch chain** of devices, and each step records the output port it takes from
  (`OUT 3`) and the input port it feeds (`HDMI 1`).
- Output chains can **split**: a step can take its signal from any earlier step, so one
  switcher output can feed several devices, and a passthrough can feed further devices.
  Input chains are straight lines.
- The **signal flow** dialog draws the chain as a tree, with the ports on each line.
- In a patch step, typing the name of an existing device chooses it; a device created
  from a step is chosen at once.

## Lighting: DMX fixture patch

- The fixture patch is one row per fixture: universe, DMX address, fixture type, channel
  mode, footprint (channels), location or truss position, gel or colour, purpose and notes.
  Open it from the job's **Lights** tab, next to Sound, Video and Rigging & power.
- A fixture takes a **fixture type** from the job's library and one of its **channel modes**.
  Typing a new name in either box adds it to the library; the mode's footprint sets the
  fixture's footprint. A type can have several modes, and an MVR import keeps every mode
  its GDTF file defines. A type also holds a manual weight and power, used for loads on the
  rigging tab when the device gives no value.
- The fixture patch is reported from the **Reports** page like any other report
  (`lighting.fixture-patch`).
- A row can be linked to a fixture device by typing its name. Typing a new name creates
  the device. The device's fixture type, mode, footprint and gel fill empty row fields.
- The patch flags a **DMX overlap** when two fixtures in the same universe share a channel,
  and **past channel 512** when a footprint runs beyond its universe.
- **Import** reads a CSV (one row per fixture, headers as on the patch sheet; `;` or `,`
  separators) or an MVR file (My Virtual Rig, exported by Capture 2021 or later, MA,
  Vectorworks or WYSIWYG). From MVR the address, position (its truss or position name, or
  coordinates), mode and footprint come from the scene and the GDTF file it names. Imports
  replace the fixtures of an earlier import unless that is switched off.
- Weight and power are device values for rigging and power planning. A Stockwire product
  value (`weight_kg`, `power_consumption_watts` on the product) overrides the value entered
  on the device, field by field; see `docs/stockwire-integration-spec.md` §3.8.

## Rigging & power

- The **Rigging & power** tab is shared by sound, video and lighting. Trusses (hanging
  points) have a weight capacity; distros have a voltage and an amps-per-phase capacity,
  and their circuits each sit on one phase with a breaker rating.
- Every fixture on the Lights tab and every plot element linked to a device is a load.
  Its weight and power come from the device; a Stockwire value overrides the value
  entered on the device, field by field. Choose the truss and the circuit each load uses.
- A power circuit is **single-phase** (on one of L1, L2 or L3) or **three-phase** (its
  load is shared over L1 to L3). Distro voltage is phase to neutral (230 V), so a three-phase
  circuit draws watts ÷ (3 × 230) amps on each line.
- The summary shows the weight on each truss against its capacity, the amps on each
  circuit against its breaker (amps = watts ÷ distro voltage), each phase against the
  amps-per-phase capacity, and the phase imbalance. Loads not on a truss or circuit are
  listed.

## Cables and cableways

- Cables are derived from the sound and video chains, from speaker outputs, and from
  video output chains. Each cable is routed over cableways when that saves distance,
  around the audience area unless the detour is much longer, and can be fixed with
  manual waypoints or hidden.
- Cables are grouped by length class and by connector, with a CSV export.

## Reports and the stage plot in PDF

- Stage plot reports route cables and draw coverage with the same rules as the plot:
  the routing runs on the server (`api/app/domains/reports/cable_routing.py`) and the
  view geometry in `plot_geometry.py`, mirroring `web/src/utils/cables.js`,
  `camera.js` and `projection.js`.
- The report options include speaker, camera and projector coverage (camera view
  range or chosen focal length), cables, cableways, and the venue or stage view.
- The template editor's layout preview draws the same coverage and cables, using the
  job's audience area and video lists.

## Testing and linting

```bash
# Backend (from api/)
./.venv/bin/ruff check app tests && ./.venv/bin/ruff format --check app tests
./.venv/bin/pytest -q

# Frontend (from web/)
./node_modules/.bin/eslint .
./node_modules/.bin/quasar build
./node_modules/.bin/playwright test e2e/unit        # geometry and parsing unit specs
./node_modules/.bin/playwright test                 # full e2e suite (needs the stack running)
```

Migrations are reviewed before commit; see `AGENTS.md` for the Alembic workflow.

## Feature phases

- **Phase 1 (this scaffold)**: Audio engine — input list / patch sheet, stage-plot
  designer models, mic & wireless plotter; Stockwire Rental integration (job/gear
  linking + "request to add" push-back stub).
- **Phase 2 (in progress)**: Video suite — video inputs, outputs, patch chains with
  ports and splits, signal flow, cameras, lenses, projectors and screens are in. The
  pixel map / LED wall is not.
- **Phase 3 (in progress)**: Lighting & rigging. The fixture patch, fixtures on the stage
  plot, the fixture patch PDF and the rigging & power tab are in. Rigging & power is shared
  with sound and video. Still open: a rigging plot drawing on the stage plot itself and
  Stockwire fixture profile fields.
