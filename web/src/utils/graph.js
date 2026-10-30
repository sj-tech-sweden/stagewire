const IGNORED_FIELDS = new Set(['revision', 'id', 'job_id', 'created_at']);

export function upsertVersioned(rows, incoming) {
  const idx = rows.findIndex((row) => row.id === incoming.id);
  if (idx === -1) return [...rows, incoming];
  if (incoming.revision < rows[idx].revision) return rows;
  const next = rows.slice();
  next[idx] = incoming;
  return next;
}

export function applyGraphEvent(state, event) {
  const { type, payload } = event;
  if (type === 'graph.device.upsert') {
    return { ...state, devices: upsertVersioned(state.devices, payload) };
  }
  if (type === 'graph.device.delete') {
    const gone = new Set(payload.edge_ids || []);
    return {
      devices: state.devices.filter((d) => d.id !== payload.id),
      edges: state.edges.filter((e) => !gone.has(e.id)),
    };
  }
  if (type === 'graph.edge.upsert') {
    return { ...state, edges: upsertVersioned(state.edges, payload) };
  }
  if (type === 'graph.edge.delete') {
    return { ...state, edges: state.edges.filter((e) => e.id !== payload.id) };
  }
  return state;
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// base: row the user started editing, mine: the fields they changed,
// theirs: the row the server now has. Fields only one side touched merge
// cleanly; fields both sides changed to different values are conflicts.
export function threeWayMerge(base, mine, theirs) {
  const merged = {};
  const conflicts = [];
  for (const [field, value] of Object.entries(mine)) {
    if (IGNORED_FIELDS.has(field)) continue;
    const theirsChanged = !same(base?.[field], theirs?.[field]);
    if (!theirsChanged || same(value, theirs?.[field])) {
      merged[field] = value;
    } else {
      conflicts.push({ field, base: base?.[field], mine: value, theirs: theirs?.[field] });
    }
  }
  return { merged, conflicts };
}

export function placeUnplaced(devices, { originX = 100, originY = 100, step = 120, perRow = 6 }) {
  let slot = 0;
  return devices.map((device) => {
    if (device.canvas_x_cm != null && device.canvas_y_cm != null) return device;
    const placed = {
      ...device,
      canvas_x_cm: originX + (slot % perRow) * step,
      canvas_y_cm: originY + Math.floor(slot / perRow) * step,
    };
    slot += 1;
    return placed;
  });
}

export const isRevisionConflict = (error) =>
  error?.response?.status === 409 && error.response?.data?.detail?.code === 'revision_conflict';
