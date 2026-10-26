// Cables run between consecutive linked devices in each signal chain. They are
// derived from the chains; only routing, visibility and length settings are stored
// on the job (cable_plan). A cable is keyed by its downstream patch point id, so a
// stored route survives changes elsewhere in the plan.

export const DEFAULT_CABLE_SETTINGS = {
  slack_pct: 10,
  slack_m: 1,
  standard_lengths_m: [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50],
  // Lower values favour cableways more: a cable on a tray costs this share of its length.
  cableway_factor: 0.5,
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

export function deriveCables(lists, elements, videoLists = []) {
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
  for (const list of videoLists || []) {
    for (const input of list.inputs || []) {
      const pts = orderedPoints(input.patch_points).filter((p) => p.device_id);
      if (!pts.length) continue;
      const label = `Cam ${input.input_number}${input.source_label ? ` ${input.source_label}` : ''}`;
      for (const el of elements || []) {
        if (el.linked_video_input_id !== input.id) continue;
        cables.push({
          key: `src:${el.id}`,
          kind: 'source',
          label,
          channelId: input.id,
          fromElementId: el.id,
          fromPointId: null,
          fromDeviceId: null,
          toDeviceId: pts[0].device_id,
          toPointId: pts[0].id,
          connector: pts[0].connector || '',
        });
      }
      for (let i = 1; i < pts.length; i++) {
        const from = pts[i - 1];
        const to = pts[i];
        if (from.device_id === to.device_id) continue;
        cables.push({
          key: to.id,
          kind: 'link',
          label,
          channelId: input.id,
          fromElementId: null,
          fromPointId: from.id,
          fromDeviceId: from.device_id,
          toDeviceId: to.device_id,
          toPointId: to.id,
          connector: to.connector || '',
        });
      }
    }
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

// Cable on a cableway costs this fraction of the same length in the open. A tray is
// used when it saves real distance; a cable never goes across the room to reach one.
const CABLEWAY_TRAVEL = 0.5;
// Each metre inside the audience area costs this much. Crossing is allowed, so a
// cable crosses only when the detour around the audience is much longer.
const AUDIENCE_PENALTY = 3;

function pointInPolygon(p, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

// Parameters t in [0, 1] where segment a-b crosses the polygon outline.
function crossingParams(a, b, poly) {
  const ts = [];
  for (let i = 0; i < poly.length; i++) {
    const c = poly[i];
    const d = poly[(i + 1) % poly.length];
    const rx = b[0] - a[0];
    const ry = b[1] - a[1];
    const sx = d[0] - c[0];
    const sy = d[1] - c[1];
    const denom = rx * sy - ry * sx;
    if (Math.abs(denom) < 1e-9) continue;
    const qx = c[0] - a[0];
    const qy = c[1] - a[1];
    const t = (qx * sy - qy * sx) / denom;
    const u = (qx * ry - qy * rx) / denom;
    if (t >= 0 && t <= 1 && u >= 0 && u <= 1) ts.push(t);
  }
  return ts;
}

// Length of a-b that lies inside the audience area.
function insideLength(a, b, poly) {
  if (!poly || poly.length < 3) return 0;
  const ts = [0, ...crossingParams(a, b, poly), 1].sort((x, y) => x - y);
  let inside = 0;
  for (let k = 1; k < ts.length; k++) {
    const t0 = ts[k - 1];
    const t1 = ts[k];
    if (t1 - t0 < 1e-9) continue;
    const mid = [a[0] + ((t0 + t1) / 2) * (b[0] - a[0]), a[1] + ((t0 + t1) / 2) * (b[1] - a[1])];
    if (pointInPolygon(mid, poly)) inside += (t1 - t0) * dist(a, b);
  }
  return inside;
}

// Cost of running a straight cable from a to b: metres in the open, with the
// audience metres counted at the penalty.
function openCost(a, b, poly) {
  const length = dist(a, b);
  return length + insideLength(a, b, poly) * (AUDIENCE_PENALTY - 1);
}

// Shortest route from `from` to `to`. The graph joins the cableway network (points
// where trays meet, and where each end drops onto a tray), the corners of the audience
// area, and the two ends. Trays cost CABLEWAY_TRAVEL per metre; open runs cost
// openCost. Returns null when the straight run is best.
function autoRoute(from, to, cableways, audience = [], trayFactor = CABLEWAY_TRAVEL) {
  const lines = (cableways || []).map((c) => c.points || []).filter((p) => p.length >= 2);
  const poly = audience && audience.length >= 3 ? audience : [];
  if (!lines.length && !poly.length) return null;

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
  for (const seg of segs) {
    seg.extra.push(projectOnSegment(from, seg.a, seg.b).point, projectOnSegment(to, seg.a, seg.b).point);
  }

  const pos = new Map();
  const adj = new Map();
  const addEdge = (a, b, w) => {
    if (!adj.has(a)) adj.set(a, []);
    if (!adj.has(b)) adj.set(b, []);
    adj.get(a).push({ to: b, w });
    adj.get(b).push({ to: a, w });
  };
  const trayNodes = [];
  for (const seg of segs) {
    const unique = [...new Map([seg.a, seg.b, ...seg.extra].map((p) => [nodeKey(p), p])).values()];
    unique.sort((p, q) => dist(seg.a, p) - dist(seg.a, q));
    for (const p of unique) {
      if (!pos.has(nodeKey(p))) trayNodes.push(nodeKey(p));
      pos.set(nodeKey(p), p);
    }
    for (let k = 1; k < unique.length; k++) {
      addEdge(
        nodeKey(unique[k - 1]),
        nodeKey(unique[k]),
        openCost(unique[k - 1], unique[k], poly) * trayFactor,
      );
    }
  }

  const S = '__from';
  const T = '__to';
  pos.set(S, from);
  pos.set(T, to);
  const corners = poly.map((c, i) => {
    const key = `__corner${i}`;
    pos.set(key, c);
    return key;
  });
  // Open runs: from each end, from each audience corner, and between the ends and
  // corners. Trays are only joined to each other along their own segments.
  const open = [S, T, ...corners];
  const everyNode = [...trayNodes, ...open];
  for (const a of open) {
    for (const b of everyNode) {
      if (a === b) continue;
      if (adj.has(a) && (adj.get(a) || []).some((e) => e.to === b)) continue;
      addEdge(a, b, openCost(pos.get(a), pos.get(b), poly));
    }
  }

  const best = new Map([[S, 0]]);
  const prev = new Map();
  const done = new Set();
  while (true) {
    let cur = null;
    for (const [k, d] of best) {
      if (!done.has(k) && (cur === null || d < best.get(cur))) cur = k;
    }
    if (cur === null) return null;
    if (cur === T) break;
    done.add(cur);
    for (const { to: n, w } of adj.get(cur) || []) {
      const nd = best.get(cur) + w;
      if (!best.has(n) || nd < best.get(n)) {
        best.set(n, nd);
        prev.set(n, cur);
      }
    }
  }
  const keys = [T];
  while (keys[0] !== S) {
    const p = prev.get(keys[0]);
    if (p === undefined) return null;
    keys.unshift(p);
  }
  const via = keys.slice(1, -1);
  if (!via.length) return null;
  return [from, ...via.map((k) => pos.get(k)), to];
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

export function routeCable(from, to, cableways, route, audience = [], trayFactor = CABLEWAY_TRAVEL) {
  if (route?.mode === 'manual') {
    const points = [from, ...(route.waypoints || []), to];
    return { points, lengthCm: pathLength(points), mode: 'manual', crossesAudience: crosses(points, audience) };
  }
  const routed = autoRoute(from, to, cableways, audience, trayFactor);
  if (routed) {
    return { points: routed, lengthCm: pathLength(routed), mode: 'auto', crossesAudience: crosses(routed, audience) };
  }
  const direct = [from, to];
  return { points: direct, lengthCm: pathLength(direct), mode: 'direct', crossesAudience: crosses(direct, audience) };
}

function crosses(points, audience) {
  for (let i = 1; i < points.length; i++) {
    if (insideLength(points[i - 1], points[i], audience) > 0) return true;
  }
  return false;
}

export function assignStandardLength(requiredM, standard) {
  const sorted = (standard || []).slice().sort((a, b) => a - b);
  return sorted.find((len) => len >= requiredM) ?? null;
}

export function buildCableRows({
  lists,
  devices,
  elements,
  plan,
  videoLists = [],
  audience = [],
  stageOffset = [0, 0],
}) {
  // The audience area is drawn in venue coordinates; cables work in stage coordinates.
  const audienceLocal = (audience || []).map(([x, y]) => [x - stageOffset[0], y - stageOffset[1]]);
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
  const rows = deriveCables(lists, elements, videoLists).map((cable, i) => {
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
    const routed = routeCable(from, to, p.cableways, route, audienceLocal, Number(settings.cableway_factor) || CABLEWAY_TRAVEL);
    const pathM = routed.lengthCm / 100;
    const requiredM = pathM * (1 + settings.slack_pct / 100) + settings.slack_m;
    const assignedM = assignStandardLength(requiredM, settings.standard_lengths_m);
    return {
      ...base,
      placed: true,
      mode: routed.mode,
      points: routed.points,
      crossesAudience: routed.crossesAudience,
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

// Cable type is the connector at the cable's destination. Cables without one are
// counted under "unspecified" so none are dropped from the shopping list.
export function cableTypeOrder(rows) {
  const groups = new Map();
  for (const r of rows) {
    if (!r.placed) continue;
    const type = r.connector || 'unspecified';
    if (!groups.has(type)) groups.set(type, new Map());
    const lengths = groups.get(type);
    const key = r.assignedM === null ? 'over' : r.assignedM;
    lengths.set(key, (lengths.get(key) || 0) + 1);
  }
  return [...groups.entries()]
    .sort((a, b) => (a[0] === 'unspecified' ? 1 : b[0] === 'unspecified' ? -1 : a[0].localeCompare(b[0])))
    .map(([type, lengths]) => {
      const sorted = [...lengths.entries()]
        .sort((a, b) => (a[0] === 'over' ? 1 : b[0] === 'over' ? -1 : a[0] - b[0]))
        .map(([length, count]) => ({ length, count }));
      return { type, lengths: sorted, total: sorted.reduce((sum, l) => sum + l.count, 0) };
    });
}

export function cableTypeCsv(rows) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [];
  for (const group of cableTypeOrder(rows)) {
    for (const l of group.lengths) {
      lines.push(
        [group.type, l.length === 'over' ? 'over max' : l.length, l.count].map(esc).join(','),
      );
    }
  }
  return ['Cable type,Length class (m),Count', ...lines].join('\n');
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
