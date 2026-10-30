import { test, expect } from '@playwright/test';
import {
  catalogQuery,
  deviceFromProduct,
  boxFor,
  modeAttributes,
  modesForType,
  dmxTree,
  universeSource,
  universesOf,
  fixturesOf,
  isFixtureNode,
  deviceCreateBody,
  deviceForm,
  devicePatch,
  portGroups,
  portsFromGroups,
  chainForm,
  chainSteps,
  videoChainForm,
  videoChainNames,
  videoRowsOf,
  addConnector,
  expandGroups,
  CONNECTOR_PRESETS,
  powerTreeRows,
  outputsLabel,
  loadStatusColor,
  longFeeds,
  cordFor,
  POWER_INLETS,
  channelsOf,
  nextChannelNumber,
  centerOf,
  devicesShownAsElements,
  domainForCategory,
  isVirtual,
  linkRoleFor,
  dropPosition,
  suggestPorts,
  edgeRows,
  needsBookingRequest,
  phaseStatus,
  visibleOnLayers,
} from '../../src/utils/workspace';

test('categories map to a domain and unknown ones stay "other"', () => {
  expect(domainForCategory('Microphones')).toBe('audio');
  expect(domainForCategory('Moving lights')).toBe('lighting');
  expect(domainForCategory('Video > Cameras')).toBe('video');
  expect(domainForCategory('Power distro')).toBe('power');
  expect(domainForCategory('Cases')).toBe('other');
  expect(domainForCategory(null)).toBe('other');
});

test('a catalog product becomes a device bound to its Stockwire product', () => {
  const device = deviceFromProduct(
    { id: 42, name: 'SM58', category: 'Microphones', power_consumption_watts: '0', weight_kg: '0.3', booked: false },
    { parentId: 'case-1' },
  );
  expect(device).toMatchObject({
    domain: 'audio',
    name: 'SM58',
    stockwire_product_id: '42',
    stockwire_booked: false,
    case_parent_id: 'case-1',
    attributes: { weight_kg: 0.3 },
  });
  expect(needsBookingRequest(device)).toBe(true);
  expect(needsBookingRequest({ ...device, stockwire_booked: true })).toBe(false);
  expect(needsBookingRequest({ ...device, stockwire_booked: null })).toBe(false);
});

test('edge rows resolve device names and survive a missing device', () => {
  const rows = edgeRows(
    [{ id: 'e', signal: 'audio', src_device_id: 'a', src_port: 'out', dst_device_id: 'x', dst_port: 'in', channels: 1, revision: 2 }],
    [{ id: 'a', name: 'Mic' }],
  );
  expect(rows[0]).toMatchObject({ from: 'Mic', to: '?', revision: 2 });
});

test('layer toggles hide a domain but never hide uncategorised devices', () => {
  const layers = { audio: false, lighting: true };
  expect(visibleOnLayers({ domain: 'audio' }, layers)).toBe(false);
  expect(visibleOnLayers({ domain: 'lighting' }, layers)).toBe(true);
  expect(visibleOnLayers({ domain: 'power' }, layers)).toBe(true);
  expect(visibleOnLayers({ domain: 'other' }, layers)).toBe(true);
});

test('phase load levels flag warn above 80% and over above the limit', () => {
  const status = phaseStatus({ L1: 3000, L2: 4000, L3: 100, imbalance_pct: 40 }, 3680);
  expect(status.L1.level).toBe('warn');
  expect(status.L2.level).toBe('over');
  expect(status.L3.level).toBe('ok');
  expect(status.imbalanceLevel).toBe('warn');
});

test('catalog query repeats multi-value facets the way FastAPI expects', () => {
  const qs = catalogQuery({ q: 'sm', categories: ['A', 'B'], manufacturers: ['Shure'], jobId: '7' }).toString();
  expect(qs).toContain('category=A&category=B');
  expect(qs).toContain('manufacturer=Shure');
  expect(qs).toContain('job_id=7');
  expect(qs).not.toContain('[]');
});

test('port suggestion needs an output, an input, the same signal and mating connectors', () => {
  const mic = { domain: 'audio', ports: [{ id: 'out', direction: 'out', signal: 'audio', connector: 'XLR3' }] };
  const box = {
    domain: 'audio',
    ports: [
      { id: 'dmx-in', direction: 'in', signal: 'dmx', connector: 'xlr5' },
      { id: 'in-xlr3', direction: 'in', signal: 'audio', connector: 'xlr3' },
    ],
  };
  expect(suggestPorts(mic, box)).toEqual({ srcPort: 'out', dstPort: 'in-xlr3', signal: 'audio' });
  expect(suggestPorts(box, mic)).toBeNull();
  expect(suggestPorts({ domain: 'audio', ports: [] }, box)).toBeNull();
  const video = { domain: 'video', ports: [{ id: 'in', direction: 'in', signal: 'video', connector: 'sdi' }] };
  expect(suggestPorts(mic, video)).toBeNull();
});

