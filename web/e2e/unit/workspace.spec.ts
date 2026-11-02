import { test, expect } from '@playwright/test';
import { apiErrorText } from '../../src/utils/errors';
import { GEAR_ELEMENTS, isSpeakerType } from '../../src/utils/plotObjects';
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
  stereoPairPlan,
  mixerSpecsOf,
  portUsage,
  chainDevices,
  physicalHintKey,
  mixerSlotsToAdd,
  stereoView,
  chainSteps,
  videoChainForm,
  videoChainNames,
  videoRowsOf,
  addConnector,
  outputPointOptions,
  cableFor,
  powerInletLabel,
  flowTree,
  connectorGroupsFromProduct,
  fillFormFromSpecs,
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
  // gear is 60 x 30 cm unless sized, never smaller than a tappable minimum, and scales as a whole
  expect(boxFor({ kind: 'mixer' }, 1)).toEqual({ w: 60, h: 30 });
  expect(boxFor({ kind: 'mixer' }, 0.1)).toEqual({ w: 28, h: 16 });
  expect(boxFor({ kind: 'mixer', attributes: { width_cm: 100, height_cm: 40 } }, 1, 0.5)).toEqual({ w: 50, h: 20 });
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

test('a Stockwire product brings its connector groups, power inlet and ports, in both spec forms', () => {
  const groups = connectorGroupsFromProduct({
    specs: {
      connectors: [
        'SDI',
        { connector: 'XLR3', direction: 'output', count: 8, signal: 'audio' },
        { type: 'dante' },
        { name: ' ' },
      ],
    },
  });
  expect(groups).toEqual([
    { direction: 'both', connector: 'sdi', count: 1, signal: null },
    { direction: 'out', connector: 'xlr3', count: 8, signal: 'audio' },
    { direction: 'both', connector: 'dante', count: 1, signal: null },
  ]);
  const device = deviceFromProduct({
    id: 9,
    name: 'Rack mixer',
    category: 'Video > Switchers',
    specs: { power_inlet: 'IEC_C13', connectors: ['sdi', { connector: 'xlr3', direction: 'in', count: 4, signal: 'audio' }] },
  });
  expect(device.attributes.power_inlet).toBe('iec_c13');
  expect(device.ports.map((p) => [p.direction, p.connector, p.channels, p.signal])).toEqual([
    ['in', 'sdi', 1, 'video'],
    ['out', 'sdi', 1, 'video'],
    ['in', 'xlr3', 4, 'audio'],
  ]);
  expect(connectorGroupsFromProduct({})).toEqual([]);
  const form = { name: '', ports: [], power_inlet: null, weight_kg: null, power_w: null };
  fillFormFromSpecs(form, { id: 3, name: 'Amp' }, { connector_groups: [{ connector: 'speakon', direction: 'out', count: 2 }], power_inlet: 'powercon', weight_kg: 12 });
  expect(form).toMatchObject({ name: 'Amp', power_inlet: 'powercon', weight_kg: 12, stockwire_product_id: '3' });
  expect(form.ports).toEqual([{ direction: 'out', connector: 'speakon', count: 2 }]);
});

test('a chain becomes a flow tree: a line of devices, with branches and separate roots where the chain has them', () => {
  const devices = [
    { id: 'a', name: 'Stagebox' },
    { id: 'b', name: 'Console' },
    { id: 'c', name: 'Amp' },
    { id: 'd', name: 'Spk' },
  ];
  const line = flowTree('Kick', [{ device_id: 'a', connector: 'XLR' }, { device_id: 'b' }], devices);
  expect(line).toHaveLength(1);
  expect(line[0]).toMatchObject({ label: 'Kick', kind: 'source' });
  expect(line[0].children[0]).toMatchObject({ label: 'Stagebox', connector: 'XLR' });
  expect(line[0].children[0].children[0].label).toBe('Console');

  const branching = flowTree('Main', [{ device_id: 'b' }, { device_id: 'c', parent_index: 0 }, { device_id: 'd', parent_index: 0 }], devices);
  expect(branching[0].children[0].children.map((n) => n.label)).toEqual(['Amp', 'Spk']);

  const roots = flowTree('Out', [{ device_id: 'a' }, { device_id: 'b' }], devices, { separateRoots: true });
  expect(roots[0].children.map((n) => n.label)).toEqual(['Stagebox', 'Console']);
  expect(flowTree('', [{ device_id: 'a' }], devices)[0].label).toBe('Stagebox');
});

