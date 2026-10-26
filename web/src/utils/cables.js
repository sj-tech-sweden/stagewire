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

function segmentIntersection(a, b, c, d) {
  const rx = b[0] - a[0];
  const ry = b[1] - a[1];
  const sx = d[0] - c[0];
  const sy = d[1] - c[1];
  const denom = rx * sy - ry * sx;
  if (Math.abs(denom) < 1e-9) return null;
  const qx = c[0] - a[0];
  const qy = c[1] - a[1];
  const t = (qx * sy - qy * sx) / denom;
  const u = (qx * ry - qy * rx) / denom;
  const eps = 1e-9;
  if (t < -eps || t > 1 + eps || u < -eps || u > 1 + eps) return null;
  return [a[0] + t * rx, a[1] + t * ry];
}

const nodeKey = (p) => `${p[0].toFixed(3)},${p[1].toFixed(3)}`;

// Shortest path from `from` to `to` that follows the cableways. All cableways form
// one network: segments are split where they cross or meet, both ends snap onto
// the nearest point of that network, and Dijkstra runs over the result.
function autoRoute(from, to, cableways) {
  const lines = (cableways || []).map((c) => c.points || []).filter((p) => p.length >= 2);
  if (!lines.length) return null;

  const segs = [];
  for (const line of lines) {
    for (let j = 0; j < line.length - 1; j++) {
      segs.push({ a: line[j], b: line[j + 1], extra: [] });
    }
  }
  for (let i = 0; i < segs.length; i++) {
    for (let j = i + 1; j < segs.length; j++) {
      const p = segmentIntersection(segs[i].a, segs[i].b, segs[j].a, segs[j].b);
      if (p) {
        segs[i].extra.push(p);
        segs[j].extra.push(p);
      }
    }
  }

  const nearest = (p) => {
    let best = null;
    for (const seg of segs) {
      const { point } = projectOnSegment(p, seg.a, seg.b);
      const d = dist(p, point);
      if (!best || d < best.d) best = { d, seg, point };
    }
    return best;
  };
  const sHit = nearest(from);
  const eHit = nearest(to);
  sHit.seg.extra.push(sHit.point);
  eHit.seg.extra.push(eHit.point);

  const pos = new Map();
  const adj = new Map();
  const link = (a, b) => {
    const w = dist(pos.get(a), pos.get(b));
    if (!adj.has(a)) adj.set(a, []);
    if (!adj.has(b)) adj.set(b, []);
    adj.get(a).push({ to: b, w });
    adj.get(b).push({ to: a, w });
  };
  for (const seg of segs) {
    const pts = [seg.a, seg.b, ...seg.extra];
    for (const p of pts) pos.set(nodeKey(p), p);
    const ordered = [...new Set(pts.map(nodeKey))]
      .map((k) => pos.get(k))
      .sort((p, q) => dist(seg.a, p) - dist(seg.a, q));
    for (let k = 1; k < ordered.length; k++) link(nodeKey(ordered[k - 1]), nodeKey(ordered[k]));
  }

  const startKey = nodeKey(sHit.point);
  const endKey = nodeKey(eHit.point);
  const best = new Map([[startKey, 0]]);
  const prev = new Map();
  const done = new Set();
  while (true) {
    let cur = null;
    for (const [k, d] of best) {
      if (!done.has(k) && (cur === null || d < best.get(cur))) cur = k;
    }
    if (cur === null) return null;
    if (cur === endKey) break;
    done.add(cur);
    for (const { to: n, w } of adj.get(cur) || []) {
      const nd = best.get(cur) + w;
      if (!best.has(n) || nd < best.get(n)) {
        best.set(n, nd);
        prev.set(n, cur);
      }
    }
  }
  const keys = [endKey];
  while (keys[0] !== startKey) {
    const p = prev.get(keys[0]);
    if (p === undefined) return null;
    keys.unshift(p);
  }
  return [from, ...keys.map((k) => pos.get(k)), to];
}

// Elements rotate about their top-left corner, so the drawn centre moves with the angle.
export function elementCentre(el) {
  const theta = ((el.rotation || 0) * Math.PI) / 180;
  const hw = (el.width_cm || 0) / 2;
  const hh = (el.height_cm || 0) / 2;
  return [
    el.position_x + hw * Math.cos(theta) - hh * Math.sin(theta),
    el.position_y + hw * Math.sin(theta) + hh * Math.cos(theta),
  ];
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
    const c = elementCentre(el);
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
      return {
        ...base,
        placed: false,
        missingName: !from ? base.fromName : base.toName,
        mode: null,
        points: [],
        pathM: null,
        requiredM: null,
        assignedM: null,
      };
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
