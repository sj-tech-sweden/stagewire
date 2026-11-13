// Column layout for the app's data tables: which columns are shown, how wide each one is, and the
// user's own choices (hidden columns, dragged widths) kept per browser, user and table (`tableId`).
// The channel list was first; every table now goes through AdaptiveTable.vue and these helpers.
//
// Everything here is pure (the storage is injected) so the rules are unit-tested without a browser.
//
// Widths are decided in one place so the header and the body cells always agree and the table can use
// `table-layout: fixed`:
//   - a column with `grow: 0` is compact: it always gets its default `width`;
//   - a column with `grow > 0` is flexible: the space left over after the compact columns is shared
//     between the flexible ones by weight (Name takes the most), never below the column's `min`;
//   - when even the minimums do not fit in the container the table is wider than the container and
//     scrolls horizontally, instead of squeezing the inputs into unreadable slivers;
//   - a width the user dragged (an "override") wins, clamped to the column's minimum, and the
//     remaining flexible columns share what is left.

export const MIN_RESIZE_PX = 48;
export const STORAGE_VERSION = 1;

/**
 * Fill in the layout fields a table did not bother to declare, so a table can list just
 * `{name, label, ...}` plus the few numbers that matter. A column named `actions` is the row's
 * buttons and can never be hidden. Defaults suit an ordinary text column.
 */
export function withDefaults(column) {
  const required = column.required ?? column.name === 'actions';
  return {
    min: 80,
    width: 140,
    grow: 1,
    defaultVisible: true,
    ...column,
    required,
  };
}
export const withAllDefaults = (columns) => columns.map(withDefaults);

// Descriptors of the desktop channel table. `required` columns can never be hidden (without a number
// and a name a row cannot be told apart; without actions it cannot be opened or deleted).
export const CHANNEL_COLUMNS = [
  { name: 'number', min: 56, width: 64, grow: 0, required: true, defaultVisible: true },
  // ~16 characters of a channel name plus the input's own padding
  { name: 'name', min: 150, width: 180, grow: 3, required: true, defaultVisible: true },
  // the type select; wireless pack / frequency / group wrap below it inside the cell
  { name: 'input_type', min: 190, width: 220, grow: 1, required: false, defaultVisible: true },
  { name: 'device', min: 150, width: 200, grow: 1.5, required: false, defaultVisible: true },
  { name: 'stand_type', min: 130, width: 170, grow: 0, required: false, defaultVisible: true },
  { name: 'phantom_power', min: 64, width: 64, grow: 0, required: false, defaultVisible: true },
  { name: 'stereo', min: 72, width: 72, grow: 0, required: false, defaultVisible: true },
  // optional, hidden until chosen in the Columns menu
  { name: 'instrument_group', min: 120, width: 140, grow: 0, required: false, defaultVisible: false },
  { name: 'color_code', min: 72, width: 80, grow: 0, required: false, defaultVisible: false },
  { name: 'performer_name', min: 120, width: 160, grow: 1, required: false, defaultVisible: false },
  { name: 'notes', min: 110, width: 160, grow: 1, required: false, defaultVisible: true },
  // the patch summary and the flow button sit side by side
  { name: 'chain', min: 210, width: 260, grow: 2, required: false, defaultVisible: true },
  { name: 'actions', min: 96, width: 96, grow: 0, required: true, defaultVisible: true },
];

const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);

/** The smallest width a column may be dragged to. */
export function minWidthOf(column) {
  return Math.max(MIN_RESIZE_PX, withDefaults(column).min || 0);
}

/** Clamp a user width to the column's minimum (and a sane maximum); non-numbers become null. */
export function clampWidth(column, value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.round(Math.min(Math.max(n, minWidthOf(column)), 1200));
}

/** Names of the columns that are shown: required ones always, the rest as chosen. */
export function visibleColumns(columns, visible) {
  const chosen = new Set(visible || []);
  return withAllDefaults(columns).filter((c) => c.required || chosen.has(c.name));
}

/**
 * Pixel width of every shown column.
 * @returns {{widths: Object<string, number>, total: number, overflow: boolean, names: string[]}}
 */
