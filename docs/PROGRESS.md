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
| 2 | Stockwire client: global catalog search, case children, booked flags, request-to-add | **Done**, verified live against the dev Stockwire |
| 3 | Pinia graph store + WS deltas + merge utils | **Done** |
| 4 | Quasar UI: workspace page, patch drawer, catalog drawer, inspector, layer HUD | **Done** (first version, see below) |
| 5 | Mode A/B switching | **Done** (header toggle, persisted per job in localStorage) |
| 6a | Backfill legacy audio devices, channel input chains, DMX trees and power trees into the graph | **Done** (`POST /jobs/{id}/graph/backfill`, idempotent) |
| 6b | Backfill video chains and audio **output** chains | **Done** |
| 6c | Readers on the graph: console exports, stage-plot cables in reports, channel-list and patch-sheet report contexts | **Done and switched on** (sync-before-read, see below) |
| 6d | Move the *writers* (channel list / patch / device / plot editors) to the graph; port `web/src/utils/cables.js` + `StagePlotPage.vue`; remaining report contexts | **Not started** |
| 7 | Retire legacy tables (new Alembic revision, never edit old ones) | **Not started** |

## What exists

### Backend (`api/`)
- `app/core/versioning.py`: `run_versioned_write` / `run_versioned_delete` / `raise_revision_conflict`. Shared by audio and graph routers. Rows use SQLAlchemy `version_id_col`, so a race that slips past the pre-check surfaces as `StaleDataError` and is turned into the same 409.
- `app/domains/audio/*`: `revision` on `AudioChannelPatch`, `ChannelPatchPoint`, `ChannelListOutput`, `OutputPatchPoint`; updates require `expected_revision` (body), deletes require `?expected_revision=`.
- `app/domains/graph/`
  - `models.py`: `GraphDevice` (domain, kind, name, `attributes` JSONB, `ports` JSONB, `canvas_x/y_cm`, `canvas_rotation`, `case_parent_id`, Stockwire binding + `stockwire_booked` + `stockwire_request_status`, `legacy_ref` for backfill, `revision`) and `ConnectionEdge` (signal, src/dst device+port, channels, `phase` L1/L2/L3, cable label, attributes, `revision`). JSON columns use `JSON().with_variant(JSONB, "postgresql")` so sqlite tests work.
  - `topology.py`: pure functions. `trace` (up/downstream BFS, signal filter, depth cap), `would_create_cycle`, `validate_edge` (direction, signal, connector compatibility incl. 19-pin Socapex, channel counts both ways, port reuse / fan-out via port `max_connections`, phase only on power), `phase_loads`.
  - `router.py` under `/api/v1/jobs/{job_id}/graph`: `GET` (whole graph), devices CRUD + `POST /devices/batch` (max 200), edges CRUD, `GET /devices/{id}/trace?direction=`, `GET /validate`, `GET /power-load`, `POST /devices/{id}/request-stockwire`. Edge create rejects loops and invalid connections with 422 (`?force=true` bypasses issues, not loops).
- `app/domains/stockwire/client.py`: `search_catalog` (over `/inventory/products`, local facets/attribute filters/booked flags), `list_child_devices` (client-side `case_device_id` match + product summary), `booked_quantities`. Tests: `tests/test_stockwire_catalog.py` (mock transport mirroring the dev quirks). Router: `GET /stockwire/catalog/search`, `GET /stockwire/catalog/cases/{id}/children`; both return empty results when Stockwire is not configured.
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

## Workspace UI (phases 4-5)

