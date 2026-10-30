export const DOMAINS = ['audio', 'lighting', 'video', 'power'];

export const DOMAIN_SIGNAL = { audio: 'audio', lighting: 'dmx', video: 'video', power: 'power' };

export const SIGNAL_COLOR = {
  audio: '#35A853',
  dmx: '#F2C037',
  video: '#31CCEC',
  power: '#C10015',
  data: '#9E9E9E',
};

const CATEGORY_RULES = [
  ['power', /power|distro|cable reel|socapex|powercon|transformer/i],
  ['lighting', /light|fixture|dmx|par\b|moving|led bar|strobe|haze|fog/i],
  ['video', /video|camera|led wall|projector|screen|sdi|hdmi|switcher|monitor tv|display/i],
  ['audio', /audio|mic|speaker|mixer|console|stagebox|snake|di box|amp|monitor|wireless|sound|headphone/i],
];

export function domainForCategory(category) {
  const text = String(category || '');
  const hit = CATEGORY_RULES.find(([, rule]) => rule.test(text));
  return hit ? hit[0] : 'other';
}

export function deviceFromProduct(product, { parentId = null } = {}) {
  const attributes = {};
  if (product.power_consumption_watts) attributes.power_w = Number(product.power_consumption_watts);
  if (product.weight_kg) attributes.weight_kg = Number(product.weight_kg);
  return {
    domain: domainForCategory(product.category),
    kind: product.category || '',
    name: product.name || product.sku || 'Item',
    attributes,
    ports: [],
    case_parent_id: parentId,
    stockwire_product_id: product.id != null ? String(product.id) : null,
    stockwire_product_name: product.name || null,
    stockwire_device_id: product.device_id != null ? String(product.device_id) : null,
    stockwire_booked: product.booked ?? null,
  };
}

export function edgeRows(edges, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  return edges.map((e) => ({
    id: e.id,
    signal: e.signal,
    from: byId.get(e.src_device_id)?.name || '?',
    fromPort: e.src_port,
    to: byId.get(e.dst_device_id)?.name || '?',
    toPort: e.dst_port,
    channels: e.channels,
    phase: e.phase,
    cableLabel: e.cable_label,
    revision: e.revision,
  }));
}

export function layerOf(device) {
  return DOMAINS.includes(device.domain) ? device.domain : 'other';
}

export function visibleOnLayers(device, layers) {
  const layer = layerOf(device);
  return layer === 'other' || layers[layer] !== false;
}

export function phaseStatus(loads, limitWatts = loads?.limit_w || 3680) {
  const levelFor = (watts) => (watts > limitWatts ? 'over' : watts > limitWatts * 0.8 ? 'warn' : 'ok');
  return {
    L1: { watts: loads.L1 || 0, level: levelFor(loads.L1 || 0) },
    L2: { watts: loads.L2 || 0, level: levelFor(loads.L2 || 0) },
    L3: { watts: loads.L3 || 0, level: levelFor(loads.L3 || 0) },
    imbalanceLevel: (loads.imbalance_pct || 0) > 30 ? 'warn' : 'ok',
  };
}

export function catalogQuery({ q, categories = [], manufacturers = [], jobId, skip = 0, limit = 50 }) {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  categories.forEach((c) => params.append('category', c));
  manufacturers.forEach((m) => params.append('manufacturer', m));
  if (jobId) params.set('job_id', jobId);
  params.set('skip', String(skip));
  params.set('limit', String(limit));
  return params;
}

export function needsBookingRequest(device) {
  return Boolean(device.stockwire_product_id) && device.stockwire_booked === false;
}

const norm = (value) => String(value || '').toLowerCase();

function connectorsFit(a, b) {
  return !a || !b || norm(a) === norm(b);
}

// Pick the first output port of src and input port of dst that can carry the same
// signal over a mating connector. Returns null when nothing fits.
export function suggestPorts(src, dst) {
  const outs = (src?.ports || []).filter((p) => p.direction === 'out');
  const ins = (dst?.ports || []).filter((p) => p.direction === 'in');
  for (const out of outs) {
    for (const input of ins) {
      const signalOk = !out.signal || !input.signal || out.signal === input.signal;
      if (signalOk && connectorsFit(out.connector, input.connector)) {
        return {
          srcPort: out.id,
          dstPort: input.id,
          signal: out.signal || input.signal || DOMAIN_SIGNAL[src.domain] || 'audio',
        };
      }
    }
  }
  return null;
}

