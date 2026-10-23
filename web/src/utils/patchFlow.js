// Flatten a signal-chain tree (each node holds at most one continuing child in
// the linear chain) into an ordered list starting at the source.
export function chainNodes(tree) {
  if (!tree) return [];
  const nodes = [tree];
  let cur = tree;
  while (cur.children && cur.children.length) {
    cur = cur.children[0];
    nodes.push(cur);
  }
  return nodes;
}

// Map channel id -> labels of stage-plot elements that sit on that channel,
// either directly, through one of its patch points, or through a device.
export function buildStageByChannel(channels, elements) {
  const pointChannel = new Map();
  const pointName = new Map();
  const deviceChannels = new Map();
  for (const ch of channels || []) {
    for (const p of ch.patch_points || []) {
      pointChannel.set(p.id, ch.id);
      pointName.set(p.id, p.name || '');
      if (p.device_id) {
        if (!deviceChannels.has(p.device_id)) deviceChannels.set(p.device_id, new Set());
        deviceChannels.get(p.device_id).add(ch.id);
      }
    }
  }
  const out = new Map();
  for (const el of elements || []) {
    const channelIds = new Set();
    if (el.linked_channel_id) channelIds.add(el.linked_channel_id);
    if (el.linked_patch_point_id && pointChannel.has(el.linked_patch_point_id)) {
      channelIds.add(pointChannel.get(el.linked_patch_point_id));
    }
    if (el.linked_device_id) {
      for (const cid of deviceChannels.get(el.linked_device_id) || []) channelIds.add(cid);
    }
    if (!channelIds.size) continue;
    const ppName = el.linked_patch_point_id ? pointName.get(el.linked_patch_point_id) : '';
    const base = el.label || el.element_type;
    const text = ppName ? `${base} (${ppName})` : base;
    for (const cid of channelIds) {
      if (!out.has(cid)) out.set(cid, []);
      out.get(cid).push(text);
    }
  }
  return out;
}
