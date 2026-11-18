# Digital stageboxes in the soft patch — implementation plan

## 1. Goal

Make the console **soft patch** show only console-relevant sockets — the mixer's own
sockets plus the sockets of stageboxes that are wired into the rig — and stop offering
every device's inputs (e.g. a **camera's XLR in**) as a soft-patch target for a mic
channel.

Support, from the start, **Allen & Heath dSnake**, but keep the model protocol-agnostic
(Dante / AES50 / AVB / MADI). Support three device origins:

1. **Stockwire-spec** devices (imported from the catalog),
2. **Manual-port** devices (created via the add-device dialog, ports typed by hand),
3. **Fully-manual** devices (no Stockwire link at all).

This builds on PR #137 (`6c39d17`), which made `job_hardware()` return *all* physical
gear so imported/manual stageboxes appear. That was too broad (cameras included); this
plan scopes the soft patch to the **console input domain** while keeping #137's intent
(imported stageboxes still appear — provided they are stageboxes and are wired in).

The plan also covers the **stockwire-rental** side (§8): that sibling app owns the gear
catalog/specs stagewire imports, so digital stageboxes and mixers must be fully definable
there (structured digital transport + channel counts, a shared protocol vocabulary) before
catalog imports carry the data this plan relies on.

## 2. Resolved scope rule (the core decision)

`GET /soft-patch` (`api/app/domains/audio/console_router.py:460`) returns sockets for the
**console input domain**, computed as follows:

- Find the mixer device node for the channel list: the `digital_stagebox`/`analog_stagebox`
  is irrelevant here — the **mixer** is the node whose `sound_list_id === list_id`.
- **If a mixer exists** for the list → domain = `[mixer] + feedingStageboxes(mixer, devices, edges)`.
  `feedingStageboxes` = stageboxes reachable from the mixer over `audio`/`data` edges,
  walking *through* network gear (switch / router / computer), never passing through
  another mixer or a virtual node. (Mirror of the existing frontend walk in
  `web/src/utils/workspace.js:338`.)
- **If no mixer exists** for the list → domain = every `digital_stagebox` / `analog_stagebox`
  that has **at least one `audio`/`data` edge** (i.e. it is wired into the rig).
- `audio_sockets()` (`api/app/domains/audio/console.py:785`) is then computed over **only**
  this domain (it already skips logical/plot nodes as a belt-and-braces guard).

Why this hybrid: when a console is set, you only care about stageboxes feeding *that*
console; when no console is set yet, you still want to see the stageboxes you have wired
up so you can plan patches.

This fixes the camera bug (a camera is neither a mixer nor a stagebox) and enforces
"connected stageboxes only".

### Consequences to be aware of
- A channel already patched to a device *outside* the new domain (e.g. a camera) will now
  report its socket as **orphaned** in the soft patch (the socket is no longer offered).
  This is the intended behaviour change.