// Map a pointer position inside the canvas host to canvas centimetres.
export function dropPosition(clientX, clientY, rect, zoom, grid = 10) {
  const snap = (v) => Math.max(0, Math.round(v / zoom / grid) * grid);
  return { x: snap(clientX - rect.left), y: snap(clientY - rect.top) };
}

export const PRODUCT_MIME = 'application/x-stagewire-products';

// Nodes that stand for list rows or chain ends, not for gear on the stage.
export const VIRTUAL_KINDS = new Set([
  'channel',
  'channel_list',
  'output',
  'video_input',
  'video_destination',
  'video_list',
  'rigging_point',
  'dmx_universe',
]);

export const isVirtual = (device) => VIRTUAL_KINDS.has(device.kind);

export const BOX_W = 96;
export const BOX_H = 40;

export const isPlotElement = (device) => device.kind === 'plot_element';

// Devices that already appear on the plot through an element are drawn as that element.
export function devicesShownAsElements(edges) {
  return new Set(
    edges
      .filter((e) => e.signal === 'link' && e.attributes?.role === 'device')
      .map((e) => e.dst_device_id),
  );
}

export function boxFor(device, zoom) {
  if (!isPlotElement(device)) return { w: BOX_W, h: BOX_H };
  const attrs = device.attributes || {};
  return {
    w: Math.max(24, (attrs.width_cm || 60) * zoom),
    h: Math.max(16, (attrs.height_cm || 60) * zoom),
  };
}

// Plot elements rotate about their top-left corner, like Konva groups do.
export function centerOf(device, zoom) {
  const { w, h } = boxFor(device, zoom);
  const theta = ((device.canvas_rotation || 0) * Math.PI) / 180;
  return [
    device.canvas_x_cm * zoom + (w / 2) * Math.cos(theta) - (h / 2) * Math.sin(theta),
    device.canvas_y_cm * zoom + (w / 2) * Math.sin(theta) + (h / 2) * Math.cos(theta),
  ];
}

// Role of the link a plot element makes to the node it is dropped on.
export function linkRoleFor(target) {
  if (target.kind === 'channel') return 'channel';
  if (target.kind === 'video_input') return 'video_input';
  if (target.domain === 'power' && target.kind !== 'plot_element') return 'power_node';
  return 'device';
}

// The edge that feeds a universe node is its source, not one of its steps.
const isUniverseSource = (node, edge) =>
  node.kind === 'dmx_universe' && edge.dst_device_id === node.id;

// Names of the devices a channel or output chain passes through, in order.
export function chainSteps(node, edges, devices) {
  const names = new Map(devices.map((d) => [d.id, d.name]));
  const steps = [];
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (attrs.chain !== node.id || isUniverseSource(node, edge)) continue;
    if (attrs.first_point) {
      steps.push({ position: attrs.first_point.position || 0, name: names.get(edge.src_device_id) });
    } else {
      steps.push({ position: attrs.position || 0, name: names.get(edge.dst_device_id) });
    }
  }
  return steps.sort((a, b) => a.position - b.position).map((s) => s.name || '?');
}

export const channelsOf = (devices, listId) =>
  devices
    .filter((d) => d.kind === 'channel' && d.attributes?.list_id === listId)
    .sort((a, b) => (a.attributes.channel_number || 0) - (b.attributes.channel_number || 0));

export const outputsOf = (devices, listId) =>
  devices
    .filter((d) => d.kind === 'output' && d.attributes?.list_id === listId)
    .sort((a, b) => a.position - b.position);

export const videoListsOf = (devices) =>
  devices.filter((d) => d.kind === 'video_list').sort((a, b) => a.position - b.position);

export const videoRowsOf = (devices, listId, kind) =>
  devices
    .filter((d) => d.kind === kind && d.attributes?.list_id === listId)
    .sort((a, b) => a.position - b.position);

// Every point of a video chain with the data the chain dialog edits, in order. Input chains have
// one edge per point; output chains keep the points that start a branch on the destination node.
export function videoChainForm(node, edges, devices) {
  const points = [];
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (attrs.chain !== node.id || !attrs.point_id) continue;
    points.push({ ...attrs, device_id: edge.dst_device_id });
  }
  for (const root of node.attributes?.roots || []) points.push(root);
  points.sort((a, b) => (a.position || 0) - (b.position || 0));
  const index = new Map(points.map((p, i) => [p.point_id, i]));
  return points
    .filter((p) => devices.some((d) => d.id === p.device_id))
    .map((p) => ({
      device_id: p.device_id,
      connector: p.connector || '',
      patch_label: p.patch_label || '',
      source_port: p.source_port || '',
      input_port: p.input_port || '',
      notes: p.notes || '',
      parent_index: p.parent_id && index.has(p.parent_id) ? index.get(p.parent_id) : null,
    }));
}