Route `/jobs/:jobId/workspace` (`web/src/pages/JobWorkspacePage.vue`, opened from the "Workspace" button on the job page).
- `WorkspaceCanvas.vue` (Konva, Mode A): draggable device boxes at `canvas_x/y_cm`, edges as signal-coloured lines, selection, zoom. Unbooked Stockwire items get an amber outline.
- `WorkspaceTable.vue` (Mode B): virtual-scroll `q-table` with inline name/notes edit, Stockwire column with the "Request to add to Stockwire Job booking" button; cards on `$q.screen.lt.sm`.
- `DeviceInspector.vue`: edit name/notes, booking request, connect form (rejected connections list the validator's issues with a "connect anyway" override), upstream/downstream trace, remove. Side card on desktop, bottom dialog below `md`.
- `MultiDomainPatchDrawer.vue`: tabs Audio / DMX / Power / Video over `graph.edges`, virtual-scroll table (cards on phones), inline cable label and power phase, per-row validation status, remove.
- `StockwireCatalogDrawer.vue`: search, multi category/manufacturer facets (counts come from the API), in-stock toggle, multi-select batch add, case expansion by Stockwire device id (creates a `case` device plus children with `case_parent_id`). It states that date-range availability is unavailable (see Stockwire contract).
- Layer HUD toggles audio/lighting/video/power; phase chips use `/power-load` with a fixed 3680 W per-phase limit (placeholder, should come from the power source rating).
- Switching to Mode A auto-places every device without a position (`placeUnplacedDevices`) and never touches patch data, notes or Stockwire bindings. Mode B just hides nothing; spatial data stays in the rows.
- Real-time: the page opens its own job WebSocket (`useJobSocket`) and applies `graph.*` events.
- Tests: `web/e2e/unit/workspace.spec.ts` (helpers), `web/e2e/workspace.spec.ts` (Playwright flows incl. a 390px phone viewport).

Added after the first version: **drag-to-connect** (connect tool in the canvas header; drag from one device to another, ports are auto-picked by `suggestPorts`, rejected connections show the validator's issues with a "connect anyway" action; works with touch because the drop target is hit-tested from the pointer position), **catalog drag-and-drop** (items, or the whole selection, can be dragged onto the canvas or list on screens wider than a phone; the drawer is non-modal there; phones keep click/multi-select), **case picker** (`GET /stockwire/catalog/cases` lists devices that other devices point at via `case_device_id`, since Stockwire has no case flag), and a **real phase limit** (`/power-load` returns `limit_w` = sum of power-source `rating_amps` x 230 V, 16 A fallback).

Known gaps: no edge selection on the canvas; dropping several catalog items offsets them by 20 px each; the legacy job page, stage plot, reports and exports do not read the graph yet (phase 6c).

## Graph readers (phase 6c)

Each reader exists next to its legacy twin, produces the same output, and has a parity test that seeds legacy data, backfills, and compares:
- **Console exports**: `GET /jobs/{id}/graph/lists/{list_id}/export?plugin=` and `/graph/export-plugins` (`graph/readers.py`). `tests/test_graph_exports.py` compares every plugin against the legacy endpoint. The workspace page has an Export menu using it.
- **Cable routing**: `derive_cables_from_graph` / `routed_cable_paths_from_graph` in `reports/cable_routing.py` (routing core shared with the legacy path). Output buses are looked through, channel / video-input nodes are replaced by the plot elements linked to them, and cable keys stay the legacy patch point ids so saved cable routes (`cable_plan.routes`) keep working. `tests/test_graph_cables.py`.
- **Report contexts**: `reports/graph_context.py` (`channel_rows`, `patch_sheets`) wrapped as `_channel_list_context_from_graph` / `_patch_sheet_context_from_graph` in `registry.py`. `tests/test_graph_reports.py`.
- **Plot links**: migration `d4e5f6g7h8i9` adds `stage_plot_elements.graph_device_id` plus `graph_link_role` (`channel`, `video_input`, `output_point`, `device`, `patch_point`). The role is an addition to the agreed design: one id alone cannot say whether a speaker is tied to an output point (draws a cable) or only to a device (does not). Backfill fills both, priority channel > video input > output point > device > patch point, and notes any element that had more than one link. Verified on Postgres (upgrade from empty, no drift on the new columns).
- To make the exports and report contexts lossless the backfill now carries every channel/output field, a `channel_list` container node, and per-point fields (type, connector, label, notes, position) on the chain edges (`first_point` on the console-to-bus edge). Re-running the backfill fills missing attributes on rows that already exist but never overwrites existing values.

**Switched on, with sync-before-read.** Because the editors still write the legacy tables, every graph-backed read first calls `backfill_job` (the legacy endpoint `GET .../channel-lists/{id}/export`, `_channel_list_context`, `_patch_sheet_context`, `_stage_plot_context`). The legacy builders are kept as `*_legacy` for the parity tests. Sync rules (`graph/backfill.py`):
- rows carry `legacy_ref`; new legacy rows are created, untouched graph rows (`graph_edited = false`) are refreshed from legacy, and untouched rows whose legacy source is gone are removed (edges first);
- any row PATCHed through the graph API gets `graph_edited = true` and is never overwritten or pruned by sync (migration `e5f6g7h8i9j0`);
- plot-element links are recomputed on every sync;
- the sync runs under `no_autoflush` with devices flushed before edges (the ORM has no relationship ordering edge inserts after devices; SQLite hides this, Postgres does not) and reports `updated`/`removed` counts; a second sync with no legacy change is a no-op (tested).
- Graph PATCH edits to a row are visible in the exports/reports; legacy edits to a row already edited in the graph are not (the graph wins). Sync does not publish WebSocket events, so open workspace tabs only see legacy-driven changes after a refetch.

**Plot-element links (migration `f6g7h8i9j0k1`)**: real data has elements linked to a device (position) *and* to a video input or output point (cable) (e.g. cameras, speakers). So `graph_device_id` = the device link, and `graph_source_id` + `graph_source_role` (`channel` > `video_input` > `output_point` > `patch_point`) = the source link. `graph_link_role` from the earlier migration is no longer written; drop it with the legacy columns.

**Verified on real data**: a copy of the dev database (517 jobs with audio or plot data, 870 plugin exports, 251 patch sheets, every channel row, all routed cables) matched legacy output exactly after sync and after a second sync; the check also found the FK ordering bug and the two-link bug above, neither visible with SQLite.

Remaining on the legacy path: job summary, fixture patch, stage plot (elements) and video sheet report contexts; `web/src/utils/cables.js` and `StagePlotPage.vue` (the Konva plot derives its own cables client-side); and all writers.

## Backfill mapping (phase 6a, decisions made)

- Legacy connector group `{direction, connector, count}` becomes **one port** (`in-xlr3`, `channels=count`). Edges carry used channel numbers in `attributes`.
- Port validation is capacity based: edges on a port may sum up to its `channels`; a port without `channels` accepts one edge (outputs: up to `max_connections`).
- Each audio channel row becomes a `kind="channel"` source device; each patch point becomes an edge from the previous hop to the device.
- `AudioDevice` -> `GraphDevice` (domain guessed: fixture_type -> lighting, video fields -> video, else audio). A lighting fixture or power node linked to a device is merged into that device's `attributes`; unlinked ones become their own devices.
- DMX steps -> `dmx` edges (root steps hang off the universe source device, `attributes.universe`); power parent/extra feeds -> `power` edges with phase; fixture `power_node_id` -> power edge.
- Every row/edge gets `legacy_ref` (`table:id`); re-running only adds what is new. Edits made in the graph are not overwritten (existing refs are skipped), and nothing is ever deleted by the backfill.
- Audio outputs: first patch point is the console (confirmed). `ChannelListOutput` becomes a `kind="output"` bus node: console -> bus -> rest of chain. A point's parent is `parent_id`, else the previous point; points whose parent is the console hang off the bus.
- Video inputs: each `VideoInput` is a `kind="video_input"` source node feeding its linear chain. `input_port` names the input port on that step's device; `source_port` names the output port on the parent step's device (ports are created on demand).
- Video outputs: parent via `parent_id` only; leaves of the tree feed a `kind="video_destination"` node whose input port `channels` equals the number of leaves.
- `parallel` on output points is kept in edge attributes only; it does not change topology.

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

- **Stockwire contract: verified against the dev instance (2026-10-30)**, and it differs from the original task text. `/api/v1/inventory/search` does not exist (404): global search is `GET /inventory/products` (`search`, single-valued `category`/`brand`/`manufacturer`, `exclude_rental`, `min_inputs/outputs`, envelope `{items,total,skip,limit,has_more}`). `/inventory/devices` only honours `skip`/`limit`: the `case_device_id` filter is **ignored** (returns all devices), and `GET /jobs/requirements?job_id=` also ignores `job_id`. `StockwireClient` therefore filters case children, booked quantities, multi-value facets and attribute filters client-side and computes facet counts itself. Availability is only `eventory_available_qty` (current stock); **date-range availability has no upstream endpoint**, so the catalog response reports `availability.date_range_supported = false` and the UI must not offer a date filter until Stockwire adds one. Worth asking the Stockwire team to honour `case_device_id` / `job_id` filters and add facets + date-range availability.
- **Migrations verified on Postgres (2026-10-30):** `alembic upgrade head` from an empty database succeeds and `alembic check` reports no drift on `graph_*` or the new `revision` columns. It does report six older diffs on other tables (an index on `audio_channel_patches.channel_list_id`, NOT NULL on `audio_devices.ports` and `output_patch_points.connector/patch_label`, TEXT vs String(2000) on two `notes` columns); they predate this work and were left alone. The dev DB (`stagewire-db`) was upgraded to `c3d4e5f6g7h8` when the api container was rebuilt.
- **Connector compatibility table** in `topology.py` is a small starter set (XLR3/5, SDI, HDMI, RJ45, Powercon, Schuko, Socapex 19). Needs a domain review before relying on it.
- Channel-count rule currently requires equal channel counts on both ports of an edge; real splitters/breakouts are modelled as separate devices. Confirm that matches how techs think about it.
- Phase 6 is the highest-risk step (reports, console exports and the stage plot all read the legacy tables). Estimate and split per domain before starting.

## Verify locally

```
cd api && ./.venv/bin/ruff check app tests && ./.venv/bin/ruff format --check app tests && ./.venv/bin/pytest -q
cd web && ./node_modules/.bin/eslint . && ./node_modules/.bin/playwright test e2e/unit && npx quasar build
```
