// Cables run between consecutive linked devices in each signal chain. They are
// derived from the chains; only routing, visibility and length settings are stored
// on the job (cable_plan). A cable is keyed by its downstream patch point id, so a
// stored route survives changes elsewhere in the plan.

export const DEFAULT_CABLE_SETTINGS = {
  slack_pct: 10,
  slack_m: 1,
  standard_lengths_m: [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50],
};

export function emptyCablePlan(plan) {
  return {
    cableways: plan?.cableways || [],
    routes: plan?.routes || {},
    settings: { ...DEFAULT_CABLE_SETTINGS, ...(plan?.settings || {}) },
  };
}

function orderedPoints(points) {
  return (points || []).slice().sort((a, b) => (a.position || 0) - (b.position || 0));
}

// Stage elements that start a channel's chain: its microphones/DIs, or else its
// performers when there is no mic or DI.
export function sourceElementsFor(channelId, elements) {
  const linked = (elements || []).filter((e) => e.linked_channel_id === channelId);
  const mics = linked.filter((e) => e.element_type === 'microphone' || e.element_type === 'di');
  return mics.length ? mics : linked.filter((e) => e.element_type === 'performer');
}

const SPEAKER_TYPES = new Set(['speaker', 'speaker_main', 'speaker_sub', 'speaker_delay', 'monitor']);

export function deriveCables(lists, elements) {
  const cables = [];
  for (const list of lists || []) {
    for (const ch of list.channels || []) {
      const label = `Ch ${ch.channel_number}${ch.source_label ? ` ${ch.source_label}` : ''}`;
      const pts = orderedPoints(ch.patch_points).filter((p) => p.device_id);
      if (pts.length) {
        for (const el of sourceElementsFor(ch.id, elements)) {
          cables.push({
            key: `src:${el.id}`,
            kind: 'source',
            label,
            channelId: ch.id,
            fromElementId: el.id,
            fromPointId: null,
            fromDeviceId: null,
            toDeviceId: pts[0].device_id,
            toPointId: pts[0].id,
            connector: pts[0].connector || '',
          });
        }
      }
      for (let i = 1; i < pts.length; i++) {
        const from = pts[i - 1];
        const to = pts[i];
        if (from.device_id === to.device_id) continue;
        cables.push({
          key: to.id,
          kind: 'link',
          label,
          channelId: ch.id,
          fromElementId: null,
          fromPointId: from.id,
          fromDeviceId: from.device_id,
          toDeviceId: to.device_id,
          toPointId: to.id,
          connector: to.connector || '',
        });
      }
    }
    for (const out of list.outputs || []) {
      const pts = orderedPoints(out.points).filter((p) => p.device_id);
      const byId = new Map(pts.map((p) => [p.id, p]));
      for (let i = 0; i < pts.length; i++) {
        const to = pts[i];
        const parent = to.parent_id ? byId.get(to.parent_id) : i > 0 ? pts[i - 1] : null;
        if (!parent || parent.device_id === to.device_id) continue;
        cables.push({
          key: to.id,
          kind: 'link',
          label: out.name,
          channelId: out.id,
          fromElementId: null,
          fromPointId: parent.id,
          fromDeviceId: parent.device_id,
          toDeviceId: to.device_id,
          toPointId: to.id,
          connector: to.connector || '',
        });
      }
    }
  }
  const outputPoints = new Map();
  for (const list of lists || []) {
    for (const out of list.outputs || []) {
      for (const pt of out.points || []) outputPoints.set(pt.id, { pt, out });
    }
  }
  for (const el of elements || []) {
    if (!SPEAKER_TYPES.has(el.element_type) || !el.linked_output_point_id) continue;
    const hit = outputPoints.get(el.linked_output_point_id);
    if (!hit || !hit.pt.device_id) continue;
    cables.push({
      key: `spk:${el.id}`,
      kind: 'speaker',
      label: hit.out.name,
      channelId: hit.out.id,
      fromElementId: null,
      fromPointId: hit.pt.id,
      fromDeviceId: hit.pt.device_id,
      toDeviceId: null,
      toElementId: el.id,
      toPointId: null,
      connector: hit.pt.connector || '',
    });
  }
  return cables;
}

function dist(a, b) {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function pathLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += dist(points[i - 1], points[i]);
  return total;
}

function projectOnSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return { point: a, t: 0 };
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
  return { point: [a[0] + t * dx, a[1] + t * dy], t };
}

