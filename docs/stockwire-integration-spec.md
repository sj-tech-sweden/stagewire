# Stagewire ⇄ Stockwire-Rental Integration — Implementation Spec (stockwire-rental side)

This document specifies what the **stockwire-rental** backend must expose/implement so that
**Stagewire** (the stage-plot / patch-sheet tool) can integrate with it: browse its product
catalog, push gear "requirements" onto a rental job, and create/link jobs in both directions
(deeplinking). It is written to be handed to an LLM implementing the stockwire-rental side.

## 1. Goals

1. **Catalog browsing** — Stagewire lists stockwire-rental products (mics, DIs, stands, mixers,
   …) and their accessories/components, and adds them to a Stagewire job as gear items.
2. **Gear push-back** — Stagewire turns its local gear list into **job requirements** on the
   stockwire-rental job (the "request to add" flow).
3. **Mixer suggestion** — Stagewire can suggest a mixer model given a channel list's input/output
   counts. Requires mixer I/O counts to be queryable from the catalog.
4. **Two-way job creation / deeplink** — creating a job in one app can create the matching job in
   the other, and a link/button opens the linked job in the other app.

## 2. Auth model (shared API keys)

- Each side stores the **other side's API base URL + API key** in its own settings.
- On **Stagewire**, the user pastes a stockwire-rental API key (UI at
  `Settings → Stockwire integration`). The key is encrypted at rest.
- **"Stagewire provisions"**: with that key, Stagewire calls stockwire-rental to **register
  itself** as an integration instance (see §3.2). This lets stockwire-rental store Stagewire's
  base URL + a key it can use to call back into Stagewire.
