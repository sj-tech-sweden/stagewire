# AGENTS.md — Contributor & LLM Agent Guidelines

These guidelines apply to **all** contributors, including LLM coding agents working in
this repository. Follow them without exception.

## 0. When in doubt, ask

> **If anything in a task, spec, or existing code is unclear, ambiguous, or
> under-specified, STOP and ask the user for clarification before writing code or
> making changes.** Do not guess at intent, invent requirements, or silently pick a
> design decision that affects behaviour or data models. A short clarifying question
> is always cheaper than a wrong implementation.

## 1. Repository shape

Monorepo with two deployable units:

- `api/` — FastAPI backend (Python 3.12+, Pydantic v2, SQLAlchemy 2.0 async, Alembic).
- `web/` — Quasar (Vue 3) PWA frontend (Pinia, Konva.js for the stage-plot canvas).

Keep backend and frontend concerns separate. The frontend never talks to the database
directly; it goes through the REST/WebSocket API.

## 2. Architecture & 12-factor rules

- **Config is environment-only.** Read all configuration from env vars via
  `app/core/config.py` (pydantic-settings). Never hardcode hosts, ports, secrets, or
  URLs. Add new settings there and document them in `api/.env.example`.
- **Stateless processes.** Backend containers hold no local state. Sessions/cache live
  in Valkey; durable data lives in PostgreSQL.
- **Backing services**: PostgreSQL (async via `psycopg` v3) and Valkey
  (`redis://...` from `REDIS_URL`).
- **Health checks**: expose `/api/v1/health/live` and `/api/v1/health/ready`
  (mirrors stockwire-rental). `ready` must reflect DB/Valkey connectivity.
- **API versioning**: all routes live under `/api/v1/...`.

## 3. Conventions to mirror (from stockwire-rental)

This project is the sibling of `stockwire-rental`. Reuse its patterns:

- FastAPI + pydantic-settings config objects.
- Domain-driven folders under `app/domains/<domain>/` with
  `models.py` (SQLAlchemy), `schemas.py` (Pydantic), `router.py`, `service.py`.
- Models use SQLAlchemy 2.0 typed `Mapped`/`mapped_column`.
- Schemas use Pydantic v2 with `model_config = ConfigDict(from_attributes=True)`.
- Images publish to `ghcr.io/sj-tech-sweden/stagewire-{backend,frontend}`.
- Renovate config groups stagewire images into a single PR (see `.github/renovate.json`).

## 4. Dev ports (do NOT reuse stockwire-rental defaults)

| Service  | Port |
|----------|------|
| API      | 8010 |
| Web dev  | 9010 |
| Postgres | 5433 |
| Valkey   | 6380 |

If you add a new local service, pick a port that does not collide with these or with
stockwire-rental (8000 / 9000 / 5432 / 6379).

## 5. Code style

- Python: `ruff` (lint + format). Type-hint everything. No comments unless asked.
- Frontend: ESLint + Prettier as configured by Quasar; `<script setup>` SFCs.
- Commits: conventional commits (`feat:`, `fix:`, `chore:`, …) — release-please derives
  versions and changelogs from them.
- Do not commit secrets, `.env`, or generated lockfile diffs that leak credentials.

### 5a. Always run the linters before finishing

Before declaring any backend change done (and before committing), an LLM agent MUST
run the linters and fix every issue it reports — do not leave the tree red:

- Backend: `cd api && ./.venv/bin/ruff check app tests` and
  `./.venv/bin/ruff format --check app tests` (auto-fix with
  `./.venv/bin/ruff format app tests` and `./.venv/bin/ruff check --fix app tests`).
- Frontend: `cd web && ./node_modules/.bin/eslint .` (and the Quasar build for
  type/template errors).
- Treat `ruff format --check` failures as errors: a file "would be reformatted" means
  you must reformat it. CI fails on any lint/format error, so a clean local run is the
  bar for "done".

## 6. Testing

- Backend: `pytest` under `api/tests/`. Each domain router gets at least one happy-path
  test using `httpx.AsyncClient` + the FastAPI `app` (or `ASGITransport`).
- Frontend: component tests where practical.
- CI runs lint + tests + image build on every PR (see `.github/workflows/ci.yml`).

## 6b. Database migrations (Alembic)