export const videoChainNames = (node, edges, devices) =>
  videoChainForm(node, edges, devices).map(
    (step) => devices.find((d) => d.id === step.device_id)?.name || '?',
  );

export const nextChannelNumber = (channels) =>
  channels.reduce((max, c) => Math.max(max, c.attributes?.channel_number || 0), 0) + 1;

// Steps the chain dialog edits, rebuilt from the graph so saving sends the whole chain.
export function chainForm(node, edges, devices) {
  const byPos = [];
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (attrs.chain !== node.id || isUniverseSource(node, edge)) continue;
    const point = attrs.first_point || attrs;
    byPos.push({
      position: point.position || 0,
      device_id: attrs.first_point ? edge.src_device_id : edge.dst_device_id,
      connector: point.connector || '',
      patch_label: point.patch_label || '',
      in_port: point.in_port || '',
      out_port: point.out_port || '',
      notes: point.notes || '',
      point_id: point.point_id || point.step_id,
      parent_id: point.parent_id || null,
    });
  }
  byPos.sort((a, b) => a.position - b.position);
  const index = new Map(byPos.map((p, i) => [p.point_id, i]));
  return byPos
    .filter((p) => devices.some((d) => d.id === p.device_id))
    .map((p) => ({
      device_id: p.device_id,
      connector: p.connector,
      patch_label: p.patch_label,
      in_port: p.in_port,
      out_port: p.out_port,
      notes: p.notes,
      parent_index: p.parent_id && index.has(p.parent_id) ? index.get(p.parent_id) : null,
    }));
}

export const DEVICE_TYPES = [
  'digital_stagebox',
  'analog_stagebox',
  'mixer',
  'split',
  'network',
  'direct',
  'switcher',
  'router',
  'multiviewer',
  'camera',
  'lens',
  'ptz_camera',
  'computer',
  'patchbay',
  'converter',
  'encoder',
  'recorder',
  'screen',
  'projector',
  'fixture',
  'other',
];

export const IO_DEVICE_TYPES = ['mixer', 'switcher', 'router', 'multiviewer'];
export const CAMERA_TYPES = ['camera', 'ptz_camera'];

export function signalForType(type) {
  if (type === 'fixture') return 'dmx';
  if (['camera', 'ptz_camera', 'lens', 'screen', 'projector', 'switcher', 'multiviewer'].includes(type)) {
    return 'video';
  }
  return 'audio';
}

const slug = (connector) => String(connector || '').toLowerCase() || 'x';

// A connector group is what the editor shows for a device's connectors: a direction ('in', 'out'
// or 'both'), a connector type and how many of them. The graph has no bidirectional port, so a
// 'both' group is stored as two ports (one in, one out) with the same connector and count, and
// shown as one group again when a matching in/out pair is found.
export const CONNECTOR_CHOICES = [
  { value: 'xlr3', label: 'XLR 3-pin' },
  { value: 'xlr5', label: 'XLR 5-pin' },
  { value: 'trs', label: 'TRS / jack' },
  { value: 'speakon', label: 'Speakon' },
  { value: 'dante', label: 'Dante' },
  { value: 'aes50', label: 'AES50' },
  { value: 'madi', label: 'MADI' },
  { value: 'avb', label: 'AVB' },
  { value: 'ethernet', label: 'Ethernet (RJ45)' },
  { value: 'ethercon', label: 'etherCON' },
  { value: 'fiber', label: 'Fibre' },
  { value: 'sdi', label: 'SDI' },
  { value: 'hdmi', label: 'HDMI' },
  { value: 'displayport', label: 'DisplayPort' },
  { value: 'bnc', label: 'BNC' },
  { value: 'usb', label: 'USB' },
  { value: 'dmx', label: 'DMX (XLR 5)' },
  { value: 'powercon', label: 'powerCON' },
  { value: 'schuko', label: 'Schuko' },
  { value: 'cee16', label: 'CEE 16 A' },
];