- **Patching to any device stays possible** — only the *offered socket list* (`GET /soft-patch`)
  is scoped. `PUT /channels/{id}/soft-patch`, the bulk endpoint and the auto-patch all accept
  *any* target device and do **not** validate the input domain. So a channel can still be
  patched to a snake/camera/etc.; such a device simply does not appear as a selectable socket
  in the soft-patch UI. (Per explicit product decision: "it should still be possible to patch
  those, but not in the softpatch.")
- **The `mixerInputChoices` Inputs-tab dropdown has been removed.** It was a separate,
  mixer-anchored "which physical console input" annotation (`channel.attributes.mixer_input`)
  duplicating what the soft patch already expresses via `dsp_source`. The soft patch is now the
  single source of truth for "where is this channel physically fed from"; the dropdown and its
  `mixer_input` attribute writes are gone (existing `mixer_input` values are inert and no longer
  shown). See §7.

## 3. Hard prerequisite: `deviceTypeFromCategory` must classify stageboxes (P0)

`web/src/utils/workspace.js:1450` `deviceTypeFromCategory` currently has **no stagebox
rule** and returns `'other'` for any stagebox / IO / split product. That makes an imported
stagebox `kind = 'other'`, which `isStagebox` (both frontend `workspace.js:326` and the
backend helper we add in §4.1) will **not** match — so the domain filter would
*silently exclude every imported stagebox*. Fixing this is mandatory before §4.1 can work
for catalog imports, and it also removes the spurious single-XLR-out + `power_inlet:'none'`
passive-gear fallback in `fillFormFromSpecs` (`workspace.js:1375`).

## 4. Changes

### 4.1 Backend — soft-patch domain filter (Phase A)
- `api/app/domains/audio/console.py`: add
  - `is_mixer_device(d)` / `is_stagebox(d)` (mirror `workspace.js:326-331`),
  - `feedingStageboxes(mixer, devices, edges)` — a Python port of the frontend walk
    (`workspace.js:338`): start from `mixer` + the mixer's list channels, walk `audio`/`data`
    edges, collect stageboxes, never pass through another mixer or a virtual node,
  - `console_input_devices(devices, edges, mixer)` implementing the §2 hybrid rule.
- `api/app/domains/audio/console_router.py` `get_soft_patch` (`:460`): fetch the job's edges
  (reuse the graph edge query, e.g. `graph/router.py:102` `_all_edges`), find the list's
  mixer node, compute the domain, and pass **only** that device list to `audio_sockets`.
- Leave `job_hardware()` (`console_service.py:324`) broad (other console endpoints such as
  direct-outs / output chains may still want all gear); scope **only** the soft patch here.
- `audio_sockets()` is unchanged.

### 4.2 Frontend — `deviceTypeFromCategory` stagebox rule (Phase A, P0)
- `web/src/utils/workspace.js:1450`: add a rule mapping a Stockwire category containing
  `stagebox` / `stage box` / `io` / `snake` / `multicore` to
  - `digital_stagebox` when the name/category path also contains `digital|dante|dsnake|d-snake|avb|madi`, else
  - `analog_stagebox`.
  Reuse the exact keyword set already in `guessChainDevice` (`workspace.js:1079-1081`).

### 4.3 Connectors — `dsnake` + bidirectional + multiple (Phase B)
- `web/src/utils/workspace.js` `CONNECTOR_CHOICES` (`:931`): add `dsnake` (it is **missing**
  today; `dante`/`aes50`/`madi`/`avb`/`ethernet` are already present). Keep labels.
- `CONNECTOR_PRESETS` (`:955`): add a `dsnake` `both ×1` preset (like `dante`/`aes50` at
  `:959-960`), and add `avb`/`madi` `both ×1` presets for symmetry. Keep them **bidirectional**
  (`direction: 'both'`).
- The port model already holds a **list** of connector groups and the connector editor adds
  several, so a device with *both* dSnake and Dante (e.g. a GX4816) is already representable
  once the presets exist. **No schema change.**
- Optional: add `aes50`/`avb`/`madi`/`dsnake` to `NETWORK_PROTOCOLS` in
  `web/src/components/DeviceInspector.vue:1015` (currently only `dante`/`ndi`/`artnet`/`sacn`).

### 4.4 Stockwire — mixer expansion ports into device specs (Phase C, P2)
- `api/app/domains/stockwire/router.py` `get_device_specs` (`:327`): also read
  `specs.mixer.expansion_ports` and emit connector groups — an `in-<protocol>` group with
  `count = max_channels_in` and an `out-<protocol>` group with `count = max_channels_out`,
  `connector = protocol`. So an imported dSnake/Dante mixer actually carries sockets.
  (`parse_mixer_specs` / `ExpansionPort` already accept `dsnake` as a protocol; the device
  import path `MixerDialog` → `fillFormFromSpecs` already routes through this endpoint.)

### 4.5 Easy-link UX (Phase D, later)
- Phase D is **manual now**: the existing stage-plot connect UX (draw an edge) already covers
  point-to-point (AES50/dSnake: stagebox ↔ mixer) and Dante networks (stagebox ↔ switch ↔
  mixer). The §2 walk picks these up automatically.
- Later convenience: a one-click "add to Dante network" that auto-inserts a network/switch
  node and links both ends. **Out of scope for the initial implementation.**

### 4.6 Later: separate Dante / network patch surface (Phase E, distinct from the mixer soft patch)

The §2 soft patch is **mixer-centric**: it answers "which physical sockets feed this
console's strips." Dante (and other switched-network transports like AVB/MADI-over-IP) is
**not** mixer-bound — a Dante stagebox, I/O rack, or even a laptop can exchange flows with
*any* other Dante node on the network, independent of whether a console is present or which
console owns the local soft patch. Cramming that into the mixer soft patch would conflate two
different mental models (console input patching vs. network routing). So Phase E delivers a
**separate** patch surface:

- A "Dante / network patch" view (separate tab/panel from the console soft patch) that lists
  every device carrying a Dante/network digital connector (`dsnake`/`dante`/`aes50`/`avb`/
  `madi` over a `data`/network edge) and lets you route a **transmitter flow → receiver flow**
  device-to-device, not just into the mixer.
- It reuses the existing `feedingStageboxes`-style network walk (`workspace.js:338`) to
  discover the Dante domain (stageboxes/IO reachable through switches/routers/computers over
  `audio`/`data` edges), but treats the set as a peer mesh rather than a mixer-anchored tree.
- Paired with Phase D's "add to Dante network" convenience, this becomes the place to draw
  non-point-to-point links (stagebox → switch → multiple receivers) that the mixer soft patch
  deliberately ignores.
- **Scope boundary:** the mixer soft patch (§2) stays the single source of truth for *console
  input* patching; the Dante/network patch (Phase E) is the single source of truth for
  *network flow* routing. They share device/port data but never blur which one a socket belongs
  to. A Dante flow that ultimately lands on a console input still shows up in §2 as that
  console's input; Phase E records the *network* leg separately.

## 5. Device origins (all supported once §4.1–4.3 land)
- **Stockwire-spec**: import path exists; §4.2 + §4.4 make the type/ports correct.
- **Manual-port**: `web/src/components/DeviceDialog.vue` already lets you add ports by hand.
- **Fully-manual (no Stockwire)**: `DeviceDialog` already creates devices with no
  `stockwire_product_id`; just ensure `digital_stagebox` is a selectable type (it is, in
  `DEVICE_TYPES`) and the digital presets are available.

## 6. Tests

### 6.1 Tests to update (behaviour changed)
- `api/tests/test_console.py:551` `test_catalog_imported_device_is_a_soft_patch_target`: it
  creates a stagebox with **no mixer and no connection**. Under §2 it would no longer appear.
  Update it to wire the stagebox in (add a mixer device node + an `audio` edge, or any
  `audio`/`data` edge) so it stays within the domain — while preserving the "no `legacy_ref`"
  intent of #137.
- Review `api/tests/test_console.py` `test_soft_patch_and_direct_outs_use_any_device_…`: if it
  targets a non-stagebox/non-mixer device, switch the target to a connected stagebox/mixer.

### 6.2 New tests (acceptance)
- **Camera exclusion**: a device of type `camera` with an XLR in is **not** present in
  `GET /soft-patch` sockets (type exclusion).
- **Connected stagebox with mixer**: a stagebox reachable from the list's mixer appears in
  sockets (both `in` and `out`); an unconnected stagebox in the same job does **not**.
- **No mixer present**: a stagebox with an `audio`/`data` edge appears in sockets; an
  isolated (no-edge) stagebox does **not**.
- **`deviceTypeFromCategory`**: a Stockwire `stagebox` category maps to `digital_stagebox`
  (when the name/path carries a digital keyword) or `analog_stagebox`, not `'other'`.
- **`dsnake` connector**: a device with a `dsnake` `both` group yields `in-dsnake` /
  `out-dsnake` sockets that are labelled (exists as a unit test at
  `web/e2e/unit/workspace.spec.ts:833,841` — extend/confirm).
- **Imported mixer expansion**: importing a mixer product whose `specs.mixer.expansion_ports`
  has a `dsnake` entry produces dSnake in/out port groups on the device.

### 6.3 E2E
- When practical, a Playwright spec that opens the soft patch and asserts only mixer +
  connected-stagebox sockets are offered (camera/mic/DI absent).

## 7. Out of scope / follow-ups
- One-click "add to Dante network" auto node (§4.5).
- Treating wireless racks / audio interfaces with digital outs as **direct** soft-patch
  targets. Current decision: mixer + stageboxes only; other digital sources are modelled as
  upstream chain devices.
- Adding `dsnake` to the backend connector doc list (`device_specs.py:10`) and
  `docs/stockwire-integration-spec.md` so Stockwire-side data stays consistent.

## 8. stockwire-rental side work (define digital stageboxes & mixers at the source)

`stagewire` imports gear from `stockwire-rental` via `GET /integrations/stagewire/.../products/{id}/device-specs`
(rental `backend/app/domain/inventory/public_router.py:419`). That endpoint reads the product's free-form
`Product.specs` JSON blob (`backend/.../inventory/models.py:92`) and emits `connectors`, `power_inlet`,
`inputs`, `outputs`, and `mixer`. For the soft-patch plan to work on catalog imports, the rental side must be
able to **fully define** a digital stagebox and a digital mixer.

### 8.1 What already exists (mostly the mixer side)

- **`Product.specs`** is a single free-form JSON column — no DB migration needed to add new nested blocks.
- **Digital mixer**: `backend/.../inventory/mixer_spec.py` already defines a typed `MixerSpec` with a nested
  `expansion_ports: list[ExpansionPort]`; each `ExpansionPort` carries `protocol` (`dsnake`/`dante`/`aes50`/
  `avb`/`madi`/`io_card`/…), `max_channels_in`, `max_channels_out`, `slots`, `max_channels`. There is a lenient
  `parse_mixer_spec` / `normalize_mixer_spec`, a frontend editor in `ProductDialog.vue` (the `mixer` spec group),
  and the export **already emits** `specs.mixer` via `_normalize_stagewire_mixer` (`:325`). `dsnake` is already in
  the rental frontend `MIXER_EXPANSION_PROTOCOLS` (`frontend/.../productSpecs.js:482`).
- **Flat stagebox counts**: `PRODUCT_SPEC_GROUPS` has a `stagebox` group (`productSpecs.js:135`) with only
  `sb_inputs` / `sb_outputs` / `sb_aux` integer fields. There is **no** structured digital-I/O analogue to
  `specs.mixer`, and no notion of transport protocol or in/out split.

### 8.2 The gap: digital stageboxes

A digital stagebox (A&H AR2412 / AB168 / DX168 / GX4816, a Dante AES50/AVB/MADI box) cannot today be defined
with its real digital transport + channel counts. The closest representation is the generic `connectors` field
(`{connector, direction, count, signal?}`) which **can** carry e.g. `{connector: 'dante', direction: 'both',
count: 48}`, but:

1. **`dsnake` is missing from `COMMON_CONNECTOR_OPTIONS`** (`productSpecs.js:20`) — the connector dropdown for
   the generic editor. So a stagebox's dSnake transport can't be picked from the menu (only `dante`/`aes50`/
   `madi`/`avb`/`ethernet` are listed). The mixer expansion dropdown *does* include `dsnake`; the inconsistency
   must be closed.
2. **No in/out split** — `connectors` is just a count with a single `direction` (`both`). A stagebox with
   `24 dSnake in / 12 dSnake out` can't be expressed faithfully (the stagewire digital link is bidirectional
   "both", but the *stagebox's own* port inventory benefits from knowing in vs out).
3. **The export doesn't emit a `stagebox` digital-I/O block** — `get_stagewire_device_specs` (`:419`) returns
   `connectors/inputs/outputs/mixer` only. Even if we add a structured `specs.stagebox`, it won't reach stagewire
   until the export is taught about it.
4. **Cross-repo consumer** — stagewire's `stockwire/router.py:327` `get_device_specs` does **not** yet read
   `specs.mixer.expansion_ports` (see §4.4), so the mixer's exported expansion ports are currently dropped on
   import too. (The rental side emits them; the gap is on the stagewire side.)

### 8.3 Deliverables (rental side)

- **R1 — Connector vocabulary (P0 for rental):** add `dsnake` (and, for symmetry, `avb`/`madi`) to
  `COMMON_CONNECTOR_OPTIONS` (`productSpecs.js:20`) and to any backend direction/signal vocabulary that needs it,
  so digital stagebox transports are selectable. Backend connector normalization (`_normalize_stagewire_connector_groups`,
  `public_router.py:252`) accepts any connector name already, but should **preserve a `protocol` field** if the
  stored entry carries one, rather than inferring protocol solely from the connector-name string.
- **R2 — Structured `specs.stagebox` model (the real work):** add a `StageboxSpec` analogue of `MixerSpec` —
  e.g. `backend/.../inventory/stagebox_spec.py` with `digital_io: list[StageboxDigitalPort]` where each port has
  `protocol` (one of the shared digital-protocol vocabulary) plus `channels_in` / `channels_out` (keep flat
  `sb_inputs`/`sb_outputs` for analog stageboxes). Provide lenient `parse_stagebox_spec` / `normalize_stagebox_spec`.
  Add a frontend editor in `ProductDialog.vue` (reuse the mixer `expansion_ports` editor pattern at lines
  ~664–720) bound to a new `stagebox` group field (e.g. `digital_io`), and a `STAGEWIRE_STAGEBOX_PROTOCOLS` list
  mirroring `MIXER_EXPANSION_PROTOCOLS`.
- **R3 — Export:** have `get_stagewire_device_specs` (`:419`) also emit a `stagebox` block (`normalize_stagebox_spec`),
  and keep `mixer.expansion_ports` flowing (already emitted). This is the payload stagewire's §4.4 must consume.
- **R4 — Shared protocol vocabulary:** keep the controlled digital-protocol set **identical** across both repos
  (`{dsnake, dante, aes50, avb, madi}` plus `io_card`/`option_card`/`waves`/`other` for mixer cards) so import
  mapping is stable. Consider a single source of truth / a documented constant on each side and a test asserting
  the two lists match.
- **R5 — Tests:** rental unit tests for `parse_stagebox_spec` (digital in/out, missing fields, malformed → None);
  a `test_public_router.py` case asserting `get_stagewire_device_specs` includes the `stagebox` digital-I/O block;
  a frontend component test for the stagebox digital-I/O editor.

### 8.4 Follow-ups (rental)

- Expose a machine-readable `device_class` hint (digital_stagebox / analog_stagebox / mixer) on the product so
  stagewire's `deviceTypeFromCategory` (§4.2) can rely on it instead of keyword-sniffing the name.
- Surface digital stagebox availability in the rental catalog search (already done for mixers via
  `router.py:976` `mixer_architecture` / `min_bus_slots` filters — add a `digital_stagebox` protocol filter).

## 9. Phasing & status

- [x] **Phase A** — backend domain filter (§4.1) + `deviceTypeFromCategory` stagebox rule (§4.2)
      + tests (§6.1, §6.2 camera/connected/mapper cases). *Delivers "connected stageboxes, no
      cameras" — the foundation everything else needs.*
- [x] **Phase B** — `dsnake` (+`avb`/`madi`) connector presets, bidirectional, multiple (§4.3)
      + dsnake test.
- [ ] **Phase C** — Stockwire mixer expansion ports into device specs (§4.4) + imported-mixer test.
- [ ] **Phase D** — easy-link / Dante convenience (§4.5, later).
- [ ] **Phase E** — separate Dante / network patch surface, distinct from the mixer soft patch
      (§4.6, later).

### stockwire-rental phases (§8)

- [ ] **Phase R1** — `dsnake` (+`avb`/`madi`) into `COMMON_CONNECTOR_OPTIONS`; preserve `protocol`
      on connector export (§8.3 R1).
- [ ] **Phase R2** — structured `specs.stagebox` model (`StageboxSpec` + `StageboxDigitalPort`),
      frontend editor, shared `STAGEWIRE_STAGEBOX_PROTOCOLS` (§8.3 R2).
- [ ] **Phase R3** — emit `stagebox` (digital I/O) from `get_stagewire_device_specs` (§8.3 R3).
- [ ] **Phase R4** — keep the digital-protocol vocabulary identical across both repos; add a
      matching-vocabulary test (§8.3 R4).
- [ ] **Phase R5** — rental unit + frontend tests for the stagebox digital-I/O model/editor (§8.3 R5).

## 10. Acceptance criteria (definition of done)
1. A camera / mic / DI / wireless rack never appears as a soft-patch socket target.
2. With a mixer set, only mixer sockets + stageboxes reachable from that mixer are offered.
3. Without a mixer, every stagebox that has an `audio`/`data` edge is offered; isolated
   stageboxes are not.
4. `digital_stagebox` / `analog_stagebox` are correctly typed on import (no `'other'`,
   no spurious XLR-out / `power_inlet:'none'`).
5. `dsnake` is a labelled, bidirectional connector; a device can carry more than one digital
   connector (e.g. dSnake + Dante).
6. An imported dSnake/Dante mixer exposes its digital sockets.
7. All of §6's tests pass; linters (`ruff`, ESLint) clean.
8. A rental **digital stagebox** product can be fully defined: digital transport protocol +
   in/out channel counts, and that structured data is exported via `device-specs` and imported
   by stagewire (§8.2–§8.3).
9. The controlled digital-protocol vocabulary (`dsnake`/`dante`/`aes50`/`avb`/`madi`) is
   identical on both repos (§8.3 R4).
10. Dante / network flows are patched in a **separate** surface from the mixer soft patch
    (Phase E, §4.6): console input patching and network flow routing never blur.
