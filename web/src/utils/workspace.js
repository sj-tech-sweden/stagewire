export const DOMAINS = ['audio', 'lighting', 'video', 'power'];

export const DOMAIN_SIGNAL = { audio: 'audio', lighting: 'dmx', video: 'video', power: 'power' };

export function stockwireAssetOf(device) {
  const attributes = device?.attributes || {};
  // Read the old attribute for existing bindings; new writes use stockwire_device_id.
  const canonicalId = device?.stockwire_device_id || null;
  const code =
    attributes.stockwire_asset_code ||
    attributes.stockwire_asset_id ||
    canonicalId ||
    null;
  const tag = attributes.stockwire_asset_tag || null;
  const serial = attributes.stockwire_asset_serial || null;
  const barcode = attributes.stockwire_asset_barcode || null;
  const qrCode = attributes.stockwire_asset_qr_code || null;
  const rfid = attributes.stockwire_asset_rfid || null;
  return {
    isBound: Boolean(canonicalId || code || tag || serial || barcode || qrCode || rfid),
    canonicalId: canonicalId == null ? null : String(canonicalId),
    code,
    tag,
    serial,
    barcode,
    qrCode,
    rfid,
    description: attributes.stockwire_asset_description || null,
  };
}

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
  const domain = domainForCategory(product.category);
  const inlet = String(product.specs?.power_inlet || '').trim().toLowerCase();
  if (inlet) attributes.power_inlet = inlet;
  // Passive source gear (microphones, mic stands, DIs, instruments) takes no power by default.
  // An explicit product spec (e.g. a powered speaker) wins; clearly-powered categories (amplifiers,
  // active/powered boxes) are left for the user to set rather than assumed passive.
  else if (domain === 'audio' && !/amplif|powered|active/i.test(String(product.category || '')))
    attributes.power_inlet = 'none';
  // The same passive source gear carries a single XLR output by default; an explicit product spec
  // (its connectors or channel counts) still wins.
  const specGroups = connectorGroupsFromProduct(product).map((g) => ({
    ...g,
    signal: g.signal || DOMAIN_SIGNAL[domain] || 'audio',
  }));
  if (
    !specGroups.length &&
    domain === 'audio' &&
    !/amplif|powered|active|mixer|console|stagebox|split|patchbay/i.test(String(product.category || ''))
  ) {
    specGroups.push({ connector: 'xlr3', direction: 'out', count: 1, signal: 'audio' });
  }
  return {
    domain,
    kind: product.category || '',
    name: product.name || product.sku || 'Item',
    attributes,
    ports: portsFromGroups(specGroups, [], ''),
    case_parent_id: parentId,
    stockwire_product_id: product.id != null ? String(product.id) : null,
    stockwire_product_name: product.name || null,
    stockwire_device_id: product.device_id != null ? String(product.device_id) : null,
    stockwire_booked: product.booked ?? null,
  };
}

