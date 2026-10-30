import { buildCableRows } from './cables';

// The plot and the cable list were written against the legacy shapes (channel lists with
// patch points, video lists, plot elements). This rebuilds those shapes from the graph, using
// the legacy ids, so cable keys, saved routes and highlights keep working while the data
// itself comes from the graph.

export const legacyId = (node) => {
  const ref = node?.legacy_ref || '';
  const [table, id] = ref.split(':');
  return table && id ? id : node?.id;
};

const VIRTUAL = new Set(['channel', 'channel_list', 'output', 'video_input', 'video_destination', 'video_list', 'dmx_universe', 'rigging_point']);
const byPosition = (a, b) => (a.position || 0) - (b.position || 0);
const byCreated = (a, b) => String(a.created_at).localeCompare(String(b.created_at)) || (a.id < b.id ? -1 : 1);

const LINK_COLUMNS = {
  channel: 'linked_channel_id',
  device: 'linked_device_id',
  patch_point: 'linked_patch_point_id',
  output_point: 'linked_output_point_id',
  video_input: 'linked_video_input_id',
  lens: 'linked_lens_device_id',
  power_node: 'power_node_id',
};

// A plot element node as the plot page knows it: legacy element id, geometry, appearance and the
// legacy ids of what it links to (a link edge carries them as ``legacy_target``).
export function elementFromNode(node, links = {}, nodes = new Map()) {
  const attrs = node.attributes || {};
  const hung = attrs.rigging_point_id ? nodes.get(attrs.rigging_point_id) : null;
  return {
    id: legacyId(node),
    job_id: node.job_id,
    created_at: node.created_at,
    element_type: attrs.element_type,
    label: attrs.label || '',
    position_x: node.canvas_x_cm ?? 0,
    position_y: node.canvas_y_cm ?? 0,
    rotation: node.canvas_rotation || 0,
    width_cm: attrs.width_cm ?? 60,
    height_cm: attrs.height_cm ?? 60,
    image_url: attrs.image_url || '',
    coverage_angle_h: attrs.coverage_angle_h ?? 0,
    coverage_distance_m: attrs.coverage_distance_m ?? 0,
    focal_mm: attrs.focal_mm ?? null,
    power_connector: attrs.power_connector || '',
    rigging_point_id: hung ? legacyId(hung) : null,
    ...Object.fromEntries(Object.entries(LINK_COLUMNS).map(([role, column]) => [column, links[role] || null])),
  };
}

export function elementLinks(edges) {
  const links = new Map();
  for (const edge of edges) {
    if (edge.signal !== 'link') continue;
    const attrs = edge.attributes || {};
    if (!links.has(edge.src_device_id)) links.set(edge.src_device_id, {});
    links.get(edge.src_device_id)[attrs.role] = attrs.legacy_target;
  }
  return links;
}

export function elementsFromGraph(devices, edges) {
  const links = elementLinks(edges);
  const nodes = new Map(devices.map((d) => [d.id, d]));
  return devices
    .filter((d) => d.kind === 'plot_element')
    .sort(byCreated)
    .map((node) => elementFromNode(node, links.get(node.id) || {}, nodes));
}

