# Venues as template jobs

Status: **Design proposal** (approved direction; implementation not started).
Branch context: `feat/venue-geometry`.

## 1. Goal & principles

- A venue's equipment (house lights, sound, video, rigging) should be edited and
  rendered with the **same code** that jobs use — no parallel venue-only models or UI.
- **Keep** the `Venue` entity for geometry + stage shape, and **keep** the
  `venue_power_groups` / `venue_power_outlets` tree (already ratified as sound).
- **Keep** clone-on-assign: assigning a venue to a job clones its rig into the job
  as a private copy; later venue edits propagate only on demand.
- Introduce a single **context discriminator** — `{ scope: 'job' | 'venue', id }` —
  that every job-domain service/UI accepts, instead of hard-coding `job_id`.

## 2. Decisions (ratified)

- **Reports**: a venue should be able to generate reports from its base rig. Phase 3
  (venue base-rig reports) is in scope.
- **Cloned jobs**: when a job is created from a venue, **clone the referenced library**
  (fixture types/modes, Wireless Workbench files) into the job scope and remap
  references (option (a) below). This keeps strict per-job ownership and matches the
  existing clone semantics for the graph.

## 3. What is already unified (no work needed)

The surviving schema is small (15 tables) and most gear is already venue-capable:

- `graph_devices`, `graph_connection_edges` already carry `(job_id | venue_id)`. The
  "Venue Standard Base Rig" is literally graph rows with `venue_id` set and `job_id`
  null, cloned by `clone_base_rig_to_job`.
- `VenueBaseRigPage` already reuses `WorkspaceCanvas` + `MultiDomainPatchDrawer` + the
  shared gear catalog, so placing/connecting audio/video/lighting/rigging devices on a
  venue already works.
- `stockwire_requirement_links` already has `venue_id`.
- Legacy per-domain tables (`video_*`, `rigging_*`, `audio_devices`, `dmx_*`) were
  dropped in earlier migrations; everything is now `graph_devices` keyed by `domain`.
  There is **no duplicated gear schema to merge**.

## 4. What actually needs parameterizing (the real "rebuild" pain)

Only the *supporting/library* tables are job-only:

| Table | Current | Change |
|---|---|---|
| `fixture_types` / `fixture_modes` (lighting library) | `FixtureType` has a `venue_id` column (unused); `FixtureMode` carries `venue_id` via the `FixtureType` join; **service queries only `job_id`** | Make the `lighting` service + router accept a context and query by `venue_id` when venue-scoped. **No schema change** — the column already exists. |
| `wwb_show_files` (Wireless Workbench) | `job_id` required, no `venue_id` | **Add** nullable `venue_id` (FK→`venues`, index); make `job_id` nullable; parameterize the audio WWB service/router by context. Small migration. |
| Reports (`power_context` / `graph_context`, `report_templates`) | generated from a `job_id` graph | Parameterize the report context by scope so a venue can emit reports from its base rig. In scope (Phase 3). |

So the data-model delta is **one new column** (`wwb_show_files.venue_id`); the rest is
service/router/UI parameterization.

## 5. Service / API pattern

- Add a tiny `JobOrVenue` value (scope + id). Job-domain services (`lighting`,
  `audio.wwb`, reports) take it instead of a bare `job_id`.
- Keep **explicit venue-prefixed routes** for clarity (the codebase already has
  `/venues/{id}/graph` and `/venues/{id}/power-load`). Mirror that with
  `/venues/{id}/fixture-types`, `/venues/{id}/wwb`, … rather than overloading job
  routes with an optional `venue_id`. This avoids accidental cross-scope data leaks
  and keeps auth/ownership checks obvious.
- Existing job endpoints are untouched → no breakage, no client migration for jobs.

## 6. Clone-on-assign (ratified: clone the library)

When `clone_base_rig_to_job` copies the venue's graph devices into a job, a lighting
device may reference a venue-owned `FixtureType` (its `venue_id` set, not the job's).
A job-scoped `list_types(job_id)` would then miss it.

**Approach (a), chosen:** during clone, also clone referenced `FixtureType` /
`FixtureMode` (and WWB files) into the job scope and remap the device's
`fixture_type_id` (and WWB `list_node_id` references). This keeps strict per-job
ownership and is consistent with the existing graph-clone behaviour.

## 7. Frontend

- `VenueBaseRigPage` already drives the same canvas + patch drawer via the
  `venueGraph` store, so most editing is unified already.
- Gaps to parameterize by context: the **lighting fixture-type picker** (currently
  job-scoped) and the **WWB UI** (job-scoped). Thread the `context` into those
  components; no new editor.
- Retire any venue-specific duplicate UI discovered during the audit (none expected
  beyond the two pickers above, since gear editing is shared).

## 8. Migration path (additive, safe)

- New migration: `wwb_show_files` add `venue_id` (Uuid, nullable, FK→`venues`, index);
  make `job_id` nullable.
- `fixture_types.venue_id` / `fixture_modes.venue_id` already exist (the missing-column
  bug was fixed in commit `4037d13`); they simply become *used*.
- No backfill of gear needed — gear already lives in `graph_devices` with `venue_id`.
- Job endpoints untouched; existing jobs keep working.

## 9. Phasing

- **Phase 0** — agree on the context pattern + route shape (this document).
- **Phase 1** — Lighting fixture library: venue support in service/router + frontend
  picker. Biggest visible "everything works together" win; no schema change.
- **Phase 2** — WWB show files: migration + service/router + UI.
- **Phase 3** — Venue base-rig reports (in scope): parameterize the report context so
  a venue can emit reports from its base rig.
- **Phase 4** — Audit for any residual venue-specific UI and retire it; confirm a
  single code path serves both scopes.

## 10. Open questions

- Any venue-specific UI already known that should be treated as the "duplicate to
  retire" beyond the lighting picker + WWB UI? (Default assumption: none.)
- Exact route shape for venue-scoped domain endpoints (e.g. `/venues/{id}/fixture-types`
  vs a unified `/context/{scope}/{id}/fixture-types`). This proposal favours explicit
  venue-prefixed routes for clarity and safety.