export function edgeRows(edges, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  return edges.map((e) => {
    const source = byId.get(e.src_device_id);
    const destination = byId.get(e.dst_device_id);
    const attributes = e.attributes || {};
    return {
      id: e.id,
      signal: e.signal,
      srcId: e.src_device_id,
      dstId: e.dst_device_id,
      from: source?.name || '?',
      fromPort: portLabelOf(source, e.src_port, attributes.src_socket || null),
      to: destination?.name || '?',
      toPort: portLabelOf(destination, e.dst_port, attributes.dst_socket || null),
      patchLabel: attributes.patch_label || '',
      connector: attributes.connector || '',
      routeLabel: [attributes.patch_label, attributes.connector].filter(Boolean).join(' · '),
      channels: e.channels,
      phase: e.phase,
      cableLabel: e.cable_label,
      revision: e.revision,
    };
  });
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
    if (node.kind === 'channel') {
      const deviceId = edge.src_device_id === node.id ? edge.dst_device_id : edge.src_device_id;
      steps.push({ position: attrs.position || 0, device: byId.get(deviceId) });
    } else if (attrs.first_point) {
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
    if (node.kind === 'channel') {
      const deviceId = edge.src_device_id === node.id ? edge.dst_device_id : edge.src_device_id;
      steps.push({ position: attrs.position || 0, name: names.get(deviceId) });
    } else if (attrs.first_point) {
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

// Signals that run over a cable a stagebox can reach the mixer on: audio (analog or Dante/AES50/
// MADI over the network) and data (the ethernet switch fabric in between). Power, video, DMX and
// plot links are not part of the path a mic signal takes to the console.
const FEED_SIGNALS = new Set(['audio', 'data']);
export const isStagebox = (d) =>
  d.kind === 'digital_stagebox' ||
  d.kind === 'analog_stagebox' ||
  d.device_type === 'digital_stagebox' ||
  d.device_type === 'analog_stagebox';
export const isMixerDevice = (d) => d.kind === 'mixer' || d.device_type === 'mixer';

// The stageboxes that reach a mixer, directly or indirectly: a stagebox patched into the mixer (or
// one of its channels) with an audio cable, or through any chain of network gear (switches,
// routers, computers) in between. The walk is undirected over audio/data edges, never expands into
// virtual nodes (channels, buses) and never passes through another console, so a stagebox that
// feeds a different mixer is not claimed by this one.
export function feedingStageboxes(mixer, devices, edges) {
  if (!mixer) return [];
  const byId = new Map(devices.map((d) => [d.id, d]));
  const listId = mixer.sound_list_id;
  const start = new Set([mixer.id, ...channelsOf(devices, listId).map((c) => c.id)]);
  const seen = new Set(start);
  const queue = [...start];
  const found = new Map();
  while (queue.length) {
    const id = queue.shift();
    for (const e of edges) {
      if (!FEED_SIGNALS.has(e.signal)) continue;
      let next = null;
      if (e.src_device_id === id) next = e.dst_device_id;
      else if (e.dst_device_id === id) next = e.src_device_id;
      if (!next || seen.has(next)) continue;
      const dev = byId.get(next);
      if (!dev) continue;
      seen.add(next);
      if (isStagebox(dev)) {
        found.set(next, dev);
        continue; // a stagebox is an end of the walk: its own inputs are the stage side
      }
      if (isVirtual(dev) || isMixerDevice(dev)) continue;
      queue.push(next);
    }
  }
  return [...found.values()];
}

// The physical inputs a channel can be fed from, as a strict dropdown: the mixer's own input ports
// plus the input ports of every stagebox that reaches the mixer (feedingStageboxes). Each port
// carrying a channel count expands into its individual physical sockets — an 8-channel XLR group
// becomes "XLR in 1" … "XLR in 8" — so a channel maps to one specific physical input.
export function mixerInputChoices(channel, devices, edges) {
  const listId = channel?.attributes?.list_id;
  if (!listId) return [];
  const mixer = devices.find((d) => isMixerDevice(d) && d.sound_list_id === listId);
  if (!mixer) return [];
  const choices = [];
  const seen = new Set();
  const add = (label) => {
    if (seen.has(label)) return;
    seen.add(label);
    choices.push({ label, value: label });
  };
  for (const dev of [mixer, ...feedingStageboxes(mixer, devices, edges)]) {
    const tag = dev === mixer ? '' : ` (${dev.name})`;
    for (const p of dev.ports || []) {
      if (p.direction !== 'in') continue;
      const conn = (p.connector || 'in').toUpperCase();
      const n = Number(p.channels) || 1;
      for (let i = 1; i <= n; i += 1) add(`${conn} in ${i}${tag}`);
    }
  }
  return choices;
}

// The label a port shows in the signal flow: the port's own label when it has one, else its
// connector ("XLR out"), never the raw generated id ("out-xlr3") alone.
export function portLabelOf(device, portId, socket = null) {
  const port = (device?.ports || []).find((p) => p.id === portId);
  let label;
  if (port?.label) label = port.label;
  else if (port?.connector) label = `${port.connector.toUpperCase()} ${port.direction || ''}`.trim();
  else label = portId || '';
  return socket ? `${label} ${socket}` : label;
}

// A port with several channels is a row of physical sockets (XLR in 1 … XLR in 32). Each socket is
// an option valued `<portId>#<n>`; a single-channel port stays one option valued by its id. Used
// by the connect form, so a mic can be cabled to one specific input of a stagebox.
export function socketOptions(device, direction) {
  const options = [];
  for (const p of device?.ports || []) {
    if (p.direction !== direction) continue;
    const count = Number(p.channels) || 1;
    const conn = (p.connector || direction).toUpperCase();
    if (count <= 1) {
      options.push({ label: `${p.id}${p.connector ? ` (${p.connector})` : ''}`, value: p.id });
      continue;
    }
    for (let i = 1; i <= count; i += 1) {
      options.push({ label: `${conn} ${direction} ${i}`, value: `${p.id}#${i}` });
    }
  }
  return options;
}

// Splits a socket option value into its port id and socket number (null for a plain port).
export function splitSocket(value) {
  const text = String(value ?? '');
  const at = text.lastIndexOf('#');
  if (at < 0) return { port: text, socket: null };
  return { port: text.slice(0, at), socket: Number(text.slice(at + 1)) || null };
}

// The cables a node has outside its patch chain (drawn in the inspector, not the chain editor), one
// line per cable, read from the graph edges: the node's own port, the other device and its port.
function mixerForChannel(channel, devices) {
  const listId = channel?.kind === 'channel' ? channel.attributes?.list_id : null;
  return listId
    ? devices.find(
        (device) =>
          isMixerDevice(device) && String(device.sound_list_id) === String(listId),
      )
    : null;
}

export function directConnections(node, edges, devices) {
  if (!node) return [];
  const byId = new Map(devices.map((d) => [d.id, d]));
  const ownerMixer = mixerForChannel(node, devices);
  return edges
    .filter(
      (e) =>
        FEED_SIGNALS.has(e.signal) &&
        !e.attributes?.chain &&
        !(ownerMixer && e.src_device_id === node.id && e.dst_device_id === ownerMixer.id) &&
        (e.src_device_id === node.id || e.dst_device_id === node.id),
    )
    .map((e) => {
      const incoming = e.dst_device_id === node.id;
      const other = byId.get(incoming ? e.src_device_id : e.dst_device_id);
      const socket = e.attributes?.dst_socket || null;
      const nodePort = incoming ? portLabelOf(node, e.dst_port, socket) : portLabelOf(node, e.src_port);
      const otherPort = incoming
        ? portLabelOf(other, e.src_port)
        : portLabelOf(other, e.dst_port, socket);
      const otherName = other?.name || '?';
      const text = incoming
        ? `${otherName} ${otherPort} → ${node.name} ${nodePort}`
        : `${node.name} ${nodePort} → ${otherName} ${otherPort}`;
      return { id: e.id, incoming, other: otherName, text };
    });
}

// The Patch column: what the node is connected to, upstream feeds first, then its patch chain, then
// cables out. A node with inspector cables includes its own name so the chain reads through it.
export function patchSummary(node, edges, devices) {
  const direct = directConnections(node, edges, devices);
  const chain = chainSteps(node, edges, devices);
  if (node.kind === 'channel') {
    const byId = new Map(devices.map((d) => [d.id, d]));
    const sourceId = node.attributes?.source_device_id;
    const source = byId.get(sourceId)?.name || node.attributes?.device || '';
    const upstream = source
      ? [source]
      : direct.filter((connection) => connection.incoming).map((connection) => connection.other);
    const inputPath =
      upstream.length || chain.length ? [...upstream, ...chain, node.name].join(' → ') : '';
    const outputPaths = direct
      .filter((connection) => !connection.incoming)
      .map((connection) => `${node.name} → ${connection.other}`);
    return [inputPath, ...outputPaths].filter(Boolean).join(' / ');
  }
  if (!direct.length) return chain.join(' → ');
  const upstream = direct.filter((d) => d.incoming).map((d) => d.other);
  const downstream = direct.filter((d) => !d.incoming).map((d) => d.other);
  return [...upstream, node.name, ...chain, ...downstream].join(' → ');
}

// --- soft patch in the signal flow / chain editor -----------------------------------------------
// A channel's soft patch (`attributes.dsp_source` {device_id, port_id, socket}) is mirrored by the
// server into its patch chain as the LAST hop: the device whose socket feeds the DSP strip. The
// source (microphone) is at the other end and any analog hops (snakes, splitters, patch panels) sit
// between them. These helpers find that hop and describe it; the server enforces the order too.

// Index of the soft-patched hop among chain `steps` (the last one for that device), or -1.
export function lockedStepIndex(channel, steps) {
  const ref = channel?.attributes?.dsp_source;
  if (!ref?.device_id || !steps?.length) return -1;
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    if (String(steps[i].device_id) === String(ref.device_id)) return i;
  }
  return -1;
}

// `steps` with the soft-patched hop moved to the end (a copy; unchanged when there is none or it is
// already last). Every step is kept, only the order changes.
export function withLockedLast(channel, steps) {
  const at = lockedStepIndex(channel, steps);
  if (at < 0 || at === steps.length - 1) return [...(steps || [])];
  return [...steps.slice(0, at), ...steps.slice(at + 1), steps[at]];
}

// What the locked hop shows: socket number, the port's connector and the label "In 5 (XLR3)".
export function softPatchInfo(channel, devices) {
  const ref = channel?.attributes?.dsp_source;
  if (!ref?.device_id) return null;
  const device = (devices || []).find((d) => d.id === ref.device_id);
  const port = (device?.ports || []).find((p) => p.id === ref.port_id);
  const connector = (port?.connector || '').toUpperCase();
  const socket = ref.socket || 1;
  return {
    device_id: ref.device_id,
    device_name: device?.name || '',
    socket,
    connector,
    label: `In ${socket}${connector ? ` (${connector})` : ''}`,
  };
}

// The chain a channel's chain dialog starts from: its steps with the soft-patched hop last and
// flagged `locked`. When the chain lost that hop (it was edited elsewhere) it is put back, so saving
// never drops the strip-side hop (the server would then clear the soft patch).
export function chainStepsWithLock(channel, steps, devices) {
  const info = softPatchInfo(channel, devices);
  if (!info) return steps.map((s) => ({ ...s }));
  const ordered = withLockedLast(channel, steps);
  const at = lockedStepIndex(channel, ordered);
  if (at >= 0) return ordered.map((s, i) => ({ ...s, locked: i === at }));
  return [
    ...ordered.map((s) => ({ ...s })),
    {
      device_id: info.device_id,
      connector: info.connector.toLowerCase(),
      patch_label: `In ${info.socket}`,
      in_port: '',
      out_port: '',
      notes: '',
      parent_index: null,
      locked: true,
    },
  ];
}

// The channel's selected source and explicit patch points define its input route. Other cables
// connected to the channel remain separate branches; a physical device does not imply port routing.
export function channelFlowTree(channel, edges, devices, sourceLabel, steps = []) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  const sourceId = channel.attributes?.source_device_id;
  const ownerMixer = mixerForChannel(channel, devices);
  const pointEdges = edges.filter((edge) => edge.attributes?.chain === channel.id);
  const orderedPointEdges = [...pointEdges].sort(
    (a, b) => (a.attributes?.position || 0) - (b.attributes?.position || 0),
  );
  const pointEdgeFor = (index) => {
    const point = steps[index];
    const nextId = steps[index + 1]?.device_id || channel.id;
    const edgeAtPosition = orderedPointEdges[index];
    if (
      edgeAtPosition?.src_device_id === point.device_id &&
      edgeAtPosition?.dst_device_id === nextId
    ) {
      return edgeAtPosition;
    }
    return pointEdges.find(
      (edge) => edge.src_device_id === point.device_id && edge.dst_device_id === nextId,
    );
  };
  const sourceEdge = edges.find(
    (edge) =>
      edge.signal === 'audio' &&
      ((edge.attributes?.channel_source &&
        String(edge.attributes.channel_id) === String(channel.id)) ||
        (sourceId &&
          edge.src_device_id === sourceId &&
          [steps[0]?.device_id, channel.id].includes(edge.dst_device_id))),
  ) || edges.find(
    (edge) =>
      steps.length > 0 &&
      // the console's own link to a stagebox (dSNAKE / Dante / ethernet) carries the stagebox's
      // return, it is not where this channel's signal comes from
      edge.src_device_id !== ownerMixer?.id &&
      FEED_SIGNALS.has(edge.signal) &&
      edge.dst_device_id === steps[0].device_id &&
      !edge.attributes?.chain &&
      byId.has(edge.src_device_id) &&
      !steps.some((step) => step.device_id === edge.src_device_id),
  );
  // The source is the linked gear, else a feeding device found by the edges, else - for a mic that
  // is only named in the Source device field (no gear linked) - a label-only source, so the flow
  // always starts at the microphone the patch summary names.
  const typedSource = String(channel.attributes?.device || '').trim();
  const sourceDevice =
    byId.get(sourceId) ||
    byId.get(sourceEdge?.src_device_id) ||
    (typedSource ? { id: `source-text-${channel.id}`, name: typedSource } : null);
  const incomingEdges = edges.filter(
    (edge) =>
      FEED_SIGNALS.has(edge.signal) &&
      edge.dst_device_id === channel.id &&
      !edge.attributes?.chain &&
      byId.has(edge.src_device_id),
  );
  const directFeeds =
    steps.length || sourceDevice
      ? []
      : incomingEdges.map((edge) => ({ edge, device: byId.get(edge.src_device_id) }));
  const soft = softPatchInfo(channel, devices);
  const softIndex = lockedStepIndex(channel, steps);
  // The end of the flow is the mixer strip: "Console · Ch 5 Vox", with the last cable's connector
  // and (for a soft-patched strip) its "In 5" label on the cable into the channel.
  const stripName = sourceLabel || channel.name;
  const stripLabel = ownerMixer
    ? `${ownerMixer.name} · Ch ${channel.attributes?.channel_number ?? ''} ${stripName}`.replace(/\s+/g, ' ').trim()
    : stripName;
  const endpoint = (id, edge = null) => ({
    id,
    device_id: channel.id,
    label: stripLabel,
    kind: 'channel',
    in_port: edge
      ? portLabelOf(channel, edge.dst_port, edge.attributes?.dst_socket || null)
      : '',
    out_port: '',
    connector: steps.at(-1)?.connector || channel.attributes?.input_type || '',
    patch_label: softIndex === steps.length - 1 && soft ? steps.at(-1)?.patch_label || `In ${soft.socket}` : '',
    children: [],
  });
  const routes = [];
  if (steps.length || sourceDevice) {
    const finalEdge = steps.length ? pointEdgeFor(steps.length - 1) : sourceEdge;
    let route = endpoint(`channel-${channel.id}`, finalEdge);
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      const step = steps[index];
      const device = byId.get(step.device_id);
      const incoming = index === 0 ? sourceEdge : pointEdgeFor(index - 1);
      const outgoing = pointEdgeFor(index);
      route = {
        id: `channel-step-${channel.id}-${index}`,
        device_id: step.device_id || null,
        label: device?.name || '?',
        kind: 'device',
        in_port:
          incoming?.dst_device_id === device?.id
            ? portLabelOf(device, incoming.dst_port, incoming.attributes?.dst_socket || null)
            : step.in_port || '',
        out_port:
          outgoing?.src_device_id === device?.id
            ? portLabelOf(device, outgoing.src_port)
            : step.out_port || '',
        connector: step.connector || '',
        patch_label: step.patch_label || '',
        // the soft-patched hop shows the real input socket it is plugged into: "XLR3 in 5"
        ...(soft && index === softIndex
          ? {
              soft_patch: {
                connector: soft.connector || (step.connector || '').toUpperCase(),
                socket: soft.socket,
              },
            }
          : {}),
        children: [route],
      };
    }
    if (sourceDevice && sourceDevice.id !== steps[0]?.device_id) {
      route = {
        id: `channel-source-${channel.id}`,
        device_id: sourceDevice.id,
        label: sourceDevice.name,
        kind: 'source',
        in_port: '',
        out_port:
          sourceEdge?.src_device_id === sourceDevice.id
            ? portLabelOf(sourceDevice, sourceEdge.src_port)
            : '',
        connector: '',
        children: [route],
      };
    }
    routes.push(route);
  } else {
    routes.push(
      ...directFeeds.map(({ edge, device }, index) => ({
        id: `channel-feed-${edge.id}`,
        device_id: device.id,
        label: device.name,
        kind: 'source',
        in_port: '',
        out_port: portLabelOf(device, edge.src_port),
        connector: '',
        children: [
          endpoint(`channel-${channel.id}-feed-${index}`, edge),
        ],
      })),
    );
  }
  for (const edge of edges.filter(
    (item) =>
      FEED_SIGNALS.has(item.signal) &&
      item.src_device_id === channel.id &&
      item.dst_device_id !== ownerMixer?.id &&
      !item.attributes?.chain &&
      byId.has(item.dst_device_id),
  )) {
    const destination = byId.get(edge.dst_device_id);
    routes.push({
      id: `channel-output-${edge.id}`,
      device_id: channel.id,
      label: sourceLabel || channel.name,
      kind: 'channel',
      in_port: '',
      out_port: portLabelOf(channel, edge.src_port),
      connector: '',
      children: [
        {
          id: `channel-output-device-${edge.id}`,
          device_id: destination.id,
          label: destination.name,
          kind: 'device',
          in_port: portLabelOf(destination, edge.dst_port, edge.attributes?.dst_socket || null),
          out_port: '',
          connector: edge.attributes?.connector || '',
          patch_label: edge.attributes?.patch_label || '',
          children: [],
        },
      ],
    });
  }
  return routes.length ? routes : [endpoint(`channel-${channel.id}`)];
}