// One-tap additions for the connector editor. Adding one that already exists adds to its count.
export const CONNECTOR_PRESETS = [
  { label: 'XLR ×8 in', connector: 'xlr3', direction: 'in', count: 8 },
  { label: 'XLR ×8 out', connector: 'xlr3', direction: 'out', count: 8 },
  { label: 'Speakon ×4 out', connector: 'speakon', direction: 'out', count: 4 },
  { label: 'Dante', connector: 'dante', direction: 'both', count: 1 },
  { label: 'AES50', connector: 'aes50', direction: 'both', count: 1 },
  { label: 'Ethernet', connector: 'ethernet', direction: 'both', count: 1 },
  { label: 'SDI in', connector: 'sdi', direction: 'in', count: 1 },
  { label: 'SDI out', connector: 'sdi', direction: 'out', count: 1 },
  { label: 'HDMI in', connector: 'hdmi', direction: 'in', count: 1 },
  { label: 'HDMI out', connector: 'hdmi', direction: 'out', count: 1 },
  { label: 'DMX in', connector: 'dmx', direction: 'in', count: 1 },
  { label: 'DMX out', connector: 'dmx', direction: 'out', count: 1 },
  { label: 'powerCON in', connector: 'powercon', direction: 'in', count: 1 },
  { label: 'powerCON out', connector: 'powercon', direction: 'out', count: 1 },
];

export const connectorLabel = (value) =>
  CONNECTOR_CHOICES.find((c) => c.value === String(value || '').toLowerCase())?.label || value || '';

// Add a preset to a list of groups: bump the count of the same connector and direction, else append.
export function addConnector(groups, preset) {
  const key = String(preset.connector).toLowerCase();
  const hit = groups.find(
    (g) => String(g.connector).toLowerCase() === key && g.direction === preset.direction,
  );
  if (!hit) return [...groups, { direction: preset.direction, connector: key, count: preset.count }];
  return groups.map((g) => (g === hit ? { ...g, count: (g.count || 0) + preset.count } : g));
}

// Connector groups the editor shows: the ports that carry a connector or a channel count, with a
// matching in/out pair folded into one 'both' group.
export function portGroups(ports) {
  const groups = (ports || [])
    .filter((p) => p.connector || p.channels)
    .map((p) => ({ direction: p.direction, connector: p.connector || '', count: p.channels || 0 }));
  const folded = [];
  const used = new Set();
  groups.forEach((g, i) => {
    if (used.has(i)) return;
    const mate = groups.findIndex(
      (o, j) =>
        j > i &&
        !used.has(j) &&
        o.direction !== g.direction &&
        o.connector === g.connector &&
        o.count === g.count,
    );
    if (mate === -1) {
      folded.push(g);
    } else {
      used.add(mate);
      folded.push({ ...g, direction: 'both' });
    }
  });
  return folded;
}

// Groups as plain in/out groups (a 'both' group becomes two), the form the create endpoint takes.
export const expandGroups = (groups) =>
  groups.flatMap((g) =>
    g.direction === 'both'
      ? [
          { ...g, direction: 'in' },
          { ...g, direction: 'out' },
        ]
      : [g],
  );

// Graph ports for a set of connector groups, keeping the device's own generic ports as they are.
export function portsFromGroups(groups, existing, type) {
  const generic = (existing || []).filter((p) => !p.connector && !p.channels);
  const seen = new Set(generic.map((p) => p.id));
  const signal = signalForType(type);
  const fromGroups = expandGroups(groups).map((g) => {
    const base = `${g.direction}-${slug(g.connector)}`;
    let id = base;
    for (let n = 2; seen.has(id); n += 1) id = `${base}-${n}`;
    seen.add(id);
    return {
      id,
      direction: g.direction,
      signal,
      connector: g.connector ? g.connector.toLowerCase() : null,
      channels: g.count || null,
    };
  });
  return [...fromGroups, ...generic];
}

export const NUMBER_FIELDS = [
  'weight_kg',
  'power_w',
  'input_override',
  'output_override',
  'footprint_channels',
  'sensor_width_mm',
  'focal_min_mm',
  'focal_max_mm',
  'max_distance_m',
  'throw_ratio_min',
  'throw_ratio_max',
  'image_aspect_ratio',
];
export const TEXT_FIELDS = ['fixture_type', 'channel_mode', 'default_gel'];

export function deviceForm(node) {
  const attrs = node?.attributes || {};
  const form = {
    name: node?.name || '',
    device_type: node?.kind || 'other',
    notes: node?.notes || '',
    ports: portGroups(node?.ports).map((g) => ({ ...g })),
  };
  for (const key of [...NUMBER_FIELDS, ...TEXT_FIELDS]) form[key] = attrs[key] ?? null;
  return form;
}

// PATCH body for an edit: only the form's attributes; the server keeps the others.
export function devicePatch(node, form) {
  const attributes = {};
  for (const key of NUMBER_FIELDS) {
    attributes[key] = form[key] === '' || form[key] == null ? null : Number(form[key]);
  }
  for (const key of TEXT_FIELDS) attributes[key] = form[key] || null;
  return {
    name: form.name,
    kind: form.device_type,
    notes: form.notes,
    attributes,
    ports: portsFromGroups(form.ports, node.ports, form.device_type),
  };
}