test('the lead a device needs follows its power inlet and the outlet it is plugged into', () => {
  expect(powerInletLabel(undefined)).toBe('IEC C13');
  expect(powerInletLabel('attached_schuko')).toBe('Attached cable, Schuko');
  expect(cableFor('', 'Schuko 16 A')).toBe('IEC C13 → Schuko 16 A');
  expect(cableFor('none', 'Schuko 16 A')).toBe('');
  expect(cableFor('attached_schuko', 'Schuko 16 A')).toBe('Fixed cable (Schuko)');
  expect(cableFor('attached_schuko', 'powerCON 20 A')).toBe('Fixed Schuko → powerCON 20 A');
  expect(cableFor('powercon', 'powerCON 20 A')).toBe('powerCON → powerCON 20 A');
});

test('API errors become readable text: strings, validation lists, objects and a fallback', () => {
  const err = (detail: unknown, status = 422) => ({ response: { status, data: { detail } }, message: 'Request failed' });
  expect(apiErrorText(err('Power group not found'))).toBe('Power group not found');
  expect(apiErrorText(err([{ msg: 'Input should be greater than 0' }, { msg: 'Field required' }]))).toBe(
    'Input should be greater than 0; Field required',
  );
  expect(apiErrorText(err({ message: 'Revision moved on' }, 409))).toBe('Revision moved on');
  expect(apiErrorText(err({ code: 'invalid_connection', issues: [{ message: 'not an input' }] }))).toBe('not an input');
  expect(apiErrorText(err(undefined, 502))).toContain('Stockwire');
  expect(apiErrorText(new Error('Network Error'))).toBe('Network Error');
  expect(apiErrorText({}, 'fallback')).toBe('fallback');
});

test('speakers carry coverage defaults and the output points of every chain can be linked', () => {
  const main = GEAR_ELEMENTS.find((g) => g.type === 'speaker_main')!;
  expect([main.coverageAngle, main.coverageDistance, main.rotation]).toEqual([90, 30, 180]);
  expect(isSpeakerType('monitor')).toBe(true);
  expect(isSpeakerType('camera')).toBe(false);
  expect(GEAR_ELEMENTS.find((g) => g.type === 'camera')).toMatchObject({ deviceType: 'camera', createDevice: true });

  const devices = [
    { id: 'o1', kind: 'output', name: 'Main' },
    { id: 'a', name: 'Console' },
    { id: 'b', name: 'Amp' },
  ];
  const edges = [
    { src_device_id: 'a', dst_device_id: 'o1', attributes: { chain: 'o1', first_point: { point_id: 'p0', connector: 'XLR' } } },
    { src_device_id: 'o1', dst_device_id: 'b', attributes: { chain: 'o1', point_id: 'p1', patch_label: 'Out 3' } },
    { src_device_id: 'a', dst_device_id: 'b', attributes: { chain: 'other', point_id: 'x' } },
  ];
  expect(outputPointOptions(devices, edges)).toEqual([
    { value: 'p0', label: 'Main · XLR · Console' },
    { value: 'p1', label: 'Main · Out 3 · Amp' },
  ]);
});

const chan = (id: string, n: number, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  kind: 'channel',
  attributes: { channel_number: n, ...extra },
});

test('stereo pairing links a channel with its odd/even neighbour and labels the legs L and R', () => {
  const odd = chan('a', 3, 'Keys');
  const plan = stereoPairPlan(odd, [odd, chan('b', 4, '')], true);
  expect(plan.partnerNumber).toBe(4);
  expect(plan.main.name).toBe('Keys L');
  expect(plan.partnerChanges?.name).toBe('Keys R');
  expect(plan.partnerChanges?.attributes.stereo_channel).toBe(3);

  const even = chan('b', 4, 'Keys');
  const lowerPartner = stereoPairPlan(even, [chan('a', 3, ''), even], true);
  expect(lowerPartner.partnerNumber).toBe(3);
  expect(lowerPartner.main.name).toBe('Keys R');
});

test('stereo pairing makes a missing partner, copies the shared fields and never stacks suffixes', () => {
  const main = chan('a', 1, 'Piano L', { input_type: 'di', connector: 'xlr', phantom_power: true });
  const plan = stereoPairPlan(main, [main], true);
  expect(plan.partnerCreate).toMatchObject({
    channel_number: 2,
    source_label: 'Piano R',
    input_type: 'di',
    connector: 'xlr',
    phantom_power: true,
    stereo: true,
    stereo_channel: 1,
  });
  expect(plan.main.name).toBe('Piano L');
});