// Return only the channel routes that actually contain a device. A gear node may be used by
// several channels, so each matching channel keeps its own diagram instead of joining nearby
// graph edges into an implied signal path.
export function channelFlowsForDevice(deviceId, devices, edges) {
  if (!deviceId) return [];
  return devices
    .filter((device) => device.kind === 'channel')
    .flatMap((channel) => {
      const routes = channelFlowTree(
        channel,
        edges,
        devices,
        channel.name,
        chainForm(channel, edges, devices),
      );
      const containsDevice = (nodes) =>
        nodes.some(
          (node) =>
            node.device_id === deviceId ||
            containsDevice(node.children || []),
        );
      return containsDevice(routes) ? [{ channel, routes }] : [];
    });
}

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
      device_id:
        node.kind === 'channel'
          ? edge.src_device_id === node.id
            ? edge.dst_device_id
            : edge.src_device_id
          : attrs.first_point
            ? edge.src_device_id
            : edge.dst_device_id,
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

// Audio gear that is actively powered (needs a mains inlet) versus passive source gear
// (microphones, mic stands, DIs, instruments). Passive gear defaults to no power inlet.
export const POWERED_AUDIO_TYPES = new Set([
  'mixer',
  'switcher',
  'router',
  'multiviewer',
  'digital_stagebox',
  'analog_stagebox',
  'split',
  'patchbay',
  'converter',
  'encoder',
  'network',
  'computer',
  'recorder',
]);

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