// Body for the create endpoint, which speaks the legacy field names.
export function deviceCreateBody(form) {
  const body = {
    name: form.name,
    device_type: form.device_type,
    notes: form.notes,
    ports: expandGroups(form.ports.filter((p) => p.connector || p.count)),
  };
  const map = { power_w: 'power_watts' };
  for (const key of [...NUMBER_FIELDS, ...TEXT_FIELDS]) {
    const value = form[key];
    if (value !== null && value !== '' && value !== undefined) body[map[key] || key] = value;
  }
  return body;
}

export const isGear = (device) => !isVirtual(device) && !isPlotElement(device);

// A node that is a fixture: its own fixture node, or a device that carries a DMX patch.
export const isFixtureNode = (device) =>
  device.kind === 'fixture' ||
  device.attributes?.universe != null ||
  device.attributes?.dmx_address != null;

export const fixtureView = (node) => ({
  id: node.id,
  universe: node.attributes?.universe ?? null,
  dmx_address: node.attributes?.dmx_address ?? null,
  footprint: node.attributes?.footprint ?? null,
});

export const fixturesOf = (devices) =>
  devices
    .filter((d) => isFixtureNode(d) && !isPlotElement(d))
    .sort(
      (a, b) =>
        (a.attributes?.universe ?? 1e9) - (b.attributes?.universe ?? 1e9) ||
        (a.attributes?.dmx_address ?? 1e9) - (b.attributes?.dmx_address ?? 1e9) ||
        a.name.localeCompare(b.name),
    );

export const universesOf = (devices) =>
  devices.filter((d) => d.kind === 'dmx_universe').sort((a, b) => a.position - b.position);

// The device feeding a universe: the source of the edge that ends at the universe node.
export const universeSource = (universe, edges) =>
  edges.find(
    (e) => e.dst_device_id === universe.id && e.attributes?.chain === universe.id,
  )?.src_device_id || null;

// The step tree of a universe in the shape the DMX flow diagram draws.
export function dmxTree(universe, edges, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  const steps = edges
    .filter((e) => e.attributes?.chain === universe.id && e.attributes?.step_id)
    .map((e) => {
      const a = e.attributes;
      const target = byId.get(e.dst_device_id);
      return {
        id: a.step_id,
        parent: a.parent_id || null,
        position: a.position || 0,
        kind: target && isFixtureNode(target) ? 'fixture' : 'device',
        label: target?.name || '?',
        device_id: e.dst_device_id,
        in_port: a.in_port || '',
        out_port: a.out_port || '',
        connector: a.connector || '',
        notes: a.notes || '',
        children: [],
      };
    })
    .sort((x, y) => x.position - y.position);
  const index = new Map(steps.map((s) => [s.id, s]));
  const roots = [];
  for (const step of steps) {
    const parent = step.parent ? index.get(step.parent) : null;
    (parent ? parent.children : roots).push(step);
  }
  return roots;
}

// Modes of the library type with this name (case-insensitive), for the mode select.
export function modesForType(types, typeName) {
  const wanted = String(typeName || '').trim().toLowerCase();
  const found = (types || []).find((t) => t.name.toLowerCase() === wanted);
  return found ? [...found.modes].sort((a, b) => a.position - b.position) : [];
}

// What choosing a mode does to a fixture row: the mode's name and its footprint.
export const modeAttributes = (mode) => ({ channel_mode: mode.name, footprint: mode.footprint });

// The power tree as rows in display order (a node under its first parent), with its depth.
export function powerTreeRows(nodes) {
  const children = new Map();
  for (const node of nodes) {
    const parent = node.parent_id || null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(node);
  }
  const rows = [];
  const seen = new Set();
  const walk = (parent, depth) => {
    for (const node of children.get(parent) || []) {
      if (seen.has(node.id)) continue;
      seen.add(node.id);
      rows.push({ ...node, depth });
      walk(node.id, depth + 1);
    }
  };
  walk(null, 0);
  for (const node of nodes) if (!seen.has(node.id)) rows.push({ ...node, depth: 0 });
  return rows;
}

export const outputsLabel = (outputs, labelOf = (c) => c) =>
  (outputs || []).map((o) => `${o.count}× ${labelOf(o.connector)}${o.phase ? ` ${o.phase}` : ''}`).join(', ');

export const loadStatusColor = (status) =>
  ({ ok: 'positive', warn: 'warning', over: 'negative', unpowered: 'grey' })[status] || 'grey';