test('drop positions snap to the grid and never go negative', () => {
  const rect = { left: 100, top: 50 };
  expect(dropPosition(260, 130, rect, 0.8)).toEqual({ x: 200, y: 100 });
  expect(dropPosition(90, 40, rect, 0.8)).toEqual({ x: 0, y: 0 });
});

test('phase status uses the limit reported by the API', () => {
  const status = phaseStatus({ L1: 6000, L2: 0, L3: 0, imbalance_pct: 0, limit_w: 7360 });
  expect(status.L1.level).toBe('warn');
  expect(phaseStatus({ L1: 6000, L2: 0, L3: 0 }).L1.level).toBe('over');
});

test('channel, output, list and video chain nodes are virtual, gear is not', () => {
  for (const kind of ['channel', 'output', 'channel_list', 'video_input', 'video_destination']) {
    expect(isVirtual({ kind })).toBe(true);
  }
  for (const kind of ['mixer', 'analog_stagebox', 'fixture', 'case', '']) {
    expect(isVirtual({ kind })).toBe(false);
  }
});

test('plot elements are drawn at their real size and rotate about their top-left corner', () => {
  const element = {
    kind: 'plot_element',
    canvas_x_cm: 100,
    canvas_y_cm: 50,
    canvas_rotation: 90,
    attributes: { width_cm: 200, height_cm: 100 },
  };
  expect(boxFor(element, 0.5)).toEqual({ w: 100, h: 50 });
  expect(boxFor({ kind: 'mixer' }, 0.5)).toEqual({ w: 96, h: 40 });
  const [x, y] = centerOf(element, 1);
  expect(Math.round(x)).toBe(50);
  expect(Math.round(y)).toBe(150);
});

test('a device with a plot element is hidden from the canvas, other links are not', () => {
  const shown = devicesShownAsElements([
    { signal: 'link', dst_device_id: 'stagebox', attributes: { role: 'device' } },
    { signal: 'link', dst_device_id: 'channel', attributes: { role: 'channel' } },
    { signal: 'audio', dst_device_id: 'desk', attributes: {} },
  ]);
  expect([...shown]).toEqual(['stagebox']);
});

test('a plot element links to a channel, video input, power node or device by what it is dropped on', () => {
  expect(linkRoleFor({ kind: 'channel' })).toBe('channel');
  expect(linkRoleFor({ kind: 'video_input' })).toBe('video_input');
  expect(linkRoleFor({ kind: 'distro', domain: 'power' })).toBe('power_node');
  expect(linkRoleFor({ kind: 'mixer', domain: 'audio' })).toBe('device');
});

const names = [
  { id: 'box', name: 'Stagebox', kind: 'analog_stagebox' },
  { id: 'desk', name: 'Desk', kind: 'mixer' },
  { id: 'amp', name: 'Amp', kind: 'amp' },
];

test('a channel chain reads in order and rebuilds into the dialog form', () => {
  const edges = [
    { src_device_id: 'ch', dst_device_id: 'desk', attributes: { chain: 'ch', position: 1, connector: 'Dante' } },
    { src_device_id: 'ch', dst_device_id: 'box', attributes: { chain: 'ch', position: 0, connector: 'XLR', patch_label: 'In 3' } },
    { src_device_id: 'x', dst_device_id: 'amp', attributes: { chain: 'other', position: 0 } },
  ];
  expect(chainSteps({ id: 'ch' }, edges, names)).toEqual(['Stagebox', 'Desk']);
  expect(chainForm({ id: 'ch' }, edges, names)).toEqual([
    { device_id: 'box', connector: 'XLR', patch_label: 'In 3', in_port: '', out_port: '', notes: '', parent_index: null },
    { device_id: 'desk', connector: 'Dante', patch_label: '', in_port: '', out_port: '', notes: '', parent_index: null },
  ]);
});

test('an output chain starts at the console and keeps its branches', () => {
  const edges = [
    {
      src_device_id: 'desk',
      dst_device_id: 'bus',
      attributes: { chain: 'bus', first_point: { position: 0, point_id: 'p0', connector: '' } },
    },
    { src_device_id: 'bus', dst_device_id: 'amp', attributes: { chain: 'bus', position: 1, point_id: 'p1' } },
    { src_device_id: 'bus', dst_device_id: 'box', attributes: { chain: 'bus', position: 2, point_id: 'p2', parent_id: 'p0' } },
  ];
  expect(chainSteps({ id: 'bus' }, edges, names)).toEqual(['Desk', 'Amp', 'Stagebox']);
  expect(chainForm({ id: 'bus' }, edges, names).map((s) => s.parent_index)).toEqual([null, null, 0]);
});