// Shortest path from `from` to `to` that follows the cableways. Each end is joined
// to the nearest point on a cableway, then Dijkstra runs over the cableway graph.
function autoRoute(from, to, cableways) {
  const lines = (cableways || []).map((c) => c.points || []).filter((p) => p.length >= 2);
  if (!lines.length) return null;

  const pos = new Map();
  const adj = new Map();
  const link = (a, b, w) => {
    if (!adj.has(a)) adj.set(a, []);
    if (!adj.has(b)) adj.set(b, []);
    adj.get(a).push({ to: b, w });
    adj.get(b).push({ to: a, w });
  };
  lines.forEach((line, i) => {
    line.forEach((p, j) => {
      pos.set(`v${i}_${j}`, p);
      if (j > 0) link(`v${i}_${j - 1}`, `v${i}_${j}`, dist(line[j - 1], p));
    });
  });

  const nearest = (p) => {
    let best = null;
    lines.forEach((line, i) => {
      for (let j = 0; j < line.length - 1; j++) {
        const { point } = projectOnSegment(p, line[j], line[j + 1]);
        const d = dist(p, point);
        if (!best || d < best.d) best = { d, i, j, point };
      }
    });
    return best;
  };

  const attach = (tag, p) => {
    const hit = nearest(p);
    const key = `p${tag}`;
    pos.set(tag, p);
    pos.set(key, hit.point);
    link(tag, key, hit.d);
    const a = lines[hit.i][hit.j];
    const b = lines[hit.i][hit.j + 1];
    link(key, `v${hit.i}_${hit.j}`, dist(hit.point, a));
    link(key, `v${hit.i}_${hit.j + 1}`, dist(hit.point, b));
    return hit;
  };

  const s = attach('S', from);
  const e = attach('E', to);
  if (s.i === e.i && s.j === e.j) link('pS', 'pE', dist(pos.get('pS'), pos.get('pE')));

  const best = new Map([['S', 0]]);
  const prev = new Map();
  const done = new Set();
  while (true) {
    let cur = null;
    for (const [k, d] of best) {
      if (!done.has(k) && (cur === null || d < best.get(cur))) cur = k;
    }
    if (cur === null) return null;
    if (cur === 'E') break;
    done.add(cur);
    for (const { to: n, w } of adj.get(cur) || []) {
      const nd = best.get(cur) + w;
      if (!best.has(n) || nd < best.get(n)) {
        best.set(n, nd);
        prev.set(n, cur);
      }
    }
  }
  const keys = ['E'];
  while (keys[0] !== 'S') {
    const p = prev.get(keys[0]);
    if (p === undefined) return null;
    keys.unshift(p);
  }
  return keys.map((k) => pos.get(k));
}

export function routeCable(from, to, cableways, route) {
  if (route?.mode === 'manual') {
    const points = [from, ...(route.waypoints || []), to];
    return { points, lengthCm: pathLength(points), mode: 'manual' };
  }
  const routed = autoRoute(from, to, cableways);
  if (routed) return { points: routed, lengthCm: pathLength(routed), mode: 'auto' };
  return { points: [from, to], lengthCm: pathLength([from, to]), mode: 'direct' };
}

export function assignStandardLength(requiredM, standard) {
  const sorted = (standard || []).slice().sort((a, b) => a - b);
  return sorted.find((len) => len >= requiredM) ?? null;
}

export function buildCableRows({ lists, devices, elements, plan }) {
  const p = emptyCablePlan(plan);
  const settings = { ...DEFAULT_CABLE_SETTINGS, ...(p.settings || {}) };
  const deviceName = new Map((devices || []).map((d) => [d.id, d.name || 'Device']));
  const centerOfDevice = new Map();
  const centerOfElement = new Map();
  for (const el of elements || []) {
    const c = [el.position_x + (el.width_cm || 0) / 2, el.position_y + (el.height_cm || 0) / 2];
    centerOfElement.set(el.id, c);
    if (
      el.linked_device_id &&
      !SPEAKER_TYPES.has(el.element_type) &&
      !centerOfDevice.has(el.linked_device_id)
    ) {
      centerOfDevice.set(el.linked_device_id, c);
    }
  }
  const elementName = new Map((elements || []).map((e) => [e.id, e.label || e.element_type]));
  const rows = deriveCables(lists, elements).map((cable, i) => {
    const route = p.routes?.[cable.key] || { mode: 'auto', waypoints: [], hidden: false };
    const from = cable.fromElementId
      ? centerOfElement.get(cable.fromElementId)
      : centerOfDevice.get(cable.fromDeviceId);
    const to = cable.toElementId
      ? centerOfElement.get(cable.toElementId)
      : centerOfDevice.get(cable.toDeviceId);
    const base = {
      ...cable,
      index: i + 1,
      fromName: cable.fromElementId
        ? elementName.get(cable.fromElementId) || '—'
        : deviceName.get(cable.fromDeviceId) || '—',
      toName: cable.toElementId
        ? elementName.get(cable.toElementId) || '—'
        : deviceName.get(cable.toDeviceId) || '—',
      hidden: !!route.hidden,
      waypoints: route.waypoints || [],
      requestedMode: route.mode || 'auto',
    };
    if (!from || !to) {
      return { ...base, placed: false, mode: null, points: [], pathM: null, requiredM: null, assignedM: null };
    }
    const routed = routeCable(from, to, p.cableways, route);
    const pathM = routed.lengthCm / 100;
    const requiredM = pathM * (1 + settings.slack_pct / 100) + settings.slack_m;
    const assignedM = assignStandardLength(requiredM, settings.standard_lengths_m);
    return {
      ...base,
      placed: true,
      mode: routed.mode,
      points: routed.points,
      pathM: round2(pathM),
      requiredM: round2(requiredM),
      assignedM,
    };
  });
  return rows;
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

export function lengthOrder(rows) {
  const counts = new Map();
  for (const r of rows) {
    if (!r.placed) continue;
    const key = r.assignedM === null ? 'over' : r.assignedM;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => (a[0] === 'over' ? 1 : b[0] === 'over' ? -1 : a[0] - b[0]))
    .map(([length, count]) => ({ length, count }));
}

export function cablesToCsv(rows) {
  const head = ['Cable', 'From', 'To', 'Connector', 'Route', 'Path (m)', 'Needed (m)', 'Length class (m)'];
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = rows.map((r) =>
    [
      `C${r.index}`,
      r.fromName,
      r.toName,
      r.connector,
      r.placed ? r.mode : 'not placed',
      r.pathM ?? '',
      r.requiredM ?? '',
      r.assignedM === null ? 'over max' : (r.assignedM ?? ''),
    ]
      .map(esc)
      .join(','),
  );
  return [head.map(esc).join(','), ...lines].join('\n');
}