test('unpairing clears both legs and stereoView reads the L/R side and neighbour', () => {
  const a = chan('a', 1, 'X L', { stereo: true, stereo_channel: 2 });
  const b = chan('b', 2, 'X R', { stereo: true, stereo_channel: 1 });
  const off = stereoPairPlan(a, [a, b], false);
  expect(off.main.attributes).toEqual({ stereo: false, stereo_channel: null });
  expect(off.partnerChanges?.attributes).toEqual({ stereo: false, stereo_channel: null });
  expect(stereoView(a, [a, b])).toMatchObject({ linked: true, isL: true, top: true });
  expect(stereoView(b, [a, b])).toMatchObject({ linked: true, isL: false, bottom: true });
  expect(stereoView(chan('c', 5, '', { stereo: true, stereo_channel: 6 }), [a, b]).linked).toBe(false);
});

test('a mixer fills the list with the empty inputs and output channels it is missing, and never removes', () => {
  expect(mixerSpecsOf({ specs: { inputs: 32, outputs: 16 } })).toEqual({ inputs: 32, buses: 16 });
  expect(mixerSpecsOf({ specs: { sb_inputs: 8 } })).toEqual({ inputs: 8, buses: null });
  expect(mixerSpecsOf(null)).toEqual({ inputs: null, buses: null });

  const channels = [chan('a', 1, 'Kick'), chan('b', 5, 'Snare')];
  const outputs = [
    { id: 'o1', attributes: { mode: 'stereo' } },
    { id: 'o2', attributes: { mode: 'mono' } },
  ];
  const add = mixerSlotsToAdd(channels, outputs, 4, 6);
  // two inputs exist, so two more are added after the highest number
  expect(add.channels.map((c) => c.channel_number)).toEqual([6, 7]);
  // a stereo bus is two outputs: 2 + 1 used, so three more mono outputs reach 6
  expect(add.outputs.map((o) => o.name)).toEqual(['Out 3', 'Out 4', 'Out 5']);
  const none = mixerSlotsToAdd(channels, outputs, 1, 1);
  expect([none.channels.length, none.outputs.length]).toEqual([0, 0]);
});

test('port usage counts channels on a channel port and connections on a plain one', () => {
  const box = {
    id: 'box',
    ports: [
      { id: 'in1', direction: 'in', connector: 'xlr3', channels: 8 },
      { id: 'out1', direction: 'out', connector: 'cat6', max_connections: 2 },
      { id: 'out2', direction: 'out', connector: 'speakon' },
    ],
  };
  const edges = [
    { src_device_id: 'mic', src_port: 'o', dst_device_id: 'box', dst_port: 'in1', channels: 3 },
    { src_device_id: 'mic2', src_port: 'o', dst_device_id: 'box', dst_port: 'in1' },
    { src_device_id: 'box', src_port: 'out1', dst_device_id: 'a', dst_port: 'i' },
    { src_device_id: 'box', src_port: 'out1', dst_device_id: 'b', dst_port: 'i' },
    { src_device_id: 'x', src_port: 'out1', dst_device_id: 'y', dst_port: 'i' },
  ];
  expect(portUsage(box, edges)).toEqual([
    { id: 'in1', direction: 'in', connector: 'xlr3', capacity: 8, used: 4 },
    { id: 'out1', direction: 'out', connector: 'cat6', capacity: 2, used: 2 },
    { id: 'out2', direction: 'out', connector: 'speakon', capacity: 1, used: 0 },
  ]);
  expect(portUsage(null, edges)).toEqual([]);
});

test('the weight and power hints say whether the value comes from Stockwire or was typed in', () => {
  const eff = { weight_kg_effective: 14, weight_source: 'stockwire', power_watts_effective: 60, power_source: 'manual' };
  expect(physicalHintKey(eff, 'weight_kg_effective', 'weight_source')).toEqual({ key: 'devices.stockwireInUse', value: 14 });
  expect(physicalHintKey(eff, 'power_watts_effective', 'power_source')).toEqual({ key: 'devices.manualInUse' });
  expect(physicalHintKey(null, 'weight_kg_effective', 'weight_source')).toEqual({ key: 'devices.notSet' });
});

test('the devices of a chain come back in order and skip steps whose device is gone', () => {
  const channel = { id: 'ch' };
  const devices = [{ id: 'a', name: 'Box' }, { id: 'b', name: 'Desk' }];
  const edges = [
    { dst_device_id: 'b', attributes: { chain: 'ch', position: 1 } },
    { src_device_id: 'a', dst_device_id: 'x', attributes: { chain: 'ch', first_point: { position: 0 } } },
    { dst_device_id: 'gone', attributes: { chain: 'ch', position: 2 } },
    { dst_device_id: 'a', attributes: { chain: 'other', position: 0 } },
  ];
  expect(chainDevices(channel, edges, devices).map((d) => d.name)).toEqual(['Box', 'Desk']);
});