test('channels are listed by number and the next number follows the highest', () => {
  const devices = [
    { id: 'a', kind: 'channel', attributes: { list_id: 'L', channel_number: 10 } },
    { id: 'b', kind: 'channel', attributes: { list_id: 'L', channel_number: 2 } },
    { id: 'c', kind: 'channel', attributes: { list_id: 'other', channel_number: 99 } },
  ];
  const mine = channelsOf(devices, 'L');
  expect(mine.map((c) => c.id)).toEqual(['b', 'a']);
  expect(nextChannelNumber(mine)).toBe(11);
  expect(nextChannelNumber([])).toBe(1);
});

test('only ports with a connector or channel count are connector groups', () => {
  const ports = [
    { id: 'in-xlr3', direction: 'in', connector: 'xlr3', channels: 32 },
    { id: 'out-audio', direction: 'out', signal: 'audio' },
  ];
  expect(portGroups(ports)).toEqual([{ direction: 'in', connector: 'xlr3', count: 32 }]);
});

test('editing groups keeps generic ports and gives every port a unique id', () => {
  const existing = [{ id: 'out-audio', direction: 'out', signal: 'audio' }];
  const ports = portsFromGroups(
    [
      { direction: 'in', connector: 'XLR3', count: 16 },
      { direction: 'in', connector: 'XLR3', count: 8 },
      { direction: 'out', connector: '', count: 4 },
    ],
    existing,
    'analog_stagebox',
  );
  expect(ports.map((p) => p.id)).toEqual(['in-xlr3', 'in-xlr3-2', 'out-x', 'out-audio']);
  expect(ports[0]).toMatchObject({ connector: 'xlr3', channels: 16, signal: 'audio' });
  expect(portsFromGroups([{ direction: 'out', connector: 'SDI', count: 2 }], [], 'camera')[0].signal).toBe('video');
});

test('a device form round-trips into a patch that clears emptied fields and keeps other attributes', () => {
  const node = {
    name: 'Cam',
    kind: 'camera',
    notes: '',
    attributes: { weight_kg: 2, max_distance_m: 30, device_type: 'camera', custom: 'keep' },
    ports: [{ id: 'out-sdi', direction: 'out', connector: 'sdi', channels: 2 }],
  };
  const form = deviceForm(node);
  expect(form).toMatchObject({ device_type: 'camera', weight_kg: 2, max_distance_m: 30 });
  form.max_distance_m = '';
  form.focal_min_mm = '4.3';
  const patch = devicePatch(node, form);
  expect(patch.attributes).toMatchObject({ weight_kg: 2, max_distance_m: null, focal_min_mm: 4.3 });
  expect(patch.attributes).not.toHaveProperty('custom');
  expect(patch.ports).toHaveLength(1);
  const body = deviceCreateBody({ ...form, power_w: 120, ports: [{ direction: 'out', connector: 'SDI', count: 2 }] });
  expect(body).toMatchObject({ name: 'Cam', device_type: 'camera', power_watts: 120, focal_min_mm: '4.3' });
  expect(body).not.toHaveProperty('max_distance_m');
});

test('fixtures are found by their DMX patch and listed by universe then address', () => {
  const devices = [
    { id: 'a', name: 'B', kind: 'fixture', attributes: { universe: 2, dmx_address: 1 } },
    { id: 'b', name: 'A', kind: 'other', attributes: { universe: 1, dmx_address: 30 } },
    { id: 'c', name: 'C', kind: 'fixture', attributes: { universe: 1, dmx_address: 1 } },
    { id: 'd', name: 'Desk', kind: 'mixer', attributes: {} },
    { id: 'e', name: 'Spot', kind: 'plot_element', attributes: { universe: 1 } },
  ];
  expect(isFixtureNode(devices[3])).toBe(false);
  expect(fixturesOf(devices).map((d) => d.id)).toEqual(['c', 'b', 'a']);
});