- All inter-service calls use `Authorization: Bearer <key>` (HTTPBearer, already the scheme in
  stockwire-rental's OpenAPI `securitySchemes`).

## 3. Endpoints stockwire-rental must expose

> Verify names against the live OpenAPI (`/openapi.json`). Some already exist; align to them.

### 3.1 Already available (use as-is)

- `GET /api/v1/health/ready`, `GET /api/v1/health/live` — connectivity check (public).
- `GET /api/v1/inventory/products`, `GET /api/v1/public/products`, `GET /api/v1/inventory/products/{product_id}`
  plus `.../{product_id}/accessories` and `.../{product_id}/components` — catalog.
- `GET/POST /api/v1/auth/api-keys`, `DELETE /api/v1/auth/api-keys/{key_id}` — key management
  (use to mint a scoped key for the Stagewire instance if needed).
- `GET /api/v1/jobs`, `POST /api/v1/jobs`, `GET/PUT/DELETE /api/v1/jobs/{job_id}`.

### 3.2 Implement / confirm: integration registration ("Stagewire provisions")

- `PUT /api/v1/settings/integrations` (already exists) must accept an integration object, e.g.:
  ```json
  { "plugin": "stagewire", "enabled": true,
    "base_url": "https://stagewire.example.com", "api_key": "<stagewire_key>" }
  ```
  and persist it (note: do **not** reuse any existing "stockwire" integration namespace — that is
  a different feature; name this one `stagewire`).
- Return the stored instance id so Stagewire can reference it.
- `GET /api/v1/settings/integrations/stockwire/{instance_id}/customers` — extend/replace to return
  the customers available to the linked Stagewire workspace (used by Stagewire to tag a job's
  customer). If a different endpoint is cleaner, expose `GET .../stagewire/{instance_id}/customers`.
- `POST /api/v1/settings/integrations/{plugin}/test` — validate the stored `base_url`/`api_key`
  by calling Stagewire's `GET /api/v1/health/ready` (and ideally an authenticated probe).

### 3.3 Job requirements (the gear push-back)

- Stagewire maps its gear list → **job requirements**. Use stockwire-rental's
  `POST /api/v1/jobs/{job_id}/requirements` (or `/api/v1/jobs/requirements`) rather than any
  `/requests` path (that path does not exist in stockwire-rental).
- Confirm the requirement schema carries at least: product reference (id or SKU), quantity,
  label/notes. Align with Stagewire's `StockwireAdditionItem { asset_type, label, quantity, notes }`.

### 3.4 Mixer I/O data

- Expose, per mixer product, its **input count** and **bus/output count** (and aux/matrix counts
  if available) so Stagewire can suggest a model from a channel list's totals.
- Preferred: a structured field on the product (e.g. `specs.inputs`, `specs.outputs`) returned by
  `GET /inventory/products/{id}` and filterable in the products list. If not present today, add it
  as a product custom field / search facet.

### 3.5 Speaker coverage data

- Stagewire reads optional speaker fields from a product's `specs` object, for the product
  linked to the speaker's output device (`GET /inventory/products/{id}`):
  - `specs.dispersion_h_deg`: horizontal coverage angle, degrees.
  - `specs.throw_m`: throw distance, metres.
- When a product provides either field it overrides the manual value on the speaker.
  Missing fields or an unreachable product fall back to the manual values.

### 3.6 Camera and lens data

- Stagewire reads optional fields from a product's `specs` object, for the product linked to a
  camera device and to a lens device (`GET /inventory/products/{id}`). A camera with an integrated
  lens has both sets of fields on one product.
  - `specs.cam_sensor_width_mm`: sensor width, millimetres (camera products).
  - `specs.cam_max_distance_m`: longest useful distance, metres (optional; camera products).
  - `specs.lens_focal_length_min_mm`: shortest focal length, millimetres (lens, or camera with integrated lens).
  - `specs.lens_focal_length_max_mm`: longest focal length, millimetres. Equal to the minimum for a fixed lens.
- Values are numbers, not strings. Omit a field or send `null` when it is unknown.
- When a product provides a field it overrides the value entered in Stagewire. Missing fields or an
  unreachable product fall back to the manual values.

### 3.7 Projector data (proposed, not yet read by Stagewire)

Stagewire will read these from `specs` on the product linked to a projector device, with the same
precedence rules as §3.6. The names are proposed and can change to match your conventions.

- `specs.proj_throw_ratio_min`: shortest throw ratio, as distance ÷ image width (for example `1.2`).
- `specs.proj_throw_ratio_max`: longest throw ratio. Equal to the minimum for a fixed lens.

Stagewire assumes a 16:9 image. Lens shift is not used yet, so it is not requested.

## 4. Endpoints Stagewire exposes (for the reverse direction)

stockwire-rental will call these (key from §3.2):

- `POST /api/v1/jobs` — create a Stagewire job (mirror of a stockwire-rental job).
- `GET /api/v1/jobs` / `GET /api/v1/jobs/{id}` — look up / verify the linked job.
- `GET /api/v1/health/ready` — liveness for the integration test.
- A deeplink resolver (§5) that, given a token, returns the in-app route to a job.

## 5. Deeplink / job-linking scheme

- A **link token** is an HMAC-signed payload: `{ src: "stagewire"|"stockwire", job_id, ts, nonce }`
  signed with the **shared secret** (derive from the stored API key or a dedicated integration
  secret). Both sides verify with their copy of the secret.
- Opening a deeplink: the target app validates the token, then redirects to the linked job
  (creating it on first open if "create in other platform" is enabled), and stamps
  `ProductionJob.stockwire_job_id` (Stagewire side) / the reciprocal field (stockwire-rental side).
- Never put the raw API key in the token — only the HMAC.

## 6. Data-model mapping

| Concept | Stagewire | stockwire-rental |
| --- | --- | --- |
| Job | `production_jobs` (`stockwire_job_id` FK) | `jobs` |
| Gear line | local gear list / channel patch `stockwire_asset_id` | `jobs/{id}/requirements` (+ `products`) |
| Customer | n/a (or company) | `customers` |
| Mixer | selected per channel list | `products` with `specs.inputs/outputs` |

## 7. Implementation checklist (for the LLM building stockwire-rental side)

- [ ] Add/confirm `PUT /api/v1/settings/integrations` storing a `stagewire` plugin instance
      (unique plugin name; do not collide with existing `stockwire` integration).
- [ ] Add `GET .../stagewire/{instance_id}/customers` (or extend the existing stockwire one).
- [ ] Add `POST .../{plugin}/test` that probes Stagewire `health/ready` + authenticated endpoint.
- [ ] Ensure `POST /api/v1/jobs/{job_id}/requirements` exists and matches Stagewire's addition item.
- [ ] Add mixer I/O counts to product model + list filter (inputs/outputs).
- [ ] Expose the camera, lens and projector `specs` fields in §3.6 and §3.7 on products (values as numbers).
- [ ] Document the signed deeplink token scheme (HMAC) and a resolver endpoint.
- [ ] Add an OpenAPI note + a small integration test that pings a mock Stagewire base URL.

## 8. Notes / open questions for the human

- Is there already a `stockwire` integration plugin in stockwire-rental? If so, the new Stagewire
  link must use a distinct plugin key (e.g. `stagewire`) to avoid clobbering it.
- Which stockwire-rental role/scope should the API key Stagewire receives have (so it can only
  read catalog + write requirements for its own workspace)?
- Is `cam_max_distance_m` the longest useful distance, or a recommended maximum? Stagewire treats it as a hard limit on the coverage drawn.
- Confirm the projector field names in §3.7 or give the names you use, so Stagewire can read them.
- Confirm whether `jobs/{id}/requirements` is per-job and whether it auto-creates the rental
  booking or just records the need.