// --- a device typed into the Edit patch dialog ----------------------------------------------------
// A step's device may be a name that is neither a job device nor a catalog product. It is made into
// a real device with exactly that name when the chain is saved (see ChainDialog). Gear in the middle
// of a path passes signal through, so it gets BOTH an input and an output connector group; a name
// that says what it is ("Snake 16", "Splitter", "Patch panel") also gets the matching type, port
// count and (for passive snakes and patch panels) no power inlet.
export const NEW_DEVICE_PREFIX = 'new:';
export const newDeviceValue = (name) => `${NEW_DEVICE_PREFIX}${String(name || '').trim()}`;
export const isNewDeviceValue = (value) => typeof value === 'string' && value.startsWith(NEW_DEVICE_PREFIX);
export const newDeviceName = (value) => (isNewDeviceValue(value) ? value.slice(NEW_DEVICE_PREFIX.length).trim() : '');

// The job device that already carries exactly this name (case-insensitive), so typing it picks the
// existing one instead of making a duplicate.
export function findDeviceByName(devices, name) {
  const needle = String(name || '').trim().toLowerCase();
  if (!needle) return null;
  return (devices || []).find((d) => String(d.name || '').trim().toLowerCase() === needle) || null;
}

// Type, ports and power for a typed chain device, guessed from its name. Never throws; an unknown
// name is a plain pass-through 'other' device with one XLR in and one out.
export function guessChainDevice(name) {
  const text = String(name || '').trim();
  const lower = text.toLowerCase();
  let device_type = 'other';
  let passive = false;
  if (/split/.test(lower)) {
    device_type = 'split';
    passive = !/active|powered/.test(lower);
  } else if (/patch/.test(lower)) {
    device_type = 'patchbay';
    passive = true;
  } else if (/snake|multicore|multi-core/.test(lower)) {
    device_type = 'analog_stagebox';
    passive = !/digital|dante|dsnake|d-snake|avb|madi/.test(lower);
  } else if (/stagebox|stage box/.test(lower)) {
    device_type = /digital|dante|dsnake|d-snake|avb|madi/.test(lower) ? 'digital_stagebox' : 'analog_stagebox';
  }
  // "Snake 16", "16ch snake", "AR2412" is left alone (a model number, not a channel count)
  const match = lower.match(/(?:^|[^a-z0-9])(\d{1,2})(?:\s*(?:ch|channels?|in|x|-?way))?(?:$|[^a-z0-9])/);
  const count = match && Number(match[1]) >= 2 && Number(match[1]) <= 64 ? Number(match[1]) : 1;
  return {
    device_type,
    count,
    passive,
    ports: [
      { direction: 'in', connector: 'xlr3', count },
      { direction: 'out', connector: 'xlr3', count },
    ],
  };
}

// The create-endpoint body for a typed chain device (see guessChainDevice).
export function newChainDeviceBody(name) {
  const guess = guessChainDevice(name);
  const form = deviceForm(null);
  form.name = String(name || '').trim();
  form.device_type = guess.device_type;
  form.ports = guess.ports;
  if (guess.passive) form.power_inlet = 'none';
  return deviceCreateBody(form);
}

// The device options of a step's picker plus, for typed text that is not an existing device,
// a leading 'Create "<text>"' option (value `new:<text>`), labelled by `label(text)`.
export function chainDeviceOptions(options, needle, label) {
  const text = String(needle || '').trim();
  const lower = text.toLowerCase();
  const matches = (options || []).filter((o) => String(o.label || '').toLowerCase().includes(lower));
  if (!text || (options || []).some((o) => String(o.label || '').trim().toLowerCase() === lower)) return matches;
  return [{ label: label(text), value: newDeviceValue(text), create: true }, ...matches];
}

// Graph ports for a mixer imported from Stockwire. The import yields editor connector groups
// (direction in/out/both); the graph PATCH only accepts ports with an id and an in|out direction,
// so a 'both' group (the GLD-80's etherCON, a dSNAKE port) is expanded to an in and an out port and
// the device's own generic ports are kept. Empty when the product states no connectors.
export const mixerGraphPorts = (groups, existingPorts) =>
  groups?.length ? portsFromGroups(groups, existingPorts, 'mixer') : [];

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
  // A channel/video list that minted this device (e.g. an auto-created mixer) travels with it so
  // the backend can link the gear back to the list and the frontend can find it again.
  if (form.sound_list_id) body.sound_list_id = form.sound_list_id;
  if (form.video_list_id) body.video_list_id = form.video_list_id;
  const map = { power_w: 'power_watts' };
  for (const key of [...NUMBER_FIELDS, ...TEXT_FIELDS]) {
    const value = form[key];
    if (value !== null && value !== '' && value !== undefined) body[map[key] || key] = value;
  }
  // Passive source gear (microphones, mic stands, DIs, instruments) takes no power by default;
  // only actively-powered audio boxes keep the inherited IEC C13 inlet. An explicit inlet (e.g. from
  // a product spec) always wins.
  if (
    !body.power_inlet &&
    signalForType(form.device_type) === 'audio' &&
    !POWERED_AUDIO_TYPES.has(form.device_type)
  ) {
    body.power_inlet = 'none';
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
  // Passive source gear (microphones, mic stands, DIs, instruments) takes no power by default.
  // An explicit product spec (e.g. a powered speaker) still wins over this default.
  if (
    !form.power_inlet &&
    signalForType(form.device_type) === 'audio' &&
    !POWERED_AUDIO_TYPES.has(form.device_type)
  ) {
    form.power_inlet = 'none';
  }
  // The same passive source gear carries a single XLR output by default so a patch has somewhere
  // to start; an explicit product spec (its connectors or channel counts) always wins.
  if (
    !form.ports.length &&
    signalForType(form.device_type) === 'audio' &&
    !POWERED_AUDIO_TYPES.has(form.device_type)
  ) {
    form.ports = addConnector(form.ports, { connector: 'xlr3', direction: 'out', count: 1 });
  }
  return form;
}