test('a universe chain skips its source edge, finds its source device and keeps parents', () => {
  const uni = { id: 'u1', kind: 'dmx_universe', name: 'U1', position: 1 };
  const edges = [
    { src_device_id: 'desk', dst_device_id: 'u1', attributes: { chain: 'u1' } },
    { src_device_id: 'u1', dst_device_id: 'box', attributes: { chain: 'u1', position: 0, step_id: 's0', connector: 'XLR5', in_port: 'In' } },
    { src_device_id: 'box', dst_device_id: 'amp', attributes: { chain: 'u1', position: 1, step_id: 's1', parent_id: 's0' } },
  ];
  expect(universeSource(uni, edges)).toBe('desk');
  expect(chainSteps(uni, edges, names)).toEqual(['Stagebox', 'Amp']);
  const form = chainForm(uni, edges, names);
  expect(form.map((s) => s.parent_index)).toEqual([null, 0]);
  expect(form[0]).toMatchObject({ connector: 'XLR5', in_port: 'In' });
  expect(universesOf([{ id: 'x', kind: 'fixture', position: 0 }, uni, { id: 'u0', kind: 'dmx_universe', position: 0 }]).map((d) => d.id)).toEqual(['u0', 'u1']);
});

test('universe nodes are virtual: never drawn on the canvas or listed as gear', () => {
  expect(isVirtual({ kind: 'dmx_universe' })).toBe(true);
});

test('the DMX flow tree nests steps under their parents and tells fixtures from devices', () => {
  const uni = { id: 'u1' };
  const devices = [
    { id: 'a', name: 'Wash A', kind: 'fixture', attributes: { universe: 1 } },
    { id: 'b', name: 'Wash B', kind: 'fixture', attributes: { universe: 1 } },
    { id: 's', name: 'Splitter', kind: 'other', attributes: {} },
  ];
  const edges = [
    { src_device_id: 'u1', dst_device_id: 'a', attributes: { chain: 'u1', step_id: 's0', position: 0, connector: 'XLR5' } },
    { src_device_id: 'a', dst_device_id: 'b', attributes: { chain: 'u1', step_id: 's1', position: 1, parent_id: 's0' } },
    { src_device_id: 'u1', dst_device_id: 's', attributes: { chain: 'u1', step_id: 's2', position: 2 } },
    { src_device_id: 'desk', dst_device_id: 'u1', attributes: { chain: 'u1' } },
  ];
  const tree = dmxTree(uni, edges, devices);
  expect(tree.map((n) => [n.label, n.kind])).toEqual([['Wash A', 'fixture'], ['Splitter', 'device']]);
  expect(tree[0].children.map((n) => n.label)).toEqual(['Wash B']);
  expect(tree[0].connector).toBe('XLR5');
});

test('library modes are found by type name and bring their footprint', () => {
  const types = [
    { name: 'LED wash', modes: [{ name: '16ch', footprint: 16, position: 1 }, { name: '8ch', footprint: 8, position: 0 }] },
    { name: 'Spot', modes: [] },
  ];
  expect(modesForType(types, ' led WASH ').map((m) => m.name)).toEqual(['8ch', '16ch']);
  expect(modesForType(types, 'Unknown')).toEqual([]);
  expect(modesForType(types, null)).toEqual([]);
  expect(modeAttributes(types[0].modes[0])).toEqual({ channel_mode: '16ch', footprint: 16 });
});

test('only a universe skips the edge that feeds it: other chains keep every step', () => {
  const channel = { id: 'ch', kind: 'channel' };
  const edges = [{ src_device_id: 'x', dst_device_id: 'ch', attributes: { chain: 'ch', position: 0 } }];
  expect(chainForm(channel, edges, [{ id: 'ch', name: 'Ch' }, { id: 'x', name: 'X' }])).toHaveLength(1);
});

test('video rows are listed per list and in number order', () => {
  const devices = [
    { id: 'a', kind: 'video_input', position: 2, attributes: { list_id: 'L' } },
    { id: 'b', kind: 'video_input', position: 1, attributes: { list_id: 'L' } },
    { id: 'c', kind: 'video_input', position: 1, attributes: { list_id: 'M' } },
    { id: 'd', kind: 'video_destination', position: 1, attributes: { list_id: 'L' } },
  ];
  expect(videoRowsOf(devices, 'L', 'video_input').map((d) => d.id)).toEqual(['b', 'a']);
  expect(isVirtual({ kind: 'video_list' })).toBe(true);
});