export function legacyViewFromGraph(devices, edges) {
  const nodes = new Map(devices.map((d) => [d.id, d]));
  const chainEdges = new Map();
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (edge.signal === 'link' || !attrs.chain) continue;
    if (!chainEdges.has(attrs.chain)) chainEdges.set(attrs.chain, []);
    chainEdges.get(attrs.chain).push(edge);
  }
  const deviceId = (graphId) => legacyId(nodes.get(graphId));

  const audioPoints = (node) =>
    (chainEdges.get(node.id) || [])
      .filter((e) => !e.attributes.first_point)
      .map((e) => ({
        id: e.attributes.point_id,
        device_id: deviceId(e.dst_device_id),
        connector: e.attributes.connector || '',
        parent_id: e.attributes.parent_id || null,
        position: e.attributes.position,
      }))
      .sort(byPosition);

  const outputPoints = (bus) => {
    const points = audioPoints(bus);
    for (const e of chainEdges.get(bus.id) || []) {
      const first = e.attributes.first_point;
      if (first) {
        points.push({
          id: first.point_id,
          device_id: deviceId(e.src_device_id),
          connector: first.connector || '',
          parent_id: null,
          position: first.position,
        });
      }
    }
    return points.sort(byPosition);
  };

  const lists = devices
    .filter((d) => d.kind === 'channel_list')
    .sort(byPosition)
    .map((container) => {
      const members = (kind) =>
        devices.filter((d) => d.kind === kind && d.attributes?.list_id === container.id);
      return {
        id: legacyId(container),
        name: container.name,
        channels: members('channel')
          .map((ch) => ({
            id: legacyId(ch),
            channel_number: ch.attributes.channel_number,
            source_label: ch.name,
            patch_points: audioPoints(ch),
          }))
          .sort((a, b) => a.channel_number - b.channel_number),
        outputs: members('output')
          .sort(byPosition)
          .map((bus) => ({ id: legacyId(bus), name: bus.name, points: outputPoints(bus) })),
      };
    });

  const videoPoints = (node) => audioPoints(node);
  const videoOutputPoints = (dest) => {
    const points = new Map();
    const implied = [];
    for (const e of chainEdges.get(dest.id) || []) {
      const attrs = e.attributes;
      points.set(attrs.point_id, {
        id: attrs.point_id,
        device_id: deviceId(e.dst_device_id),
        connector: attrs.connector || '',
        parent_id: attrs.parent_id || null,
        position: attrs.position,
      });
      if (attrs.parent_id) {
        implied.push({
          id: attrs.parent_id,
          device_id: deviceId(e.src_device_id),
          connector: '',
          parent_id: null,
          position: (attrs.position || 0) - 1,
        });
      }
    }
    for (const point of implied) if (!points.has(point.id)) points.set(point.id, point);
    return [...points.values()].sort(byPosition);
  };

  const videoGroups = new Map();
  for (const d of devices) {
    if (d.kind !== 'video_input' && d.kind !== 'video_destination') continue;
    const id = d.attributes?.list_id;
    if (!videoGroups.has(id)) videoGroups.set(id, { id, inputs: [], outputs: [] });
    const group = videoGroups.get(id);
    if (d.kind === 'video_input') {
      group.inputs.push({
        id: legacyId(d),
        input_number: d.attributes.input_number,
        source_label: d.attributes.source_label || '',
        patch_points: videoPoints(d),
      });
    } else {
      group.outputs.push({
        id: legacyId(d),
        output_number: d.attributes.output_number,
        name: d.attributes.name || '',
        patch_points: videoOutputPoints(d),
      });
    }
  }
  const videoLists = [...videoGroups.values()].map((g) => ({
    ...g,
    inputs: g.inputs.sort((a, b) => a.input_number - b.input_number),
    outputs: g.outputs.sort((a, b) => a.output_number - b.output_number),
  }));

  const elements = elementsFromGraph(devices, edges);
  // Gear placed on the workspace map without a plot element stands for itself: cables run to its
  // box (a pseudo element linked to the device), so they can be routed from the new map too.
  const represented = new Set(elements.map((e) => e.linked_device_id).filter(Boolean));
  for (const node of devices) {
    if (VIRTUAL.has(node.kind) || node.kind === 'plot_element') continue;
    if (node.canvas_x_cm == null || node.canvas_y_cm == null || represented.has(legacyId(node))) continue;
    elements.push({
      id: `gear:${node.id}`,
      element_type: 'gear',
      label: node.name,
      position_x: node.canvas_x_cm,
      position_y: node.canvas_y_cm,
      rotation: node.canvas_rotation || 0,
      width_cm: node.attributes?.width_cm ?? 60,
      height_cm: node.attributes?.height_cm ?? 30,
      linked_device_id: legacyId(node),
    });
  }

  const plain = devices
    .filter((d) => d.kind !== 'plot_element' && d.kind !== 'channel_list')
    .map((d) => ({ id: legacyId(d), name: d.name }));

  return { lists, videoLists, elements, devices: plain };
}

const NODE_ATTRIBUTES = [
  'element_type',
  'width_cm',
  'height_cm',
  'image_url',
  'coverage_angle_h',
  'coverage_distance_m',
  'focal_mm',
  'power_connector',
];
const CANVAS = { position_x: 'canvas_x_cm', position_y: 'canvas_y_cm', rotation: 'canvas_rotation' };
const LINKS = [
  'linked_channel_id',
  'linked_device_id',
  'linked_patch_point_id',
  'linked_output_point_id',
  'linked_video_input_id',
  'linked_lens_device_id',
  'power_node_id',
  'rigging_point_id',
];

// What an element edit changes on the node, and which of it is a link (set by legacy id).
export function splitElementChanges(payload) {
  const node = {};
  const attributes = {};
  const links = {};
  for (const [key, value] of Object.entries(payload)) {
    if (CANVAS[key]) node[CANVAS[key]] = value;
    else if (key === 'label') attributes.label = value ?? '';
    else if (NODE_ATTRIBUTES.includes(key)) attributes[key] = value;
    else if (LINKS.includes(key)) links[key] = value ?? null;
  }
  if (Object.keys(attributes).length) node.attributes = attributes;
  return { node, links };
}

export function buildCableRowsFromGraph({ devices, edges, plan, audience, stageOffset }) {
  return buildCableRows({ ...legacyViewFromGraph(devices, edges), plan, audience, stageOffset });
}
