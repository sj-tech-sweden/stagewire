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

const byPosition = (a, b) => (a.position || 0) - (b.position || 0);
const byCreated = (a, b) => String(a.created_at).localeCompare(String(b.created_at)) || (a.id < b.id ? -1 : 1);

export function legacyViewFromGraph(devices, edges) {
  const nodes = new Map(devices.map((d) => [d.id, d]));
  const chainEdges = new Map();
  const links = new Map();
  for (const edge of edges) {
    const attrs = edge.attributes || {};
    if (edge.signal === 'link') {
      if (!links.has(edge.src_device_id)) links.set(edge.src_device_id, {});
      links.get(edge.src_device_id)[attrs.role] = attrs.legacy_target;
    } else if (attrs.chain) {
      if (!chainEdges.has(attrs.chain)) chainEdges.set(attrs.chain, []);
      chainEdges.get(attrs.chain).push(edge);
    }
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

  const elements = devices
    .filter((d) => d.kind === 'plot_element')
    .sort(byCreated)
    .map((node) => {
      const to = links.get(node.id) || {};
      const attrs = node.attributes || {};
      return {
        id: legacyId(node),
        element_type: attrs.element_type,
        label: attrs.label || '',
        position_x: node.canvas_x_cm,
        position_y: node.canvas_y_cm,
        rotation: node.canvas_rotation || 0,
        width_cm: attrs.width_cm ?? 60,
        height_cm: attrs.height_cm ?? 60,
        linked_channel_id: to.channel || null,
        linked_device_id: to.device || null,
        linked_patch_point_id: to.patch_point || null,
        linked_output_point_id: to.output_point || null,
        linked_video_input_id: to.video_input || null,
        linked_lens_device_id: to.lens || null,
      };
    });

  const plain = devices
    .filter((d) => d.kind !== 'plot_element' && d.kind !== 'channel_list')
    .map((d) => ({ id: legacyId(d), name: d.name }));

  return { lists, videoLists, elements, devices: plain };
}

const GEOMETRY = ['position_x', 'position_y', 'rotation', 'width_cm', 'height_cm', 'label'];

// ``liveElements`` are the plot's own (possibly mid-drag) elements: their geometry wins over
// the graph's so cables follow the cursor, while chains and links still come from the graph.
export function buildCableRowsFromGraph({ devices, edges, plan, audience, stageOffset, liveElements }) {
  const view = legacyViewFromGraph(devices, edges);
  if (liveElements?.length) {
    const live = new Map(liveElements.map((e) => [e.id, e]));
    view.elements = view.elements.map((el) => {
      const mine = live.get(el.id);
      if (!mine) return el;
      return { ...el, ...Object.fromEntries(GEOMETRY.map((k) => [k, mine[k] ?? el[k]])) };
    });
  }
  return buildCableRows({ ...view, plan, audience, stageOffset });
}