test('a video chain is rebuilt from its edges and from the roots kept on the destination', () => {
  const gear = [
    { id: 'conv', name: 'Converter' },
    { id: 'sw', name: 'Switcher' },
    { id: 'screen', name: 'Screen' },
  ];
  const input = { id: 'cam' };
  const inputEdges = [
    { dst_device_id: 'sw', attributes: { chain: 'cam', point_id: 'p1', position: 1, input_port: 'In 1' } },
    { dst_device_id: 'conv', attributes: { chain: 'cam', point_id: 'p0', position: 0, connector: 'SDI' } },
  ];
  expect(videoChainNames(input, inputEdges, gear)).toEqual(['Converter', 'Switcher']);
  expect(videoChainForm(input, inputEdges, gear)[1].input_port).toBe('In 1');

  const output = { id: 'dest', attributes: { roots: [{ device_id: 'sw', point_id: 'r', position: 0 }] } };
  const outputEdges = [
    { dst_device_id: 'screen', attributes: { chain: 'dest', point_id: 'p1', position: 1, parent_id: 'r' } },
  ];
  expect(videoChainNames(output, outputEdges, gear)).toEqual(['Switcher', 'Screen']);
  expect(videoChainForm(output, outputEdges, gear).map((s) => s.parent_index)).toEqual([null, 0]);
});

test('the power tree is listed under its parents and orphans are still shown', () => {
  const nodes = [
    { id: 'b', parent_id: 'a' },
    { id: 'a', parent_id: null },
    { id: 'c', parent_id: 'b' },
    { id: 'x', parent_id: 'missing' },
  ];
  expect(powerTreeRows(nodes).map((n) => [n.id, n.depth])).toEqual([
    ['a', 0],
    ['b', 1],
    ['c', 2],
    ['x', 0],
  ]);
  expect(outputsLabel([{ connector: 'schuko', count: 4, phase: 'L1' }, { connector: 'cee16', count: 1 }])).toBe(
    '4× schuko L1, 1× cee16',
  );
  expect(loadStatusColor('over')).toBe('negative');
  expect(loadStatusColor('whatever')).toBe('grey');
  expect(isVirtual({ kind: 'rigging_point' })).toBe(true);
});

test('a connector preset adds a group, or raises the count of the same connector and direction', () => {
  const xlrIn = CONNECTOR_PRESETS.find((p) => p.label === 'XLR ×8 in')!;
  const once = addConnector([], xlrIn);
  expect(once).toEqual([{ direction: 'in', connector: 'xlr3', count: 8 }]);
  expect(addConnector(once, xlrIn)[0].count).toBe(16);
  const out = addConnector(once, { connector: 'xlr3', direction: 'out', count: 8 });
  expect(out).toHaveLength(2);
});

test('a bidirectional connector is two ports and shows as one group again', () => {
  const groups = [{ direction: 'both', connector: 'dante', count: 1 }];
  const ports = portsFromGroups(groups, [], 'mixer');
  expect(ports.map((p) => [p.direction, p.connector, p.channels])).toEqual([
    ['in', 'dante', 1],
    ['out', 'dante', 1],
  ]);
  expect(new Set(ports.map((p) => p.id)).size).toBe(2);
  expect(portGroups(ports)).toEqual([{ direction: 'both', connector: 'dante', count: 1 }]);
  expect(expandGroups(groups).map((g) => g.direction)).toEqual(['in', 'out']);
  // different counts are two different groups, not a bidirectional one
  expect(
    portGroups([
      { id: 'a', direction: 'in', connector: 'xlr3', channels: 8 },
      { id: 'b', direction: 'out', connector: 'xlr3', channels: 4 },
    ]),
  ).toHaveLength(2);
});

test('extension cords are suggested for feeds longer than the threshold, rounded up to a stock length', () => {
  expect([1, 5, 5.1, 12, 60].map(cordFor)).toEqual([2, 5, 10, 15, 60]);
  const nodes = [
    { id: 'src', kind: 'source', parent_id: null, venue_outlet_id: 'o1', x_cm: null, y_cm: null },
    { id: 'near', kind: 'distro', parent_id: 'src', x_cm: 300, y_cm: 0 },
    { id: 'far', kind: 'distro', parent_id: 'src', x_cm: 1200, y_cm: 500 },
    { id: 'cord', kind: 'extension', parent_id: 'src', x_cm: 5000, y_cm: 0 },
    { id: 'behind', kind: 'breakout', parent_id: 'cord', x_cm: 9000, y_cm: 0 },
    { id: 'unplaced', kind: 'distro', parent_id: 'src' },
  ];
  const found = longFeeds(nodes, [{ id: 'o1', x_cm: 0, y_cm: 0 }], 5);
  expect(found.map((f) => [f.node.id, f.metres, f.length])).toEqual([['far', 13, 15]]);
  expect(longFeeds(nodes, [{ id: 'o1', x_cm: 0, y_cm: 0 }], 1).map((f) => f.node.id)).toEqual(['far', 'near']);
  expect(POWER_INLETS[0].value).toBe('iec_c13');
});
