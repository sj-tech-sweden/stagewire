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
  // NetBox sync events (IP assigned/changed/conflict) update only the device's
  // NetBox attribute bag; the device entity itself is unchanged so we merge in
  // place rather than replacing it. `netbox_url`/`netbox_device_id` arrive on a
  // successful assignment so the inspector can link back out to NetBox.
  if (type === 'graph.device.netbox') {
    const p = payload || {};
    return {
      ...state,
      devices: state.devices.map((d) => {
        if (d.id !== p.device_id) return d;
        const attributes = {
          ...(d.attributes || {}),
          netbox_sync_status: p.status,
        };
        if (p.ip) attributes.network_ip = p.ip;
        if (p.netbox_url) attributes.netbox_url = p.netbox_url;
        if (p.netbox_device_id) attributes.netbox_device_id = p.netbox_device_id;
        return { ...d, attributes };
      }),
    };
  }
  return state;
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// `attributes` is sent as a partial object that the server merges key by key, so two edits to
// different attribute keys (a wireless pack and then its frequency) do not conflict even though the
// whole `attributes` object changed in between. A key both sides changed to different values is a
// real conflict and still falls back to the whole-field conflict below.
function attributesDisjoint(field, mine, base, theirs) {
  if (field !== 'attributes' || !mine || typeof mine !== 'object') return false;
  return Object.entries(mine).every(
    ([key, value]) =>
      same(base?.attributes?.[key], theirs?.attributes?.[key]) || same(value, theirs?.attributes?.[key]),
  );
}

// base: row the user started editing, mine: the fields they changed,
// theirs: the row the server now has. Fields only one side touched merge
// cleanly; fields both sides changed to different values are conflicts.
export function threeWayMerge(base, mine, theirs) {
  const merged = {};
  const conflicts = [];
  for (const [field, value] of Object.entries(mine)) {
    if (IGNORED_FIELDS.has(field)) continue;
    const theirsChanged = !same(base?.[field], theirs?.[field]);
    if (!theirsChanged || same(value, theirs?.[field]) || attributesDisjoint(field, value, base, theirs)) {
      merged[field] = value;
    } else {
      conflicts.push({ field, base: base?.[field], mine: value, theirs: theirs?.[field] });
    }
  }
  return { merged, conflicts };
}

export const isRevisionConflict = (error) =>
  error?.response?.status === 409 && error.response?.data?.detail?.code === 'revision_conflict';
