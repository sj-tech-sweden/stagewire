# Unified multi-domain refactor: progress & handoff

Last updated: 2026-10-29. Nothing here is committed yet (working tree only, branch `main`).
Read `AGENTS.md` first; rule 0 (ask when unclear) applies to every open question below.

## Decisions made (do not re-litigate)

| Topic | Decision |
|---|---|
| Data model | **Full replacement.** All domains (audio, lighting, video, power/rigging) end up on one `GraphDevice` + `ConnectionEdge` model. Done in phases (below) so the tree stays green between phases. |
| Conflicts | Optimistic concurrency: integer `revision` per row, `expected_revision` on every PATCH/DELETE, `409 {code: "revision_conflict", current: <row>}`. Client does a field-level three-way merge and only asks the user about fields both sides changed. |

## Status

| # | Phase | State |
|---|---|---|
| 0 | Stabilise revision/conflict work on audio patch rows | **Done** (backend + store) |
| 1 | Unified `GraphDevice` / `ConnectionEdge`, traversal + validation, REST, WS events | **Done** (backend, new tables) |
| 2 | Stockwire client: global catalog search, case children, request-to-add | **Done** on our side; upstream contract **unverified** |
| 3 | Pinia graph store + WS deltas + merge utils | **Done** |
| 4 | Quasar UI: `JobWorkspaceView`, `MultiDomainPatchDrawer`, `StockwireCatalogDrawer`, inspector, layer HUD | **Not started** |
| 5 | Mode A/B switching UI (store state + `placeUnplaced` exist, no view) | **Not started** |
| 6a | Backfill legacy audio devices, channel input chains, DMX trees and power trees into the graph | **Done** (`POST /jobs/{id}/graph/backfill`, idempotent) |
| 6b | Backfill video chains and audio **output** chains | **Not started** |
| 6c | Repoint routers, reports, exports, stage plot to read the graph, one domain at a time | **Not started** (the big one) |
| 7 | Retire legacy tables (new Alembic revision, never edit old ones) | **Not started** |

## What exists

### Backend (`api/`)
- `app/core/versioning.py`: `run_versioned_write` / `run_versioned_delete` / `raise_revision_conflict`. Shared by audio and graph routers. Rows use SQLAlchemy `version_id_col`, so a race that slips past the pre-check surfaces as `StaleDataError` and is turned into the same 409.
- `app/domains/audio/*`: `revision` on `AudioChannelPatch`, `ChannelPatchPoint`, `ChannelListOutput`, `OutputPatchPoint`; updates require `expected_revision` (body), deletes require `?expected_revision=`.
- `app/domains/graph/`
  - `models.py`: `GraphDevice` (domain, kind, name, `attributes` JSONB, `ports` JSONB, `canvas_x/y_cm`, `canvas_rotation`, `case_parent_id`, Stockwire binding + `stockwire_booked` + `stockwire_request_status`, `legacy_ref` for backfill, `revision`) and `ConnectionEdge` (signal, src/dst device+port, channels, `phase` L1/L2/L3, cable label, attributes, `revision`). JSON columns use `JSON().with_variant(JSONB, "postgresql")` so sqlite tests work.
  - `topology.py`: pure functions. `trace` (up/downstream BFS, signal filter, depth cap), `would_create_cycle`, `validate_edge` (direction, signal, connector compatibility incl. 19-pin Socapex, channel counts both ways, port reuse / fan-out via port `max_connections`, phase only on power), `phase_loads`.
  - `router.py` under `/api/v1/jobs/{job_id}/graph`: `GET` (whole graph), devices CRUD + `POST /devices/batch` (max 200), edges CRUD, `GET /devices/{id}/trace?direction=`, `GET /validate`, `GET /power-load`, `POST /devices/{id}/request-stockwire`. Edge create rejects loops and invalid connections with 422 (`?force=true` bypasses issues, not loops).
- `app/domains/stockwire/client.py`: `search_catalog` (`GET /api/v1/inventory/search`), `list_child_devices` (`GET /api/v1/inventory/devices?case_device_id=`). Router: `GET /stockwire/catalog/search`, `GET /stockwire/catalog/cases/{id}/children`; both return empty results when Stockwire is not configured.
- Migrations: `b2c3d4e5f6g7` (revisions), `c3d4e5f6g7h8` (graph tables). Head is `c3d4e5f6g7h8`.
- Tests: `tests/test_revision_conflicts.py`, `tests/test_graph.py` (topology, API, conflicts, Stockwire request with a fake client). Full suite: 127 passed. `ruff check` and `ruff format --check` clean.

### WebSocket events (all broadcast on the existing `/ws/jobs/{job_id}` room)
`graph.device.upsert` (full `GraphDeviceRead`), `graph.device.delete` (`{id, edge_ids}`), `graph.edge.upsert` (full `ConnectionEdgeRead`), `graph.edge.delete` (`{id}`). Batch create emits one upsert per device. The in-process manager is single-worker only; multiple workers need Valkey pub/sub (noted in `ws.py`).

### Frontend (`web/`)
- `src/utils/graph.js`: `upsertVersioned`, `applyGraphEvent`, `threeWayMerge`, `placeUnplaced`.
- `src/stores/graph.js`: fetch, CRUD, batch create, `requestStockwireBooking`, `trace`, `mode` (`canvas`|`list`), conflict handling (`conflict`, `resolveConflict`).
- `src/stores/channels.js`: audio revision handling with `conflict`, `reapplyConflict`, `clearConflict` (no UI consumes these yet).
- `src/pages/JobDetailPage.vue`: routes `graph.*` WS events into the graph store.
- Tests: `web/e2e/unit/graph.spec.ts` (4 cases). `eslint .` clean, `quasar build` succeeds.

