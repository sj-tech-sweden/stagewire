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

const PRODUCT_DIRECTIONS = { in: 'in', input: 'in', out: 'out', output: 'out', both: 'both', io: 'both', bidirectional: 'both' };

// Connector groups from a Stockwire product's specs.connectors, the same tolerant reading as
// api/app/domains/audio/device_specs.py (see docs/stockwire-integration-spec.md section 3.10): a
// list of names, or of {connector, direction, count}. Returns editor groups (direction in, out or both).
export function connectorGroupsFromProduct(product) {
  const raw = product?.specs?.connectors;
  if (!Array.isArray(raw)) return [];
  const groups = [];
  for (const entry of raw) {
    const item = typeof entry === 'string' ? { connector: entry } : entry;
    if (!item || typeof item !== 'object') continue;
    const name = String(item.connector || item.type || item.name || '').trim().toLowerCase();
    if (!name) continue;
    const count = Number.parseInt(item.count, 10);
    groups.push({
      direction: PRODUCT_DIRECTIONS[String(item.direction || '').toLowerCase()] || 'both',
      connector: name,
      count: count >= 1 ? count : 1,
      signal: ['audio', 'video', 'dmx', 'power', 'data'].includes(item.signal) ? item.signal : null,
    });
  }
  return groups;
}

