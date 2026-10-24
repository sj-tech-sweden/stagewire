# Stagewire

Stage plot, patch sheet and input-list tooling for live audio, video and lighting
professionals, with first-class sync to **Stockwire Rental** for gear lists and job
assignments.

This is a monorepo:

```
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

## Feature phases

- **Phase 1 (this scaffold)**: Audio engine — input list / patch sheet, stage-plot
  designer models, mic & wireless plotter; Stockwire Rental integration (job/gear
  linking + "request to add" push-back stub).
- **Phase 2 (prep)**: Video suite — pixel map / LED wall, video patch & signal flow.
- **Phase 3 (prep)**: Lighting & rigging — DMX fixture patch, rigging & power plot.

Domain folders for video and lighting exist as stubs for later phases.