// A chain as a tree for the flow diagram: the source (channel, input or output) first, then the
// devices. `steps` are chain-dialog steps (chainForm / videoChainForm). A step takes its signal
// from `parent_index`; without one it follows the previous step, except in a video output where
// a step without a parent starts its own branch (`separateRoots`).
export function flowTree(sourceLabel, steps, devices, { separateRoots = false } = {}) {
  const nodes = steps.map((step, i) => ({
    id: `step-${i}`,
    // the device node behind the box, so the flow can open it for editing
    device_id: step.device_id || null,
    label: devices.find((d) => d.id === step.device_id)?.name || '?',
    kind: 'device',
    in_port: step.in_port || step.input_port || '',
    out_port: step.out_port || step.source_port || '',
    connector: step.connector || '',
    patch_label: step.patch_label || '',
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
// renumbering never stacks suffixes. The partner is created when it does not exist yet, with just
// its number and name: input type, connector, patch and socket are per leg (each is its own
// preamp, possibly on another stagebox). What the link binds is done by the server once linked:
// the secondary follows the primary's name (keeping its side: "Keys L" -> "Keys R"), colour,
// instrument group and +48V, so the secondary's 48V checkbox is read-only. Unpairing clears both
// rows but leaves the labels the user may have edited.
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
  // Each leg is its own preamp: input type, connector and +48V are NOT copied to the partner.
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
          attributes: { stereo: true, stereo_channel: number },
        }
      : null,
    partnerCreate: partner
      ? null
      : {
          channel_number: partnerNumber,
          source_label: `${base} ${lowerIsMain ? 'R' : 'L'}`,
          stereo: true,
          stereo_channel: number,
        },
  };
}

// The L/R badge of a stereo channel and whether its partner sits directly above or below it, for
// the link line between the two rows. A channel whose partner is gone reads as mono.
export function stereoView(channel, channels) {
  const attrs = channel.attributes || {};
  // The console link (job lists) is authoritative when present: primary = L, secondary = R.
  if (attrs.is_stereo_linked && attrs.stereo_partner_id) {
    const partner = channels.find((c) => c.id === attrs.stereo_partner_id || c.attributes?.legacy_id === attrs.stereo_partner_id);
    const isL = attrs.stereo_link_role === 'primary';
    const idx = channels.findIndex((c) => c.id === channel.id);
    return {
      linked: !!partner,
      isL,
      partner: partner?.attributes?.channel_number ?? attrs.stereo_channel,
      top: isL && channels[idx + 1]?.id === partner?.id,
      bottom: !isL && channels[idx - 1]?.id === partner?.id,
    };
  }
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

// The propose-mixer response as the dialog shows it: the list's need and one suggestion row per
// candidate console (the candidate's product_id is the row id the picker uses).
export const proposalFromResponse = (data) => ({
  need: data?.need || null,
  suggestions: (data?.candidates || []).map((c) => ({ ...c, id: c.product_id })),
});

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

// What importing a Stockwire mixer adds to a list. `summary` is the console summary returned after
// the product's specs.mixer was read into the list's profile, or null when the product has none
// (then the old padding applies: empty inputs and empty mono outputs up to the flat counts). A
// bus-pool console gets empty inputs up to its DSP mono strips and NO pre-made buses: the pool is a
// budget the engineer spends (20 empty mono buses would burn 20 of a GLD-80's 30 slots before a
// single stereo IEM mix was made). `slots` is the pool size for the user message.
export function mixerImportPlan(channels, outputs, want, summary) {
  const profile = summary?.profile;
  if (!profile?.bus_pool) {
    return { ...mixerSlotsToAdd(channels, outputs, want.inputs, want.buses), busPool: false, slots: null };
  }
  const mono = profile.dsp_inputs?.mono || 0;
  const add = mixerSlotsToAdd(channels, outputs, mono || want.inputs, 0);
  return { channels: add.channels, outputs: [], busPool: true, slots: profile.bus_pool.total_slots };
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

// Whether a device is used by nothing but one channel's source link, so replacing or clearing that
// source can remove it instead of leaving an orphan. Any connection of the device (a chain step, a
// plot link, power) or another node that names it as its source keeps it.
export function isOrphanedBySource(deviceId, channelId, devices, edges) {
  if (edges.some((e) => e.src_device_id === deviceId || e.dst_device_id === deviceId)) return false;
  return !devices.some((d) => d.id !== channelId && d.attributes?.source_device_id === deviceId);
}

// Fader layout draft: {"layer:bank:fader": stripId}. It is the WHOLE layout, not a set of pins on top
// of an automatic fill: a slot that is not in the draft is a blank fader and a strip that is in no
// slot is *unplaced* (it waits in the tray). The server's default fill is only a starting point
// (the map has `custom: false` until a layout is stored) and is laid out again only by "Auto fill"
// / "Place unplaced". A strip may sit on SEVERAL faders (an input on layers 1 and 3, a mix master
// on both banks): placements are simply slots that hold the same id. 'empty' is accepted from older
// saved layouts and means the same as an absent slot.
const holds = (draft, slot) => {
  const value = (draft || {})[slot];
  return !value || value === 'empty' ? null : value;
};

// Put `choice` on `slot`: a strip id (an extra placement; its other faders stay) or 'empty' / null
// (leave this fader blank). `_fader` is unused now (kept so older callers keep working).
export function applyFaderChoice(draft, slot, choice, _fader = null) {
  const next = { ...(draft || {}) };
  if (choice && choice !== 'empty') next[slot] = choice;
  else delete next[slot];
  return next;
}

// Every fader a strip sits on, in surface order: [{slot, layer, bank, fader}]. With a `draft` (while
// editing) that is the draft's own view; with `draft` null it is the saved map as the server sent it.
export function stripPlacements(draft, fader, stripId) {
  const out = [];
  for (const layer of fader?.layers || []) {
    for (const bank of layer.banks) {
      for (const cell of bank.strips) {
        const here = draft ? holds(draft, cell.slot) === stripId : cell.id === stripId;
        if (here) out.push({ slot: cell.slot, layer: layer.layer, bank: bank.label || bank.id, fader: cell.fader });
      }
    }
  }
  return out;
}

// Strips that sit on no fader (the tray's "unplaced"): `strips` is the map's strip list; hidden
// strips (built-in FX nobody set up) are not counted, they are offered separately.
export function unplacedStrips(draft, fader, strips = fader?.strips || []) {
  return strips.filter((st) => !st.hidden && stripPlacements(draft, fader, st.id).length === 0);
}

// Drag and drop on the fader map. `from` is {slot} (a cell was dragged) or {strip} (one was dragged
// from the strip tray). From the tray the strip is ADDED on `toSlot`; whatever sat there loses that
// placement (and is unplaced if it had no other). A dragged cell MOVES its strip (the displaced
// strip, if any, swaps into the fader it came from); with `copy` (Alt/Option or Ctrl/Cmd held) it is
// copied instead and stays put. Other placements of the strip are never touched. Dropping a cell on
// itself, or dragging a blank cell, changes nothing.
export function moveFaderStrip(draft, _fader, from, toSlot, { copy = false } = {}) {
  const stripId = from.slot ? holds(draft, from.slot) : from.strip;
  if (!stripId || from.slot === toSlot) return draft;
  const displaced = holds(draft, toSlot);
  if (displaced === stripId && !from.slot) return draft; // already there
  const next = applyFaderChoice(draft, toSlot, stripId);
  if (from.slot && !copy) {
    if (displaced && displaced !== stripId) next[from.slot] = displaced;
    else delete next[from.slot];
  }
  return next;
}

// Take one fader's placement away (the cell menu's "Remove from this fader"): that fader goes blank
// and the strip's other placements stay. The strip does not reappear anywhere else.
export function removeFaderPlacement(draft, _fader, slot) {
  if (!(slot in (draft || {}))) return draft;
  const next = { ...draft };
  delete next[slot];
  return next;
}

// Dropping on the tray: a dragged cell loses just its own placement; a strip dragged from the tray
// itself (a no-op drop) loses every placement it has.
export function unpinFaderStrip(draft, fader, from) {
  if (from.slot) return removeFaderPlacement(draft, fader, from.slot);
  if (!from.strip) return draft;
  return Object.fromEntries(Object.entries(draft || {}).filter(([, value]) => value !== from.strip));
}

// The draft a loaded fader map starts from: EVERY placed cell, whether the map is a stored layout
// or the live starting point. That is what makes the first edit a take-over: the whole starting
// point is stored with the edit, so nothing the engineer did not touch disappears.
export function faderDraftFromMap(fader) {
  const draft = {};
  for (const layer of fader?.layers || []) {
    for (const bank of layer.banks) {
      for (const cell of bank.strips) {
        if (cell.id) draft[cell.slot] = cell.id;
      }
    }
  }
  return draft;
}

// --- stereo pair tiles (the console's Stereo links tab) --------------------------------------
// One tile per channel pair the console can link: 1-2, 3-4, ... for 'odd_even' pairing (how GLD / SQ /
// CL pair strips); 'adjacent' also allows N / N+1 but still tiles the aligned pairs (any other
// linked pair is shown as a tile too, so nothing linked is hidden). The range stops at the
// console's mono inputs (profile.dsp_inputs.mono, else mixer_inputs, else the highest channel
// number). A channel that does not exist yet is `missing`: linking creates it, like the Inputs
// page's Stereo toggle. State: 'linked' (the two are a pair), 'free', or 'blocked' (a leg is linked
// to a different channel; unlink that first).
// channels: [{id, channel_number, source_label, is_stereo_linked, stereo_link_role, stereo_partner_id}]
export function stereoPairTiles(channels, profile = null, mixerInputs = null) {
  const byNumber = new Map((channels || []).map((c) => [Number(c.channel_number), c]));
  const top = Math.max(0, ...byNumber.keys());
  const mono = Number(profile?.dsp_inputs?.mono) || 0;
  const limit = mono || Number(mixerInputs) || top;
  const tiles = new Map();
  const add = (low) => {
    const high = low + 1;
    if (tiles.has(low) || high > Math.max(limit, top)) return;
    const a = byNumber.get(low) || null;
    const b = byNumber.get(high) || null;
    const together = !!(a?.is_stereo_linked && b?.is_stereo_linked && (a.stereo_partner_id === b.id || b.stereo_partner_id === a.id));
    const elsewhere = [a, b].some((c) => c?.is_stereo_linked && !together);
    tiles.set(low, {
      low,
      high,
      label: `${low}–${high}`,
      state: together ? 'linked' : elsewhere ? 'blocked' : 'free',
      a,
      b,
      missing: [a ? null : low, b ? null : high].filter((n) => n != null),
      outOfRange: high > limit,
    });
  };
  for (let low = 1; low + 1 <= Math.max(limit, 0); low += 2) add(low);
  // linked pairs that are not on the aligned grid (adjacent pairing, e.g. 2-3) still get a tile
  for (const c of channels || []) {
    if (c.is_stereo_linked && c.stereo_link_role === 'primary') add(Number(c.channel_number));
  }
  return [...tiles.values()].sort((x, y) => x.low - y.low);
}

// The tiles a "1-16" range covers: both legs inside the range (so "1-15" leaves 15–16 alone).
export function tilesInRange(tiles, text) {
  const wanted = new Set(parseNumberRanges(text));
  return (tiles || []).filter((t) => wanted.has(t.low) && wanted.has(t.high));
}

// --- strip picker (DCA members, FX sends, auto patch) -------------------------------------------
// A big console has 100+ strips, so a plain multi-select is unusable. These pure helpers back the
// StripPicker dialog: a number-range box ("1-16, 20, 24-32"), text/kind/group filters and a
// shift-click range.

// "1-16, 20; 24–32" -> [1..16, 20, 24..32] (sorted, unique). Junk tokens are skipped; a reversed
// range ("8-5") is read forwards; a range wider than `cap` is cut so a typo cannot hang the page.
export function parseNumberRanges(text, cap = 2000) {
  const out = new Set();
  for (const token of String(text || '').split(/[\s,;]+/)) {
    const m = token.match(/^(\d+)(?:[-–](\d+))?$/);
    if (!m) continue;
    let a = Number(m[1]);
    let b = m[2] == null ? a : Number(m[2]);
    if (a > b) [a, b] = [b, a];
    for (let n = a; n <= Math.min(b, a + cap); n += 1) out.add(n);
  }
  return [...out].sort((x, y) => x - y);
}

// The channel numbers an input strip stands for: "7" -> [7], a ganged pair "1-2" -> [1, 2]. Other
// kinds (FX, mixes, DCAs) have none, so a range never selects them.
export function stripChannelNumbers(item) {
  if (item?.kind !== 'input') return [];
  const m = String(item.number ?? '').match(/^(\d+)(?:-(\d+))?$/);
  if (!m) return [];
  return m[2] == null ? [Number(m[1])] : [Number(m[1]), Number(m[2])];
}

// Ids of the items a range string covers (inputs only, matched by channel number).
export function idsInRanges(items, text) {
  const wanted = new Set(parseNumberRanges(text));
  if (!wanted.size) return [];
  return (items || []).filter((i) => stripChannelNumbers(i).some((n) => wanted.has(n))).map((i) => i.id);
}

// Filter picker items by free text (label or number), kinds (empty = all) and instrument group.
export function filterStripItems(items, { query = '', kinds = [], group = '' } = {}) {
  const q = String(query || '').trim().toLowerCase();
  const kindSet = new Set(kinds || []);
  return (items || []).filter((i) => {
    if (kindSet.size && !kindSet.has(i.kind)) return false;
    if (group && i.group !== group) return false;
    if (!q) return true;
    return `${i.number ?? ''} ${i.label ?? ''}`.toLowerCase().includes(q);
  });
}

// Shift-click: every id between two clicked rows (inclusive) in the visible order.
export function rangeBetween(order, fromId, toId) {
  const a = order.indexOf(fromId);
  const b = order.indexOf(toId);
  if (a === -1 || b === -1) return toId == null ? [] : [toId];
  return order.slice(Math.min(a, b), Math.max(a, b) + 1);
}

// Selection edits that only touch the visible rows (so "all" under a filter selects what you see).
export const selectIds = (selected, ids) => [...new Set([...(selected || []), ...ids])];
export const deselectIds = (selected, ids) => (selected || []).filter((id) => !new Set(ids).has(id));
export function invertIds(selected, visibleIds) {
  const on = new Set(selected || []);
  const visible = new Set(visibleIds);
  return [...(selected || []).filter((id) => !visible.has(id)), ...visibleIds.filter((id) => !on.has(id))];
}

// A click on a selection row: a plain click toggles it, a shift-click toggles everything between the
// anchor (the last row clicked) and this one over the VISIBLE rows, to the state the clicked row is
// switching to. Returns the new selection and the new anchor.
export function toggleRowSelection(selected, { id, shift = false, anchor = null, visibleIds = [] }) {
  const isOn = new Set(selected || []).has(id);
  if (shift && anchor != null && anchor !== id && visibleIds.includes(anchor) && visibleIds.includes(id)) {
    const span = rangeBetween(visibleIds, anchor, id);
    return { selected: isOn ? deselectIds(selected, span) : selectIds(selected, span), anchor: id };
  }
  return { selected: isOn ? deselectIds(selected, [id]) : selectIds(selected, [id]), anchor: id };
}

// Ids in channel-number order (what auto patch wants: the order is the order of the sockets).
export const orderByNumber = (ids, numbers) => [...(ids || [])].sort((a, b) => (numbers.get(a) ?? 0) - (numbers.get(b) ?? 0));

// The first `max` selected items for the collapsed chip row, and how many more there are.
export function summariseSelection(items, selected, max = 6) {
  const byId = new Map((items || []).map((i) => [i.id, i]));
  const rows = (selected || []).map((id) => byId.get(id)).filter(Boolean);
  return { shown: rows.slice(0, max), more: Math.max(0, rows.length - max), total: rows.length };
}

// --- soft patch by port ---------------------------------------------------------------------------
// A big source (a 128-channel Dante card) is one port, not 128 dropdown rows.

// Ports of the soft-patch response for one direction ('in' also lists 'both'), grouped by device.
export function groupPortsByDevice(ports, direction) {
  const want = direction === 'out' ? ['out', 'both'] : ['in', 'both'];
  const groups = new Map();
  for (const p of ports || []) {
    if (!want.includes(p.direction)) continue;
    if (!groups.has(p.device_id)) groups.set(p.device_id, { device_id: p.device_id, device_name: p.device_name, ports: [] });
    groups.get(p.device_id).ports.push(p);
  }
  return [...groups.values()];
}

// The sockets of one port, in socket order, each with the number of the channel that holds it
// (`field` is 'dsp_source' for inputs, 'direct_out' for direct outs; `numbers` maps channel id ->
// channel number).
export function portSockets(sockets, devicePort, field, numbers) {
  if (!devicePort) return [];
  return (sockets || [])
    .filter((s) => s.device_id === devicePort.device_id && s.port_id === devicePort.port_id)
    .sort((a, b) => a.socket - b.socket)
    .map((s) => {
      const owners = s[`${field}_channel_ids`] || (s[`${field}_channel_id`] ? [s[`${field}_channel_id`]] : []);
      const owner = owners[0] || null;
      const num = owner ? numbers?.get(owner) ?? null : null;
      // an input socket may feed several channels (a split source): `owners` lists them all
      return {
        ...s,
        owner,
        owners,
        shared: owners.length > 1,
        ownerKind: owner ? 'channel' : null,
        ownerNumber: num,
        ownerLabel: owner ? `Ch ${num ?? '?'}` : '',
      };
    });
}

// --- soft patch targets -----------------------------------------------------------------------
// The soft patch maps three kinds of things to physical sockets. `field` is the API's name for each:
//   dsp_source  a channel's input socket          (targets: channels, input sockets)
//   direct_out  a channel's direct output socket   (targets: channels, output sockets)
//   out_socket  a bus' output socket               (targets: buses / mixes, output sockets)
export const SOFT_FIELDS = {
  dsp_source: { mode: 'in', direction: 'in', idsKey: 'channel_ids', idKey: 'channel_id' },
  direct_out: { mode: 'out', direction: 'out', idsKey: 'channel_ids', idKey: 'channel_id' },
  out_socket: { mode: 'bus', direction: 'out', idsKey: 'bus_ids', idKey: 'bus_id' },
};
export const fieldOfMode = (mode) => ({ in: 'dsp_source', out: 'direct_out', bus: 'out_socket' })[mode] || 'dsp_source';
export const softFieldInfo = (field) => SOFT_FIELDS[field] || SOFT_FIELDS.dsp_source;

// Body of POST .../soft-patch/auto for any target kind.
export function autoPatchBody(field, ids, port, { start = 1, skip = true, dry = false, append = false, shared = false } = {}) {
  const info = softFieldInfo(field);
  return {
    field,
    [info.idsKey]: ids,
    device_id: port.device_id,
    port_id: port.port_id,
    start_socket: Math.max(1, Number(start) || 1),
    skip_taken: !!skip,
    dry_run: !!dry,
    // buses: add an endpoint to each bus instead of replacing its endpoints
    ...(field === 'out_socket' && append ? { append: true } : {}),
    // inputs: reuse sockets other channels already take (a split source)
    ...(field === 'dsp_source' && shared ? { allow_shared: true } : {}),
  };
}

// --- bus endpoints (stereo buses, several outputs per bus) -----------------------------------------
// A bus leaves from one or more endpoints; one endpoint is 1 socket (mono), 2 adjacent sockets (stereo
// L, R) or 3 (LCR). The server claims the following sockets when it is given only the first one.
export const BUS_WIDTH = { mono: 1, stereo: 2, lcr: 3 };
export const busWidth = (mode) => BUS_WIDTH[mode] || 1;
const SIDES = { 1: [''], 2: ['L', 'R'], 3: ['L', 'R', 'C'] };

// "3–4" for adjacent sockets, "3 / 7" otherwise.
export function socketRunText(sockets) {
  const nums = [...(sockets || [])].map(Number);
  if (!nums.length) return '';
  const sorted = [...nums].sort((a, b) => a - b);
  const adjacent = sorted.every((n, i) => i === 0 || n === sorted[i - 1] + 1);
  if (nums.length === 1) return String(nums[0]);
  return adjacent ? `${sorted[0]}–${sorted.at(-1)}` : nums.join(' / ');
}

// One endpoint as a chip label: "AR2412 · Out 3–4" ("Out" keeps the port's direction word).
export function endpointLabel(endpoint, deviceNames, { out = 'Out' } = {}) {
  const refs = endpoint?.refs || [];
  if (!refs.length) return '';
  const name = deviceNames?.get(refs[0].device_id) || '?';
  return `${name} · ${out} ${socketRunText(refs.map((r) => r.socket))}`;
}

// "L 3, R 4" for a stereo endpoint, "3" for mono.
export function endpointSides(endpoint, mode) {
  const refs = endpoint?.refs || [];
  const sides = SIDES[Math.min(Math.max(refs.length, 1), 3)];
  if (busWidth(mode) === 1 && refs.length <= 1) return String(refs[0]?.socket ?? '');
  return refs.map((r, i) => `${sides[i] || ''} ${r.socket}`.trim()).join(', ');
}

// Endpoints that have fewer sockets than the bus's current mode needs (a mono bus switched to
// stereo after it was patched): [{endpoint, have, need}].
export function endpointShortages(bus) {
  const need = busWidth(bus?.mode);
  return (bus?.out_endpoints || [])
    .filter((e) => (e.refs || []).length < need)
    .map((endpoint) => ({ endpoint, have: (endpoint.refs || []).length, need }));
}

// The run of sockets a tap on `socket` would claim for a bus of `width`: all must exist on the port,
// be free (or already this bus's own). Returns the socket rows, or null when it does not fit.
export function busRunAt(socketRows, socket, width, ownerId = null) {
  const bySocket = new Map((socketRows || []).map((r) => [r.socket, r]));
  const run = [];
  for (let i = 0; i < Math.max(1, width); i += 1) {
    const row = bySocket.get(socket + i);
    if (!row || (row.owner && row.owner !== ownerId)) return null;
    run.push(row);
  }
  return run;
}

// A plan row from the auto patch preview: "Mix 2 → 3–4" (a stereo bus) or "Ch 5 → 12".
export const planRowText = (row, prefix) =>
  `${prefix} ${row.channel_number ?? ''}${row.name ? ` ${row.name}` : ''} → ${socketRunText(row.sockets?.length ? row.sockets : [row.socket])}`.replace(/\s+/g, ' ');

// --- split sources --------------------------------------------------------------------------------
// One input socket may feed several channels (FOH and monitors from the same source, each with its
// own processing). "Ch 3, Ch 4" for the hint text.
export const sharedChannelsText = (sharedWith, prefix = 'Ch') =>
  (sharedWith || []).map((o) => `${prefix} ${o.channel_number ?? '?'}`).join(', ');

// "Ch 3" in front of a label unless the label already starts with it ("Ch 1 L" stays "Ch 1 L").
export function numberedLabel(prefix, number, label) {
  const text = String(label || '').trim();
  const lead = new RegExp(`^${prefix}\\s*${number}(\\D|$)`, 'i');
  if (!text) return `${prefix} ${number}`;
  return lead.test(text) ? text : `${prefix} ${number} ${text}`;
}

// --- history step names -----------------------------------------------------------------------------
// The server sends `action` (the route's function name: "update_channel"). It is translated through
// `history.actions.<action>`; unknown ones are composed from `history.verbs.<verb>` +
// `history.nouns.<noun>` (split at the first underscore); the English `label` is the last resort.
// `tr` = { has(key), t(key) } so the helper stays free of vue-i18n.
export function historyStepLabel(entry, tr) {
  const action = String(entry?.action || '');
  if (action && tr.has(`history.actions.${action}`)) return tr.t(`history.actions.${action}`);
  const i = action.indexOf('_');
  const verb = i > 0 ? action.slice(0, i) : action;
  const noun = i > 0 ? action.slice(i + 1) : '';
  if (verb && tr.has(`history.verbs.${verb}`)) {
    const v = tr.t(`history.verbs.${verb}`);
    if (!noun) return v;
    if (tr.has(`history.nouns.${noun}`)) return `${v} ${tr.t(`history.nouns.${noun}`)}`;
  }
  return entry?.label || action.replace(/_/g, ' ');
}

// Body of PUT .../soft-patch/bulk that clears the sockets of the given channels / buses.
export function bulkClearBody(field, ids) {
  const info = softFieldInfo(field);
  return { field, assignments: ids.map((id) => ({ [info.idKey]: id, ref: null })) };
}

// Sockets of one OUTPUT port with whoever holds each: a channel's direct out or a bus (a socket
// carries one or the other). `ownerKind` says which, `ownerLabel` is what the grid prints ("Ch 3",
// "Mix 2"); the input side uses portSockets.
export function portSocketsOut(sockets, devicePort, channelNumbers, busNumbers, { ch = 'Ch', mix = 'Mix' } = {}) {
  if (!devicePort) return [];
  return (sockets || [])
    .filter((x) => x.device_id === devicePort.device_id && x.port_id === devicePort.port_id)
    .sort((a, b) => a.socket - b.socket)
    .map((x) => {
      const channelId = x.direct_out_channel_id || null;
      const busId = x.out_socket_bus_id || null;
      const owner = channelId || busId;
      const ownerKind = channelId ? 'channel' : busId ? 'bus' : null;
      const num = channelId ? channelNumbers?.get(channelId) : busId ? busNumbers?.get(busId) : null;
      return { ...x, owner, ownerKind, ownerNumber: num ?? null, ownerLabel: owner ? `${channelId ? ch : mix} ${num ?? '?'}` : '' };
    });
}

// The first free socket of a port at or after `from` (1 when none is free, so the field is never empty).
export function firstFreeSocket(socketRows, from = 1) {
  return socketRows.find((s) => s.socket >= from && !s.owner)?.socket ?? 1;
}

// Rows [start, end) of a long list for the paged socket grid (page is 1-based).
export const pageOf = (rows, page, size = 64) => rows.slice((page - 1) * size, page * size);

// What the expansion editor sends: drop empty cards and keep only the fields the API takes.
export function expansionPayload(cards) {
  return (cards || [])
    .map((c) => ({
      protocol: String(c.protocol || '').trim().toLowerCase(),
      channels_in: Math.max(0, Number(c.channels_in) || 0),
      channels_out: Math.max(0, Number(c.channels_out) || 0),
    }))
    .filter((c) => c.protocol && (c.channels_in || c.channels_out));
}

// Largest channel count a port allows on one side (side-specific limit, else the total), or null.
export function expansionLimit(port, side) {
  const specific = side === 'in' ? port?.max_channels_in : port?.max_channels_out;
  return specific ?? port?.max_channels ?? null;
}

// Expansion ports as the manual profile form edits them, and back (numbers or null, never '').
export const expansionFormRows = (ports) =>
  (ports || []).map((p) => ({
    protocol: p.protocol || '',
    slots: p.slots ?? null,
    max_channels: p.max_channels ?? null,
    max_channels_in: p.max_channels_in ?? null,
    max_channels_out: p.max_channels_out ?? null,
  }));
export function expansionFromForm(rows) {
  const n = (v) => (v === '' || v == null || Number.isNaN(Number(v)) ? null : Math.max(0, Number(v)));
  return (rows || [])
    .filter((r) => String(r.protocol || '').trim())
    .map((r) => ({
      protocol: String(r.protocol).trim().toLowerCase(),
      slots: n(r.slots),
      max_channels: n(r.max_channels),
      max_channels_in: n(r.max_channels_in),
      max_channels_out: n(r.max_channels_out),
    }));
}

// Icon and class suffix of a fader strip kind (input, fx return, mix, fx send, dca, empty).
export const STRIP_KIND_ICON = {
  input: 'mic',
  fx: 'graphic_eq',
  mix: 'call_split',
  fxsend: 'north_east',
  dca: 'workspaces',
  empty: 'crop_square',
};
export const stripKindIcon = (kind) => STRIP_KIND_ICON[kind] || 'help_outline';


// --- built-in FX engines -------------------------------------------------------------------------------

// Mirrors the server: an engine is "set up" when it has sends, a name other than the default
// "FX n", or a type other than 'other'. Anything else is a built-in placeholder.
export const fxIsConfigured = (engine) =>
  !!(engine?.sends || []).length || (!!engine?.name && !/^FX \d+$/.test(engine.name)) || (engine?.type || 'other') !== 'other';
export const fxConfiguredCount = (list) => (list || []).filter(fxIsConfigured).length;
// Back to the defaults of the engine at `position` (1-based): a built-in engine is reset, not deleted.
export const fxResetEngine = (engine, position) => ({
  ...engine,
  name: `FX ${position}`,
  type: 'other',
  stereo_return: true,
  send_mode: 'mono',
  sends: [],
});