## Backfill mapping (phase 6a, decisions made)

- Legacy connector group `{direction, connector, count}` becomes **one port** (`in-xlr3`, `channels=count`). Edges carry used channel numbers in `attributes`.
- Port validation is capacity based: edges on a port may sum up to its `channels`; a port without `channels` accepts one edge (outputs: up to `max_connections`).
- Each audio channel row becomes a `kind="channel"` source device; each patch point becomes an edge from the previous hop to the device.
- `AudioDevice` -> `GraphDevice` (domain guessed: fixture_type -> lighting, video fields -> video, else audio). A lighting fixture or power node linked to a device is merged into that device's `attributes`; unlinked ones become their own devices.
- DMX steps -> `dmx` edges (root steps hang off the universe source device, `attributes.universe`); power parent/extra feeds -> `power` edges with phase; fixture `power_node_id` -> power edge.
- Every row/edge gets `legacy_ref` (`table:id`); re-running only adds what is new. Edits made in the graph are not overwritten (existing refs are skipped), and nothing is ever deleted by the backfill.
- Not mapped yet: video chains (`video_patch_points`, `video_output_patch_points`) and audio output chains (`output_patch_points`; direction of the chain vs console needs confirming).

## Conflict resolution: how it works

1. Client sends `expected_revision` = revision of the row it last saw.
2. Match: write applies, `revision` +1, WS broadcast of the new row.
3. Mismatch: server answers 409 with the current row. Client stores that row (stale revisions never overwrite newer ones) and runs `threeWayMerge(base, mine, theirs)`.
4. No overlapping fields: auto-retry once with the merged fields against the new revision.
5. Overlapping fields: `store.conflict` holds `{base, draft, current, conflicts[]}`; the UI must show a mine/theirs choice per field and call `resolveConflict({field: 'mine'|'theirs'})`.
6. Deletes of a stale row also 409, so nobody silently deletes someone else's edit. Deleting a device deletes its edges explicitly (sqlite in tests does not enforce `ON DELETE CASCADE`).

`web/src/components/ConflictDialog.vue` renders `conflicts[]` for both the channels and graph stores (mounted in `JobDetailPage.vue`, en/sv strings under `conflictDialog`); the channels store now auto-merges too. Gaps: the store-level retry and dialog flow have no automated test yet (only `threeWayMerge` is unit-tested); add a Playwright spec with a mocked 409 against the running stack. Collaborative text fields (notes) still last-merge by field, not by character.

## Next steps (suggested order)

1. ~~Conflict dialog~~ done.
2. **Phase 6b/6c**: map video chains and audio outputs in `app/domains/graph/backfill.py`, then repoint each domain router/service/report/exporter at the graph one domain at a time, keeping its tests green. Backfill must run for existing jobs (call the endpoint per job or add a startup/CLI loop) before any reader switches over.
3. **UI** (all must follow AGENTS.md §10, phones stack panes and tables become cards):
   - `JobWorkspaceView.vue`: master-detail split, header Mode A/B switch using `graphStore.mode`; entering canvas mode calls `placeUnplaced` and PATCHes positions.
   - `MultiDomainPatchDrawer.vue`: tabs Audio / DMX / Power / Video over `devicesByDomain`, `q-table` with virtual scroll, card list on `$q.screen.lt.sm`.
   - `StockwireCatalogDrawer.vue`: facets (category, manufacturer, attributes, availability dates), multi-select batch add via `createDevices`, case expansion via `/stockwire/catalog/cases/{id}/children`, a "Request to add to Stockwire Job booking" button on any device in `graphStore.unbooked`.
   - Inspector drawer and layer HUD with phase load from `/power-load`.
4. Playwright e2e for the workspace flows (needs the Docker stack).
5. Phase 7 cleanup once nothing reads the legacy tables.

## Open questions / risks

- **Stockwire upstream contract is unverified.** `/api/v1/inventory/search` (facets, `attr.*` filters, availability range) and `/api/v1/inventory/devices?case_device_id=` are not in `docs/stockwire-integration-spec.md` and the `stockwire-rental` repo is not available here. Add them to the spec and confirm response shapes (`items`, `total`, `facets`, per-item availability) with that team. Until then the client is only tested against a fake.
- **Migration `c3d4e5f6g7h8` is hand-written and was only checked via `alembic heads` and the sqlite `create_all` path.** Run `alembic upgrade head` and `alembic revision --autogenerate` against an empty Postgres (port 5433) to confirm there is no drift. Not done in this session.
- **Connector compatibility table** in `topology.py` is a small starter set (XLR3/5, SDI, HDMI, RJ45, Powercon, Schuko, Socapex 19). Needs a domain review before relying on it.
- Channel-count rule currently requires equal channel counts on both ports of an edge; real splitters/breakouts are modelled as separate devices. Confirm that matches how techs think about it.
- Phase 6 is the highest-risk step (reports, console exports and the stage plot all read the legacy tables). Estimate and split per domain before starting.

## Verify locally

```
cd api && ./.venv/bin/ruff check app tests && ./.venv/bin/ruff format --check app tests && ./.venv/bin/pytest -q
cd web && ./node_modules/.bin/eslint . && ./node_modules/.bin/playwright test e2e/unit && npx quasar build
```