export function deviceFromProduct(product, { parentId = null } = {}) {
  const attributes = {};
  if (product.power_consumption_watts) attributes.power_w = Number(product.power_consumption_watts);
  if (product.weight_kg) attributes.weight_kg = Number(product.weight_kg);
  const inlet = String(product.specs?.power_inlet || '').trim().toLowerCase();
  if (inlet) attributes.power_inlet = inlet;
  const domain = domainForCategory(product.category);
  return {
    domain,
    kind: product.category || '',
    name: product.name || product.sku || 'Item',
    attributes,
    ports: portsFromGroups(
      connectorGroupsFromProduct(product).map((g) => ({ ...g, signal: g.signal || DOMAIN_SIGNAL[domain] || 'audio' })),
      [],
      '',
    ),
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
    srcId: e.src_device_id,
    dstId: e.dst_device_id,
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

// Gear is drawn as a box in cm on the plot (a plot element has its own width and height); the
// size can be set per device (attributes width_cm/height_cm) and scaled for the whole canvas.
export const DEVICE_BOX_CM = { w: 60, h: 30 };
const MIN_BOX_PX = { w: 28, h: 16 };

export const isPlotElement = (device) => device.kind === 'plot_element';

// Devices that already appear on the plot through an element are drawn as that element.
export function devicesShownAsElements(edges) {
  return new Set(
    edges
      .filter((e) => e.signal === 'link' && e.attributes?.role === 'device')
      .map((e) => e.dst_device_id),
  );
}

export function boxFor(device, zoom, scale = 1) {
  const attrs = device.attributes || {};
  const fallback = isPlotElement(device) ? { w: 60, h: 60 } : DEVICE_BOX_CM;
  const factor = isPlotElement(device) ? 1 : scale;
  return {
    w: Math.max(MIN_BOX_PX.w, (attrs.width_cm || fallback.w) * factor * zoom),
    h: Math.max(MIN_BOX_PX.h, (attrs.height_cm || fallback.h) * factor * zoom),
  };
}

// Plot elements rotate about their top-left corner, like Konva groups do.
export function centerOf(device, zoom, scale = 1) {
  const { w, h } = boxFor(device, zoom, scale);
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
// The device nodes a chain passes through, in order (a step whose device is gone is left out).
// Used for the clickable device chips next to a chain, so the gear can be edited from the list.
export function chainDevices(node, edges, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  const steps = [];
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (attrs.chain !== node.id || isUniverseSource(node, edge)) continue;
    if (attrs.first_point) {
      steps.push({ position: attrs.first_point.position || 0, device: byId.get(edge.src_device_id) });
    } else {
      steps.push({ position: attrs.position || 0, device: byId.get(edge.dst_device_id) });
    }
  }
  return steps.sort((a, b) => a.position - b.position).map((s) => s.device).filter(Boolean);
}

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

// The device nodes of a video chain, in order (same use as chainDevices).
export const videoChainDevices = (node, edges, devices) =>
  videoChainForm(node, edges, devices)
    .map((step) => devices.find((d) => d.id === step.device_id))
    .filter(Boolean);

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
      bus_connector: point.bus_connector || '',
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
      signal: g.signal || signal,
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
// How a device takes mains: most gear has an IEC C13 inlet (a detachable cable is needed) or a
// cable attached with a Schuko plug; microphones, passive speakers and the like take none. An empty
// value means the default, IEC C13.
export const POWER_INLETS = [
  { value: 'iec_c13', label: 'IEC C13' },
  { value: 'none', label: 'No power (passive)' },
  { value: 'attached_schuko', label: 'Attached cable, Schuko' },
  { value: 'powercon', label: 'powerCON' },
  { value: 'cee16', label: 'CEE 16 A' },
  { value: 'other', label: 'Other' },
];

export const TEXT_FIELDS = ['fixture_type', 'channel_mode', 'default_gel', 'power_inlet'];

export function deviceForm(node) {
  const attrs = node?.attributes || {};
  const form = {
    name: node?.name || '',
    device_type: node?.kind || 'other',
    notes: node?.notes || '',
    ports: portGroups(node?.ports).map((g) => ({ ...g })),
    stockwire_product_id: node?.stockwire_product_id ?? null,
    stockwire_product_name: node?.stockwire_product_name ?? null,
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
    ...(form.stockwire_product_id !== (node.stockwire_product_id ?? null)
      ? { stockwire_product_id: form.stockwire_product_id, stockwire_product_name: form.stockwire_product_name }
      : {}),
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
  if (form.stockwire_product_id) {
    body.stockwire_product_id = form.stockwire_product_id;
    body.stockwire_product_name = form.stockwire_product_name;
  }
  const map = { power_w: 'power_watts' };
  for (const key of [...NUMBER_FIELDS, ...TEXT_FIELDS]) {
    const value = form[key];
    if (value !== null && value !== '' && value !== undefined) body[map[key] || key] = value;
  }
  return body;
}

// Power tree nodes (sources such as a venue outlet, distros, breakouts and extension cords) are
// edited in the rigging & power editor: they have no power inlet of their own and are not gear.
export const POWER_NODE_KINDS = ['source', 'distro', 'breakout', 'extension'];
export const isPowerNode = (device) => device.domain === 'power' && POWER_NODE_KINDS.includes(device.kind);

export const isGear = (device) => !isVirtual(device) && !isPlotElement(device) && !isPowerNode(device);

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

// Standard cord lengths (m) an extension is rented or packed in; a needed length is rounded up.
export const CORD_LENGTHS = [2, 5, 10, 15, 20, 25, 30, 50];
export const cordFor = (metres) => CORD_LENGTHS.find((l) => l >= metres) || Math.ceil(metres);

// Feeds on the plot that are longer than a normal cord reaches: the distance between a node and
// what feeds it (another node, or the venue outlet a source is plugged into), in metres. Plot
// positions are stage-relative cm for nodes and outlets alike. A feed that already goes through an
// extension is skipped. Used to suggest the extension cords the plot needs.
export function longFeeds(nodes, outlets, thresholdM = 5) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const outletAt = new Map(outlets.map((o) => [String(o.id), o]));
  const spot = (n) => (n.x_cm != null && n.y_cm != null ? [n.x_cm, n.y_cm] : null);
  const out = [];
  for (const node of nodes) {
    if (node.kind === 'extension' || !node.parent_id) continue;
    const parent = byId.get(node.parent_id);
    if (!parent || parent.kind === 'extension') continue;
    const from = spot(parent) || (parent.venue_outlet_id && outletAt.get(String(parent.venue_outlet_id)) ? [outletAt.get(String(parent.venue_outlet_id)).x_cm, outletAt.get(String(parent.venue_outlet_id)).y_cm] : null);
    const to = spot(node);
    if (!from || !to) continue;
    const metres = Math.hypot(from[0] - to[0], from[1] - to[1]) / 100;
    if (metres > thresholdM) out.push({ node, parent, metres: Math.round(metres * 10) / 10, length: cordFor(metres) });
  }
  return out.sort((a, b) => b.metres - a.metres);
}

// Fill a device form from /stockwire/products/{id}/device-specs and the picked product: name, the
// connectors (added to what is there with the usual "same connector raises the count" rule), the
// power inlet, weight and power. Fields the product does not give are left as they are.
export function fillFormFromSpecs(form, product, specs) {
  form.name = form.name || product.name || specs.name || '';
  form.stockwire_product_id = product.id != null ? String(product.id) : null;
  form.stockwire_product_name = product.name || null;
  for (const group of specs.connector_groups || []) {
    form.ports = addConnector(form.ports, {
      connector: group.connector,
      direction: group.direction,
      count: group.count,
    });
  }
  if (specs.power_inlet) form.power_inlet = specs.power_inlet;
  if (specs.weight_kg) form.weight_kg = specs.weight_kg;
  if (specs.power_watts) form.power_w = specs.power_watts;
  return form;
}

// A chain as a tree for the flow diagram: the source (channel, input or output) first, then the
// devices. `steps` are chain-dialog steps (chainForm / videoChainForm). A step takes its signal
// from `parent_index`; without one it follows the previous step, except in a video output where
// a step without a parent starts its own branch (`separateRoots`).
export function flowTree(sourceLabel, steps, devices, { separateRoots = false } = {}) {
  const nodes = steps.map((step, i) => ({
    id: `step-${i}`,
    label: devices.find((d) => d.id === step.device_id)?.name || '?',
    kind: 'device',
    in_port: step.in_port || step.input_port || '',
    out_port: step.out_port || step.source_port || '',
    connector: step.connector || '',
    children: [],
  }));
  const roots = [];
  steps.forEach((step, i) => {
    let parent = step.parent_index;
    if (parent == null && !separateRoots && i > 0) parent = i - 1;
    (parent == null ? roots : nodes[parent].children).push(nodes[i]);
  });
  if (!sourceLabel) return roots;
  return [{ id: 'source', label: sourceLabel, kind: 'source', in_port: '', out_port: '', connector: '', children: roots }];
}

export const powerInletLabel = (inlet) =>
  POWER_INLETS.find((i) => i.value === (inlet || 'iec_c13'))?.label || inlet;

// The lead a device needs to reach a node outlet: a detachable inlet (IEC C13 unless stated) needs
// a cable to the outlet's connector, a fixed Schuko cable only fits a Schuko outlet. Same wording as
// the power sheet (api/app/domains/reports/power_context.py).
export function cableFor(inlet, outletLabel) {
  const kind = inlet || 'iec_c13';
  if (kind === 'none') return '';
  if (kind === 'iec_c13') return `IEC C13 → ${outletLabel}`;
  if (kind === 'attached_schuko') return /schuko/i.test(outletLabel) || !outletLabel ? 'Fixed cable (Schuko)' : `Fixed Schuko → ${outletLabel}`;
  return `${powerInletLabel(kind)} → ${outletLabel}`;
}

// Output (bus) modes and the channels a bus has: a connection on the bus is for one of them
// (OutputPatchPoint.bus_connector). A mono bus has none. Names can also be typed in.
export const OUTPUT_MODES = [
  { value: 'mono', channels: [] },
  { value: 'stereo', channels: ['L', 'R'] },
  { value: 'stereo_sub', channels: ['L', 'R', 'Sub'] },
  { value: 'lcr', channels: ['L', 'C', 'R'] },
  { value: 'lcr_sub', channels: ['L', 'C', 'R', 'Sub'] },
  { value: '5.1', channels: ['L', 'R', 'C', 'LFE', 'Ls', 'Rs'] },
  { value: '7.1', channels: ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lb', 'Rb'] },
  { value: '7.1.2', channels: ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lb', 'Rb', 'Ltf', 'Rtf'] },
];
export const busChannelsFor = (mode) => OUTPUT_MODES.find((m) => m.value === mode)?.channels || [];

// The device type to give gear imported from a Stockwire product, from its category path.
export function deviceTypeFromCategory(category) {
  const c = String(category || '').toLowerCase();
  if (/ptz/.test(c)) return 'ptz_camera';
  if (/camera/.test(c)) return 'camera';
  if (/projector/.test(c)) return 'projector';
  if (/screen|display|monitor|led wall/.test(c)) return 'screen';
  if (/switcher|vision mixer/.test(c)) return 'switcher';
  if (/mixer|console/.test(c)) return 'mixer';
  return 'other';
}

// The output patch points a speaker can be fed from: each point of each output's chain, labelled
// "output - label or connector - device" and valued with the legacy point id the element links to.
export function outputPointOptions(devices, edges) {
  const names = new Map(devices.map((d) => [d.id, d.name]));
  const options = [];
  for (const out of devices.filter((d) => d.kind === 'output')) {
    for (const edge of edges) {
      const attrs = edge.attributes || {};
      if (attrs.chain !== out.id) continue;
      const point = attrs.first_point || attrs;
      if (!point.point_id) continue;
      const device = names.get(attrs.first_point ? edge.src_device_id : edge.dst_device_id);
      const bits = [out.name, point.patch_label || point.connector, device].filter(Boolean);
      options.push({ value: point.point_id, label: bits.join(' · ') });
    }
  }
  return options;
}

// Stereo pairing links two neighbouring channels (odd/even) as the L and R of one source. The pair
// is stored on both rows (stereo + stereo_channel = the other's number) and the lower number is
// L. The label gets a " L"/" R" suffix on both rows; the suffix is stripped first so toggling or
// renumbering never stacks suffixes. The partner is created when it does not exist yet and
// inherits the main row's input type, connector and phantom power, because both legs are the
// same source. Unpairing clears both rows but leaves the labels the user may have edited.
export const stripStereoSuffix = (label) => (label || '').replace(/\s+(L|R)$/, '');

export function stereoPairPlan(channel, channels, on) {
  const attrs = channel.attributes || {};
  const number = Number(attrs.channel_number);
  const partnerNumber = Number(attrs.stereo_channel) || (number % 2 === 0 ? number - 1 : number + 1);
  const partner =
    channels.find((c) => c.id !== channel.id && c.attributes?.channel_number === partnerNumber) || null;
  if (!on) {
    return {
      partner,
      main: { attributes: { stereo: false, stereo_channel: null } },
      partnerChanges: partner ? { attributes: { stereo: false, stereo_channel: null } } : null,
      partnerCreate: null,
    };
  }
  const lowerIsMain = number < partnerNumber;
  const base = stripStereoSuffix(channel.name) || `Input ${number}`;
  const shared = {
    input_type: attrs.input_type ?? null,
    connector: attrs.connector ?? null,
    phantom_power: !!attrs.phantom_power,
  };
  return {
    partner,
    partnerNumber,
    main: {
      name: `${base} ${lowerIsMain ? 'L' : 'R'}`,
      attributes: { stereo: true, stereo_channel: partnerNumber },
    },
    partnerChanges: partner
      ? {
          name: `${base} ${lowerIsMain ? 'R' : 'L'}`,
          attributes: { ...shared, stereo: true, stereo_channel: number },
        }
      : null,
    partnerCreate: partner
      ? null
      : {
          channel_number: partnerNumber,
          source_label: `${base} ${lowerIsMain ? 'R' : 'L'}`,
          ...shared,
          stereo: true,
          stereo_channel: number,
        },
  };
}

// The L/R badge of a stereo channel and whether its partner sits directly above or below it, for
// the link line between the two rows. A channel whose partner is gone reads as mono.
export function stereoView(channel, channels) {
  const attrs = channel.attributes || {};
  if (!attrs.stereo || !attrs.stereo_channel) return { linked: false };
  const isL = attrs.channel_number < attrs.stereo_channel;
  const idx = channels.findIndex((c) => c.id === channel.id);
  const partner = channels.find((c) => c.attributes?.channel_number === attrs.stereo_channel);
  return {
    linked: !!partner,
    isL,
    partner: attrs.stereo_channel,
    top: isL && channels[idx + 1]?.id === partner?.id,
    bottom: !isL && channels[idx - 1]?.id === partner?.id,
  };
}

// A mixer product's size from its Stockwire specs: the spec keys differ between categories (a
// console has inputs/outputs, a stagebox sb_inputs/sb_outputs), so both are read. null means the
// product does not say, and the user types it instead.
export function mixerSpecsOf(product) {
  const specs = product?.specs || {};
  return { inputs: specs.inputs ?? specs.sb_inputs ?? null, buses: specs.outputs ?? specs.sb_outputs ?? null };
}

// The empty inputs and outputs a list needs to match its mixer. It only ever adds: existing
// channels keep their numbers and outputs, so nothing a user filled in can be lost. A stereo bus
// is two mixer outputs (L and R), so buses are counted in output channels, not rows.
export function mixerSlotsToAdd(channels, outputs, wantInputs, wantBuses) {
  const top = channels.reduce((m, c) => Math.max(m, Number(c.attributes?.channel_number) || 0), 0);
  const missingInputs = Math.max(0, wantInputs - channels.length);
  const used = outputs.reduce((sum, o) => sum + (busChannelsFor(o.attributes?.mode).length || 1), 0);
  const missingBuses = Math.max(0, wantBuses - used);
  return {
    channels: Array.from({ length: missingInputs }, (_, i) => ({ channel_number: top + i + 1 })),
    outputs: Array.from({ length: missingBuses }, (_, i) => ({ name: `Out ${outputs.length + i + 1}`, mode: 'mono' })),
  };
}

// How much of each port of a device the graph's connections use. A port with a channel count
// (a stagebox's 32 XLR inputs) is used up channel by channel; any other port takes one connection
// per edge up to its max_connections (default 1), the same limits topology.py enforces when a
// connection is made. An "in" port counts the edges that end on it, an "out" port those that
// start there, and a "both" port either; the port id is what an edge names in src_port/dst_port.
export function portUsage(device, edges) {
  return (device?.ports || []).map((port) => {
    const mine = edges.filter(
      (e) =>
        (port.direction !== 'in' && e.src_device_id === device.id && e.src_port === port.id) ||
        (port.direction !== 'out' && e.dst_device_id === device.id && e.dst_port === port.id),
    );
    const byChannel = port.channels != null;
    return {
      id: port.id,
      direction: port.direction,
      connector: port.connector || '',
      capacity: byChannel ? Number(port.channels) : Number(port.max_connections || 1),
      used: byChannel ? mine.reduce((sum, e) => sum + Number(e.channels || 1), 0) : mine.length,
    };
  });
}

// Which value a device's weight or power really uses, for the hint under the field: the number
// from the linked Stockwire product, the one typed in here, or none. `source` is what the server's
// effective values report (stockwire | manual | null), so a value typed in the dialog is still
// shown as the Stockwire one until it is saved.
export function physicalHintKey(effective, valueKey, sourceKey) {
  const source = effective?.[sourceKey];
  if (source === 'stockwire') return { key: 'devices.stockwireInUse', value: effective[valueKey] };
  if (source === 'manual') return { key: 'devices.manualInUse' };
  return { key: 'devices.notSet' };
}
