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

// Names of the devices a channel or output chain passes through, in order.
export function chainSteps(node, edges, devices) {
  const names = new Map(devices.map((d) => [d.id, d.name]));
  const steps = [];
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (attrs.chain !== node.id) continue;
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

export const nextChannelNumber = (channels) =>
  channels.reduce((max, c) => Math.max(max, c.attributes?.channel_number || 0), 0) + 1;

// Steps the chain dialog edits, rebuilt from the graph so saving sends the whole chain.
export function chainForm(node, edges, devices) {
  const byPos = [];
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (attrs.chain !== node.id) continue;
    const point = attrs.first_point || attrs;
    byPos.push({
      position: point.position || 0,
      device_id: attrs.first_point ? edge.src_device_id : edge.dst_device_id,
      connector: point.connector || '',
      patch_label: point.patch_label || '',
      notes: point.notes || '',
      point_id: point.point_id,
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
      notes: p.notes,
      parent_index: p.parent_id && index.has(p.parent_id) ? index.get(p.parent_id) : null,
    }));
}