Schema is defined in SQLAlchemy `Mapped` models under `app/domains/<domain>/models.py`
(collected on `app.core.db.Base.metadata`). Alembic is the **source of truth for
production schema**; the `init_db()` startup hook still calls `Base.metadata.create_all`
as a no-op-safe fallback for local dev and the sqlite test suite (which never runs
migrations).

Workflow:

- Generate a new revision after changing models:
  `cd api && DATABASE_URL=<your-db-url> ./.venv/bin/alembic revision --autogenerate -m "describe change"`
  (point `DATABASE_URL` at an **empty** database so the diff is complete; the
  `migrations/env.py` already registers the audio + auth models and reads
  `DATABASE_URL` from settings).
- Apply migrations: `DATABASE_URL=<db-url> ./.venv/bin/alembic upgrade head`.
- Record an existing database's schema without running DDL (e.g. a DB already
  built by `create_all`): `DATABASE_URL=<db-url> ./.venv/bin/alembic stamp head`.
- Always review the autogenerated `upgrade()/down_revision` before committing; the
  autogenerate comment reminds you to adjust. Keep FK/`ondelete` and `server_default`
  behaviour explicit.
- Never hand-edit a committed migration's `down_revision` chain; add a new revision
  instead.

## 7. Domain roadmap

- **audio** (Phase 1, implemented): `ProductionJob`, `AudioChannelPatch`,
  `StagePlotElement`, mic/wireless plotter.
- **stockwire** (Phase 1, client + stub): job/gear sync, "request to add" push-back.
- **video** (Phase 2, stub): pixel map / LED wall, video patch.
- **lighting** (Phase 3, stub): DMX fixture patch, rigging & power plot.

When implementing a later phase, create its `models.py`/`schemas.py`/`router.py` under
`app/domains/<domain>/` following the audio domain as the reference template.

## 8. LLM agent workflow

1. Read this file and the relevant domain before changing anything.
2. If scope/behaviour is ambiguous → ask (see rule 0).
3. Make the minimal change that satisfies the request; match existing patterns.
4. Run the project's lint/test commands before declaring done.
5. Never expand scope beyond what was asked without checking first.

## 9. Shared design system (with stockwire-rental)

The web frontend reuses the **Stockwire Rental design system** so both apps feel
like one product:

- Quasar brand palette in `web/quasar.config.js` (`framework.config.brand`):
  cable-green `primary #3F873F`, `secondary #26A69A`, `accent #35A853`,
  `dark #0C1114`, plus positive/negative/info/warning.
- Dark mode is the default (`src/boot/theme.js` calls `Dark.set(true)`).
- Design tokens (CSS custom properties `--ec-*`: colors, surfaces, typography,
  spacing, radius, shadows) live in `web/src/css/app.css`, copied from
  `stockwire-rental/design/tokens/tokens.css`.

When the Stockwire Rental design tokens change, re-sync those two files. Do not
fork the palette per app.

## 10. Responsiveness (mobile-first frontend)

The web app is a PWA used on phones, not only desktops. Any new frontend
functionality must remain usable on small screens:

- Use Quasar's `$q.screen` breakpoints (`xs`/`sm`/`md`/`lg`/`xl`). The phone
  boundary is `lt.sm` (below 600px). Prefer `$q.screen.lt.sm` / `gt.sm` helpers
  over fixed-pixel media queries.
- **Tables become cards on phones.** Dense `q-table` grids do not fit a phone.
  When a page shows tabular data, render a `q-list` of `q-card`s on
  `$q.screen.lt.sm` (wrap the `q-table` in `v-else` and add a
  `v-if="$q.screen.lt.sm"` card block) and reuse the same rows, handlers, and
  inline editors — never drop editing or row actions on mobile.
- **Multi-pane layouts stack on phones.** A side-by-side `q-splitter` (e.g. a
  list beside detail) must not stay side-by-side on a phone. Make it stack
  vertically (`:horizontal="$q.screen.lt.sm"`) or move the secondary pane into a
  `q-drawer` / `q-tabs` so both panes are reachable without horizontal scrolling.
- Provide touch-friendly tap targets; avoid hover-only interactions. Every action
  reachable on desktop must also be reachable by tap on mobile.
- Verify with a narrow viewport (Quasar devtools device toolbar / `lt.sm`) before
  declaring a UI task done.