export function computeWidths(columns, { containerWidth = 0, visible = null, overrides = {} } = {}) {
  const shown = visible ? visibleColumns(columns, visible) : withAllDefaults(columns);
  const widths = {};
  const flexible = [];
  let fixedTotal = 0;
  for (const c of shown) {
    const own = overrides && overrides[c.name] != null ? clampWidth(c, overrides[c.name]) : null;
    if (own != null) {
      widths[c.name] = own;
      fixedTotal += own;
    } else if (!c.grow) {
      widths[c.name] = c.width;
      fixedTotal += c.width;
    } else {
      flexible.push(c);
    }
  }
  // water-filling: share the leftover by weight; a column that would fall below its minimum is pinned
  // at the minimum and the rest are shared again
  let free = Math.max(0, (containerWidth || 0) - fixedTotal);
  let open = [...flexible];
  const pinned = new Set();
  for (let round = 0; round <= flexible.length; round += 1) {
    const weight = open.reduce((sum, c) => sum + c.grow, 0);
    const below = open.filter((c) => (free * c.grow) / weight < c.min);
    if (!below.length) break;
    for (const c of below) {
      widths[c.name] = c.min;
      free -= c.min;
      pinned.add(c.name);
    }
    free = Math.max(0, free);
    open = open.filter((c) => !pinned.has(c.name));
    if (!open.length) break;
  }
  const weight = open.reduce((sum, c) => sum + c.grow, 0);
  for (const c of open) widths[c.name] = Math.floor((free * c.grow) / weight);
  const total = shown.reduce((sum, c) => sum + widths[c.name], 0);
  return {
    widths,
    total,
    // wider than the container: the table scrolls sideways
    overflow: total > (containerWidth || 0),
    names: shown.map((c) => c.name),
  };
}

// --- the stored layout ---------------------------------------------------------------------------

// The channel list was the first table and its layouts are already saved under `sw_channel_cols_v1_*`;
// that key stays, every other table is `sw_table_<tableId>_v1_<userId>`.
export const storageKey = (userId, tableId = 'channels') =>
  tableId === 'channels'
    ? `sw_channel_cols_v1_${userId || 'anon'}`
    : `sw_table_${tableId}_v1_${userId || 'anon'}`;

export function defaultLayout(columns = CHANNEL_COLUMNS) {
  return {
    visible: withAllDefaults(columns)
      .filter((c) => c.defaultVisible)
      .map((c) => c.name),
    widths: {},
  };
}

/**
 * Validate whatever was stored. Unknown column names are dropped, bad numbers ignored, required
 * columns are always visible, and a column that did not exist when the layout was saved (`known`)
 * takes its default visibility, so a column added later appears without the user doing anything.
 */
export function normalizeLayout(raw, columns = CHANNEL_COLUMNS) {
  columns = withAllDefaults(columns);
  const byName = new Map(columns.map((c) => [c.name, c]));
  const base = defaultLayout(columns);
  if (!raw || typeof raw !== 'object' || raw.v !== STORAGE_VERSION) return base;
  const known = new Set(Array.isArray(raw.known) ? raw.known.filter((n) => byName.has(n)) : []);
  const chosen = new Set(Array.isArray(raw.visible) ? raw.visible.filter((n) => byName.has(n)) : []);
  const visible = columns
    .filter((c) => c.required || (known.has(c.name) ? chosen.has(c.name) : c.defaultVisible))
    .map((c) => c.name);
  const widths = {};
  if (raw.widths && typeof raw.widths === 'object') {
    for (const [name, value] of Object.entries(raw.widths)) {
      const column = byName.get(name);
      const px = column && isNumber(value) ? clampWidth(column, value) : null;
      if (px != null) widths[name] = px;
    }
  }
  return { visible, widths };
}

function safeStorage(storage) {
  if (storage) return storage;
  try {
    return globalThis.localStorage || null;
  } catch {
    return null; // blocked storage
  }
}

export function loadLayout(userId, columns = CHANNEL_COLUMNS, storage = null, tableId = 'channels') {
  try {
    const text = safeStorage(storage)?.getItem(storageKey(userId, tableId));
    return normalizeLayout(text ? JSON.parse(text) : null, columns);
  } catch {
    return defaultLayout(columns);
  }
}

export function saveLayout(userId, layout, columns = CHANNEL_COLUMNS, storage = null, tableId = 'channels') {
  try {
    safeStorage(storage)?.setItem(
      storageKey(userId, tableId),
      JSON.stringify({
        v: STORAGE_VERSION,
        known: withAllDefaults(columns).map((c) => c.name),
        visible: layout.visible,
        widths: layout.widths,
      }),
    );
    return true;
  } catch {
    return false; // the layout simply is not remembered
  }
}

export function resetLayout(userId, columns = CHANNEL_COLUMNS, storage = null, tableId = 'channels') {
  try {
    safeStorage(storage)?.removeItem(storageKey(userId, tableId));
  } catch {
    /* nothing to forget */
  }
  return defaultLayout(columns);
}
