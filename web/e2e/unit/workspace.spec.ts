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
  chainDeviceOptions,
  findDeviceByName,
  guessChainDevice,
  isNewDeviceValue,
  newChainDeviceBody,
  newDeviceName,
  newDeviceValue,
  deviceForm,
  devicePatch,
  portGroups,
  portsFromGroups,
  chainForm,
  stereoPairPlan,
  mixerSpecsOf,
  portUsage,
  chainDevices,
  isOrphanedBySource,
  physicalHintKey,
  mixerSlotsToAdd,
  stereoView,
  chainSteps,
  videoChainForm,
  videoChainNames,
  videoRowsOf,
  stockwireAssetOf,
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
  channelFlowsForDevice,
  channelFlowTree,
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
    [{
      id: 'e',
      signal: 'audio',
      src_device_id: 'a',
      src_port: 'out',
      dst_device_id: 'x',
      dst_port: 'in',
      channels: 1,
      revision: 2,
      attributes: { patch_label: 'Stage left', connector: 'XLR3' },
    }],
    [{ id: 'a', name: 'Mic' }],
  );
  expect(rows[0]).toMatchObject({
    from: 'Mic',
    to: '?',
    revision: 2,
    patchLabel: 'Stage left',
    connector: 'XLR3',
  });
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
  const channel = { id: 'ch', name: 'Vox', kind: 'channel' };
  const edges = [
    { src_device_id: 'box', dst_device_id: 'desk', signal: 'audio', attributes: { chain: 'ch', position: 0, connector: 'XLR', patch_label: 'In 3' } },
    { src_device_id: 'desk', dst_device_id: 'ch', signal: 'audio', attributes: { chain: 'ch', position: 1, connector: 'Dante' } },
    { src_device_id: 'x', dst_device_id: 'amp', attributes: { chain: 'other', position: 0 } },
  ];
  expect(chainSteps(channel, edges, names)).toEqual(['Stagebox', 'Desk']);
  const form = chainForm(channel, edges, names);
  expect(form).toEqual([
    { device_id: 'box', connector: 'XLR', patch_label: 'In 3', in_port: '', out_port: '', notes: '', parent_index: null },
    { device_id: 'desk', connector: 'Dante', patch_label: '', in_port: '', out_port: '', notes: '', parent_index: null },
  ]);
  const mic = { id: 'mic', name: 'Mic' };
  const flow = channelFlowTree(
    channel,
    [{ src_device_id: 'mic', dst_device_id: 'box', signal: 'audio' }, ...edges],
    [...names, channel, mic],
    'Vox',
    form,
  )[0];
  expect([
    flow.label,
    flow.children[0].label,
    flow.children[0].children[0].label,
    flow.children[0].children[0].children[0].label,
  ])
    .toEqual(['Mic', 'Stagebox', 'Desk', 'Vox']);
  expect(flow.children[0].children[0].children[0].kind).toBe('channel');

  const legacyFlow = channelFlowTree(
    channel,
    [
      { src_device_id: 'ch', dst_device_id: 'desk', attributes: { chain: 'ch', position: 1 } },
      { src_device_id: 'ch', dst_device_id: 'box', attributes: { chain: 'ch', position: 0 } },
    ],
    [...names, channel],
    'Vox',
    form,
  )[0];
  expect([legacyFlow.label, legacyFlow.children[0].label, legacyFlow.children[0].children[0].label])
    .toEqual(['Stagebox', 'Desk', 'Vox']);
});

test('a Stockwire asset summary keeps the scanned code separate from its canonical id', () => {
  expect(
    stockwireAssetOf({
      stockwire_device_id: '42',
      attributes: {
        stockwire_asset_code: 'TAG-42',
        stockwire_asset_tag: 'TAG-42',
        stockwire_asset_serial: 'SN-42',
        stockwire_asset_barcode: 'BAR-42',
        stockwire_asset_qr_code: 'QR-42',
        stockwire_asset_rfid: 'RFID-42',
      },
    }),
  ).toEqual({
    isBound: true,
    canonicalId: '42',
    code: 'TAG-42',
    tag: 'TAG-42',
    serial: 'SN-42',
    barcode: 'BAR-42',
    qrCode: 'QR-42',
    rfid: 'RFID-42',
    description: null,
  });
  expect(stockwireAssetOf({ stockwire_device_id: 'legacy-asset-id' }).code).toBe(
    'legacy-asset-id',
  );
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

test('a legacy Stockwire asset ID attribute remains readable', () => {
  expect(
    stockwireAssetOf({
      attributes: {
        stockwire_asset_id: 'LEGACY-42',
        stockwire_asset_code: 'OLD-TAG',
      },
    }),
  ).toMatchObject({ isBound: true, canonicalId: null, code: 'OLD-TAG' });
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

test('a device signal flow includes each matching channel route without unrelated graph edges', () => {
  const devices = [
    { id: 'mic-1', name: 'Mic 1', kind: 'mic' },
    { id: 'mic-2', name: 'Mic 2', kind: 'mic' },
    { id: 'stagebox', name: 'Stagebox', kind: 'stagebox' },
    { id: 'channel-1', name: 'Ch 1', kind: 'channel', attributes: { source_device_id: 'mic-1' } },
    { id: 'channel-2', name: 'Ch 2', kind: 'channel', attributes: { source_device_id: 'mic-2' } },
    { id: 'wedge', name: 'Wedge', kind: 'speaker' },
  ];
  const edges = [
    {
      src_device_id: 'mic-1',
      src_port: 'out',
      dst_device_id: 'stagebox',
      dst_port: 'in',
      signal: 'audio',
    },
    {
      src_device_id: 'stagebox',
      dst_device_id: 'channel-1',
      attributes: { chain: 'channel-1', position: 0, patch_label: 'Vocal 1', connector: 'XLR3' },
    },
    {
      src_device_id: 'mic-2',
      dst_device_id: 'stagebox',
      signal: 'audio',
    },
    {
      src_device_id: 'stagebox',
      dst_device_id: 'channel-2',
      attributes: { chain: 'channel-2', position: 0, patch_label: 'Vocal 2' },
    },
    {
      src_device_id: 'stagebox',
      src_port: 'out',
      dst_device_id: 'wedge',
      attributes: { patch_label: 'Unrelated cable' },
    },
  ];

  const flows = channelFlowsForDevice('stagebox', devices, edges);
  const labels = (nodes) => nodes.flatMap((node) => [node.label, ...labels(node.children || [])]);
  expect(flows.map(({ channel }) => channel.id)).toEqual(['channel-1', 'channel-2']);
  expect(labels(flows.flatMap(({ routes }) => routes))).toEqual([
    'Mic 1',
    'Stagebox',
    'Ch 1',
    'Mic 2',
    'Stagebox',
    'Ch 2',
  ]);
  expect(labels(flows.flatMap(({ routes }) => routes))).not.toContain('Wedge');
  expect(flows[0].routes[0].children[0].patch_label).toBe('Vocal 1');
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

test('stereo pairing makes a missing partner, does not copy the preamp and never stacks suffixes', () => {
  const main = chan('a', 1, 'Piano L', { input_type: 'di', connector: 'xlr', phantom_power: true });
  const plan = stereoPairPlan(main, [main], true);
  expect(plan.partnerCreate).toMatchObject({
    channel_number: 2,
    source_label: 'Piano R',
    stereo: true,
    stereo_channel: 1,
  });
  // each leg is its own preamp: input type, connector and +48V are not copied to the partner
  expect(plan.partnerCreate).not.toHaveProperty('phantom_power');
  expect(plan.partnerCreate).not.toHaveProperty('input_type');
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

test('a replaced source device is removed only when nothing else uses it', () => {
  const devices = [
    { id: 'ch', attributes: { source_device_id: 'mic' } },
    { id: 'mic', attributes: {} },
    { id: 'ch2', attributes: { source_device_id: 'shared' } },
    { id: 'shared', attributes: {} },
  ];
  expect(isOrphanedBySource('mic', 'ch', devices, [])).toBe(true);
  // another channel names it as its source too
  expect(isOrphanedBySource('shared', 'ch', devices, [])).toBe(false);
  // patched into a chain or linked on the plot
  expect(isOrphanedBySource('mic', 'ch', devices, [{ src_device_id: 'x', dst_device_id: 'mic' }])).toBe(false);
});

test('a mixer imported from Stockwire patches the graph with real in/out ports (GLD-80 regression)', async () => {
  const { mixerGraphPorts, connectorGroupsFromProduct } = await import('../../src/utils/workspace');
  const product = {
    specs: {
      connectors: [
        { connector: 'xlr3', direction: 'in', count: 4, signal: 'audio' },
        { connector: 'xlr3', direction: 'out', count: 4, signal: 'audio' },
        { connector: 'ethercon', direction: 'both', count: 2, signal: 'audio' },
        { connector: 'dsnake', direction: 'both', count: 1, signal: 'audio' },
      ],
    },
  };
  const ports = mixerGraphPorts(connectorGroupsFromProduct(product), [{ id: 'power', direction: 'in', signal: 'power' }]);
  // every port has an id and only the directions the graph accepts; 'both' became in + out
  expect(ports.every((p) => p.id && (p.direction === 'in' || p.direction === 'out'))).toBe(true);
  expect(ports.map((p) => p.id)).toEqual([
    'in-xlr3', 'out-xlr3', 'in-ethercon', 'out-ethercon', 'in-dsnake', 'out-dsnake', 'power',
  ]);
  expect(mixerGraphPorts([], [])).toEqual([]);
});

test('a fader layout draft is the whole layout: a strip may sit on several faders, blanks are absent', async () => {
  const { applyFaderChoice, faderDraftFromMap } = await import('../../src/utils/workspace');
  let draft = applyFaderChoice({}, '1:A:1', 'c1');
  expect(draft).toEqual({ '1:A:1': 'c1' });
  // choosing c1 on another fader ADDS a placement: its first one stays
  draft = applyFaderChoice(draft, '2:B:3', 'c1');
  expect(draft).toEqual({ '1:A:1': 'c1', '2:B:3': 'c1' });
  // 'empty' and null both leave that fader blank (an absent slot); other faders are untouched
  draft = applyFaderChoice(draft, '1:A:2', 'c2');
  expect(applyFaderChoice(draft, '1:A:2', 'empty')).toEqual({ '1:A:1': 'c1', '2:B:3': 'c1' });
  expect(applyFaderChoice(draft, '1:A:2', null)).toEqual({ '1:A:1': 'c1', '2:B:3': 'c1' });
  // taking over: the draft a loaded map starts from is EVERY placed cell, stored layout or the
  // live starting point, so the first edit stores the whole map and nothing disappears
  const start = {
    custom: false,
    layers: [{ banks: [{ strips: [
      { slot: '1:A:1', pinned: false, kind: 'input', id: 'c1' },
      { slot: '1:A:2', pinned: false, kind: 'input', id: 'c2' },
      { slot: '1:A:3', pinned: false, kind: 'empty', id: null },
    ] }] }],
  };
  expect(faderDraftFromMap(start)).toEqual({ '1:A:1': 'c1', '1:A:2': 'c2' });
  const edited = applyFaderChoice(faderDraftFromMap(start), '1:A:3', 'c1');
  expect(edited).toEqual({ '1:A:1': 'c1', '1:A:2': 'c2', '1:A:3': 'c1' });
  expect(faderDraftFromMap({ ...start, custom: true })).toEqual({ '1:A:1': 'c1', '1:A:2': 'c2' });
  expect(faderDraftFromMap(null)).toEqual({});
});

test('stereoView reads the console link and the partner copy no longer shares the preamp', async () => {
  const { stereoView, stereoPairPlan } = await import('../../src/utils/workspace');
  const a = { id: 'a', attributes: { channel_number: 1, is_stereo_linked: true, stereo_link_role: 'primary', stereo_partner_id: 'b' } };
  const b = { id: 'b', attributes: { channel_number: 2, is_stereo_linked: true, stereo_link_role: 'secondary', stereo_partner_id: 'a' } };
  expect(stereoView(a, [a, b])).toMatchObject({ linked: true, isL: true, partner: 2, top: true });
  expect(stereoView(b, [a, b])).toMatchObject({ linked: true, isL: false, partner: 1, bottom: true });
  const plan = stereoPairPlan({ id: 'x', name: 'Keys', attributes: { channel_number: 3, phantom_power: true, input_type: 'di' } }, [], true);
  expect(plan.partnerCreate.phantom_power).toBeUndefined();
  expect(plan.partnerCreate.input_type).toBeUndefined();
});

// A fader map as the API returns it: layer 1, bank A, four faders; c1, c2 and fx-r placed, one blank.
const faderMap = {
  custom: true,
  strips: [
    { id: 'c1', kind: 'input' },
    { id: 'c2', kind: 'input' },
    { id: 'c3', kind: 'input' },
    { id: 'fx-r', kind: 'fx' },
    { id: 'fx-h', kind: 'fx', hidden: true },
  ],
  layers: [
    {
      layer: 1,
      banks: [
        {
          id: 'A',
          strips: [
            { slot: '1:A:1', fader: 1, id: 'c1', kind: 'input', pinned: true },
            { slot: '1:A:2', fader: 2, id: 'c2', kind: 'input', pinned: true },
            { slot: '1:A:3', fader: 3, id: null, kind: 'empty', pinned: false },
            { slot: '1:A:4', fader: 4, id: 'fx-r', kind: 'fx', pinned: true },
          ],
        },
      ],
    },
  ],
};

test('dragging a fader strip onto an empty fader moves it and leaves its other placements alone', async () => {
  const { moveFaderStrip } = await import('../../src/utils/workspace');
  const full = { '1:A:1': 'c1', '1:A:2': 'c2', '1:A:4': 'fx-r' };
  const next = moveFaderStrip(full, faderMap, { slot: '1:A:1' }, '1:A:3');
  expect(next).toEqual({ '1:A:3': 'c1', '1:A:2': 'c2', '1:A:4': 'fx-r' });
  // moving onto an occupied fader swaps: c2 takes the fader c1 came from
  expect(moveFaderStrip(next, faderMap, { slot: '1:A:3' }, '1:A:2')).toEqual({
    '1:A:2': 'c1',
    '1:A:3': 'c2',
    '1:A:4': 'fx-r',
  });
});

test('from the tray a strip is added; what it displaces becomes unplaced, nothing refills the gap', async () => {
  const { moveFaderStrip, unplacedStrips } = await import('../../src/utils/workspace');
  const full = { '1:A:1': 'c1', '1:A:2': 'c2' };
  // c3 dropped on c2's fader: c2 loses that placement and is unplaced (it is not re-filled anywhere)
  const next = moveFaderStrip(full, faderMap, { strip: 'c3' }, '1:A:2');
  expect(next).toEqual({ '1:A:1': 'c1', '1:A:2': 'c3' });
  expect(unplacedStrips(next, faderMap).map((x) => x.id)).toEqual(['c2', 'fx-r']);
  // dragged from the tray, a strip already placed is ADDED again (it now sits on two faders)
  expect(moveFaderStrip({ '1:A:2': 'c1' }, faderMap, { strip: 'c1' }, '1:A:3')).toEqual({ '1:A:2': 'c1', '1:A:3': 'c1' });
  // dropping a strip on the fader it already holds changes nothing
  const same = { '1:A:2': 'c1' };
  expect(moveFaderStrip(same, faderMap, { strip: 'c1' }, '1:A:2')).toBe(same);
});

test('fader drag edge cases: same slot, blank cell, and the tray drop', async () => {
  const { moveFaderStrip, unpinFaderStrip } = await import('../../src/utils/workspace');
  const draft = { '1:A:4': 'fx-r', '1:A:1': 'c1' };
  expect(moveFaderStrip(draft, faderMap, { slot: '1:A:1' }, '1:A:1')).toBe(draft);
  expect(moveFaderStrip(draft, faderMap, { slot: '1:A:3' }, '1:A:1')).toBe(draft); // blank: nothing to move
  // tray drop takes a dragged cell off ITS fader only; by id it removes every placement
  expect(unpinFaderStrip(draft, faderMap, { slot: '1:A:4' })).toEqual({ '1:A:1': 'c1' });
  expect(unpinFaderStrip(draft, faderMap, { strip: 'fx-r' })).toEqual({ '1:A:1': 'c1' });
  expect(unpinFaderStrip(draft, faderMap, { strip: 'c2' })).toEqual(draft);
});

test('the same strip on several faders, removing a placement leaves a blank, and unplaced counts', async () => {
  const { moveFaderStrip, removeFaderPlacement, stripPlacements, unpinFaderStrip, unplacedStrips } = await import('../../src/utils/workspace');
  const one = { '1:A:1': 'c1' };
  // copy (Alt/Ctrl drag): c1 stays on fader 1 and also lands on 3
  const copied = moveFaderStrip(one, faderMap, { slot: '1:A:1' }, '1:A:3', { copy: true });
  expect(copied).toEqual({ '1:A:1': 'c1', '1:A:3': 'c1' });
  // a plain drag moves it instead
  expect(moveFaderStrip(one, faderMap, { slot: '1:A:1' }, '1:A:3')).toEqual({ '1:A:3': 'c1' });
  // two placements, remove one (the cell menu): the other stays, the removed fader is blank
  expect(removeFaderPlacement(copied, faderMap, '1:A:3')).toEqual({ '1:A:1': 'c1' });
  expect(unpinFaderStrip(copied, faderMap, { slot: '1:A:1' })).toEqual({ '1:A:3': 'c1' });
  // removing the only placement leaves the strip unplaced; it does not come back anywhere
  const bare = removeFaderPlacement({ '1:A:2': 'c2' }, faderMap, '1:A:2');
  expect(bare).toEqual({});
  expect(stripPlacements(bare, faderMap, 'c2')).toEqual([]);
  expect(removeFaderPlacement({}, faderMap, '1:A:3')).toEqual({}); // a blank fader stays as it is
  // placements come from the draft while editing, from the saved map when there is no draft
  expect(stripPlacements(copied, faderMap, 'c1').map((p) => p.slot)).toEqual(['1:A:1', '1:A:3']);
  expect(stripPlacements(null, faderMap, 'c2').map((p) => p.slot)).toEqual(['1:A:2']);
  expect(stripPlacements({}, faderMap, 'c2')).toEqual([]);
  expect(stripPlacements(null, faderMap, 'nobody')).toEqual([]);
  // unplaced = strips on no fader, hidden built-in FX not counted
  expect(unplacedStrips(null, faderMap).map((x) => x.id)).toEqual(['c3']);
  expect(unplacedStrips({ '1:A:1': 'c1' }, faderMap).map((x) => x.id)).toEqual(['c2', 'c3', 'fx-r']);
});

test('stereo pair tiles follow the console pairing rule, states and ranges', async () => {
  const { stereoPairTiles, tilesInRange } = await import('../../src/utils/workspace');
  const ch = (n, extra = {}) => ({ id: `c${n}`, channel_number: n, source_label: `S${n}`, ...extra });
  const channels = [
    ch(1, { is_stereo_linked: true, stereo_link_role: 'primary', stereo_partner_id: 'c2' }),
    ch(2, { is_stereo_linked: true, stereo_link_role: 'secondary', stereo_partner_id: 'c1' }),
    ch(3),
    // 5-6 is a linked pair too
    ch(5, { is_stereo_linked: true, stereo_link_role: 'primary', stereo_partner_id: 'c6' }),
    ch(6, { is_stereo_linked: true, stereo_link_role: 'secondary', stereo_partner_id: 'c5' }),
  ];
  const tiles = stereoPairTiles(channels, { input_pairing: 'odd_even', dsp_inputs: { mono: 8 } });
  expect(tiles.map((t) => [t.label, t.state])).toEqual([
    ['1–2', 'linked'],
    ['3–4', 'free'],
    ['5–6', 'linked'],
    ['7–8', 'free'],
  ]);
  // channel 4 does not exist yet: the tile is free and says what linking creates
  expect(tiles[1].missing).toEqual([4]);
  expect(tiles[0].missing).toEqual([]);
  // the console's mono input count limits the grid; without a profile the highest channel does
  // (a linked pair beyond that limit stays visible so it can still be unlinked)
  expect(stereoPairTiles(channels, { dsp_inputs: { mono: 4 } }).map((t) => t.label)).toEqual(['1–2', '3–4', '5–6']);
  expect(stereoPairTiles([ch(1), ch(2), ch(3), ch(4), ch(5), ch(6)], { dsp_inputs: { mono: 4 } }).map((t) => t.label)).toEqual(['1–2', '3–4']);
  expect(stereoPairTiles(channels, null).map((t) => t.label)).toEqual(['1–2', '3–4', '5–6']);
  expect(stereoPairTiles([], null)).toEqual([]);
  // a leg linked to a different channel blocks the tile
  const blocked = stereoPairTiles(
    [ch(1), ch(2, { is_stereo_linked: true, stereo_link_role: 'primary', stereo_partner_id: 'c3' }), ch(3, { is_stereo_linked: true, stereo_link_role: 'secondary', stereo_partner_id: 'c2' })],
    { input_pairing: 'adjacent', dsp_inputs: { mono: 4 } },
  );
  expect(blocked.find((t) => t.label === '1–2').state).toBe('blocked');
  // the unaligned linked pair still has its own tile (adjacent pairing)
  expect(blocked.map((t) => t.label)).toContain('2–3');
  // the names under the numbers: a pair with one base name reads "<base> L/R", two different
  // channels "A · B", a missing leg shows only the one that exists
  const named = stereoPairTiles(
    [
      { id: 'a', channel_number: 1, source_label: 'Drums L', is_stereo_linked: true, stereo_link_role: 'primary', stereo_partner_id: 'b' },
      { id: 'b', channel_number: 2, source_label: 'Drums R', is_stereo_linked: true, stereo_link_role: 'secondary', stereo_partner_id: 'a' },
      { id: 'c', channel_number: 3, source_label: 'Kick' },
      { id: 'd', channel_number: 4, source_label: 'Snare' },
      { id: 'e', channel_number: 5, source_label: 'Keys' },
    ],
    { dsp_inputs: { mono: 8 } },
  );
  expect(named.map((t) => t.caption)).toEqual(['Drums L/R', 'Kick · Snare', 'Keys', '']);
  expect(named[0].names).toEqual(['Drums L', 'Drums R']);
  expect(named[0].captionTitle).toBe('Ch 1 Drums L · Ch 2 Drums R');
  expect(named[2].captionTitle).toBe('Ch 5 Keys · Ch 6 +');
  expect(named[3].captionTitle).toBe('Ch 7 + · Ch 8 +');
  // ranges: both legs must be inside
  expect(tilesInRange(tiles, '1-4').map((t) => t.label)).toEqual(['1–2', '3–4']);
  expect(tilesInRange(tiles, '1-3').map((t) => t.label)).toEqual(['1–2']);
  expect(tilesInRange(tiles, '3-4, 7-8').map((t) => t.label)).toEqual(['3–4', '7–8']);
  expect(tilesInRange(tiles, 'junk')).toEqual([]);
});

test('importing a bus-pool mixer adds inputs but no pre-made buses; other mixers keep the old padding', async () => {
  const { mixerImportPlan } = await import('../../src/utils/workspace');
  const pool = { profile: { dsp_inputs: { mono: 44 }, bus_pool: { total_slots: 30 } } };
  const channels = [{ attributes: { channel_number: 1 } }];
  const plan = mixerImportPlan(channels, [], { inputs: 48, buses: 20 }, pool);
  expect(plan.busPool).toBe(true);
  expect(plan.slots).toBe(30);
  expect(plan.outputs).toEqual([]);
  expect(plan.channels).toHaveLength(43); // up to 44 DSP mono strips, not the flat 48
  expect(plan.channels[0]).toEqual({ channel_number: 2 });
  // no mono count stated: fall back to the typed/flat input count
  expect(mixerImportPlan([], [], { inputs: 16, buses: 4 }, { profile: { bus_pool: { total_slots: 8 } } }).channels).toHaveLength(16);
  // no specs.mixer (422) or a simple profile: the old flat padding, buses included
  for (const summary of [null, { profile: { dsp_inputs: { mono: 16 }, bus_pool: null } }]) {
    const old = mixerImportPlan([], [], { inputs: 8, buses: 3 }, summary);
    expect(old.busPool).toBe(false);
    expect(old.channels).toHaveLength(8);
    expect(old.outputs.map((o) => o.mode)).toEqual(['mono', 'mono', 'mono']);
  }
});

test('the strip picker helpers: ranges, filters, shift-click and selection edits', async () => {
  const h = await import('../../src/utils/workspace');
  expect(h.parseNumberRanges('1-3, 8; 10–11 junk 5-4 0x')).toEqual([1, 2, 3, 4, 5, 8, 10, 11]);
  expect(h.parseNumberRanges('')).toEqual([]);
  expect(h.parseNumberRanges('1-99999', 10)).toHaveLength(11); // a typo cannot hang the page

  const items = [
    { id: 'a', kind: 'input', number: '1-2', label: 'Keys', group: 'keys' },
    { id: 'b', kind: 'input', number: '3', label: 'Kick', group: 'drums' },
    { id: 'c', kind: 'input', number: '4', label: 'Snare', group: 'drums' },
    { id: 'd', kind: 'fx', number: 'FX', label: 'Plate' },
    { id: 'e', kind: 'fxsend', number: 'FX send', label: 'Plate send' },
    { id: 'f', kind: 'mix', number: 'aux', label: 'Wedge 3' },
  ];
  expect(h.stripChannelNumbers(items[0])).toEqual([1, 2]);
  expect(h.stripChannelNumbers(items[3])).toEqual([]);
  // a range selects inputs by channel number (a ganged pair counts for both numbers), never FX/mixes
  expect(h.idsInRanges(items, '2-3')).toEqual(['a', 'b']);
  expect(h.idsInRanges(items, '3')).toEqual(['b']);
  expect(h.idsInRanges(items, 'nope')).toEqual([]);

  expect(h.filterStripItems(items, { query: 'plate' }).map((i) => i.id)).toEqual(['d', 'e']);
  expect(h.filterStripItems(items, { kinds: ['fx', 'fxsend'] }).map((i) => i.id)).toEqual(['d', 'e']);
  expect(h.filterStripItems(items, { group: 'drums' }).map((i) => i.id)).toEqual(['b', 'c']);
  expect(h.filterStripItems(items, { query: '3' }).map((i) => i.id)).toEqual(['b', 'f']); // number or label

  const order = items.map((i) => i.id);
  expect(h.rangeBetween(order, 'b', 'e')).toEqual(['b', 'c', 'd', 'e']);
  expect(h.rangeBetween(order, 'e', 'b')).toEqual(['b', 'c', 'd', 'e']);
  expect(h.rangeBetween(order, 'zz', 'b')).toEqual(['b']);

  expect(h.selectIds(['a'], ['a', 'b'])).toEqual(['a', 'b']);
  expect(h.deselectIds(['a', 'b', 'c'], ['b'])).toEqual(['a', 'c']);
  // invert only touches the visible rows
  expect(h.invertIds(['a', 'b'], ['b', 'c'])).toEqual(['a', 'c']);

  const sum = h.summariseSelection(items, ['a', 'b', 'c', 'd', 'e', 'f', 'gone'], 3);
  expect(sum.shown.map((i) => i.id)).toEqual(['a', 'b', 'c']);
  expect(sum.more).toBe(3);
  expect(sum.total).toBe(6);
});

test('soft patch by port: grouping, socket rows, paging and the expansion editor helpers', async () => {
  const h = await import('../../src/utils/workspace');
  const ports = [
    { device_id: 'D1', device_name: 'Desk', port_id: 'in-dante', direction: 'in', connector: 'dante', channels: 128 },
    { device_id: 'D1', device_name: 'Desk', port_id: 'out-dante', direction: 'out', connector: 'dante', channels: 64 },
    { device_id: 'D2', device_name: 'AR2412', port_id: 'in-xlr3', direction: 'in', connector: 'xlr3', channels: 24 },
    { device_id: 'D2', device_name: 'AR2412', port_id: 'io', direction: 'both', connector: 'ethercon', channels: 1 },
  ];
  const inGroups = h.groupPortsByDevice(ports, 'in');
  expect(inGroups.map((g) => [g.device_name, g.ports.map((p) => p.port_id)])).toEqual([
    ['Desk', ['in-dante']],
    ['AR2412', ['in-xlr3', 'io']],
  ]);
  expect(h.groupPortsByDevice(ports, 'out').map((g) => g.ports.map((p) => p.port_id))).toEqual([['out-dante'], ['io']]);

  const sockets = Array.from({ length: 128 }, (_, i) => ({
    key: `D1:in-dante:${i + 1}`,
    device_id: 'D1',
    port_id: 'in-dante',
    socket: 128 - i, // deliberately unsorted
    dsp_source_channel_id: i === 127 ? 'c1' : undefined,
  }));
  const rows = h.portSockets(sockets, ports[0], 'dsp_source', new Map([['c1', 7]]));
  expect(rows).toHaveLength(128);
  expect(rows[0].socket).toBe(1);
  expect(rows[0]).toMatchObject({ owner: 'c1', ownerNumber: 7 }); // socket 1 is the unsorted last item
  expect(h.firstFreeSocket(rows)).toBe(2);
  expect(h.firstFreeSocket(rows, 100)).toBe(100);
  expect(h.pageOf(rows, 2, 64)[0].socket).toBe(65);
  expect(h.pageOf(rows, 2, 64)).toHaveLength(64);
  expect(h.portSockets(sockets, null, 'dsp_source')).toEqual([]);

  expect(h.expansionPayload([
    { protocol: ' Dante ', channels_in: '64', channels_out: 0 },
    { protocol: 'madi', channels_in: 0, channels_out: 0 }, // empty card dropped
    { protocol: '', channels_in: 4 },
  ])).toEqual([{ protocol: 'dante', channels_in: 64, channels_out: 0 }]);
  expect(h.expansionLimit({ max_channels: 64, max_channels_in: 32 }, 'in')).toBe(32);
  expect(h.expansionLimit({ max_channels: 64, max_channels_in: 32 }, 'out')).toBe(64);
  expect(h.expansionLimit({}, 'in')).toBeNull();
  const rowsForm = h.expansionFormRows([{ protocol: 'dante', slots: 1, max_channels: 64 }]);
  expect(rowsForm).toEqual([{ protocol: 'dante', slots: 1, max_channels: 64, max_channels_in: null, max_channels_out: null }]);
  expect(h.expansionFromForm([{ protocol: ' DSNAKE ', slots: '', max_channels: '48', max_channels_in: 24, max_channels_out: null }, { protocol: '' }])).toEqual([
    { protocol: 'dsnake', slots: null, max_channels: 48, max_channels_in: 24, max_channels_out: null },
  ]);
  // every strip kind has an icon, including FX sends (they were missing from the tray before)
  for (const kind of ['input', 'fx', 'mix', 'fxsend', 'dca', 'empty']) expect(h.stripKindIcon(kind)).not.toBe('help_outline');
  expect(h.stripKindIcon('nope')).toBe('help_outline');
});


test('shift-click selects the rows between the anchor and the clicked row over the visible rows only', async () => {
  const { toggleRowSelection, orderByNumber } = await import('../../src/utils/workspace');
  const visible = ['c2', 'c4', 'c6', 'c8']; // a filtered view: odd rows are hidden
  const first = toggleRowSelection([], { id: 'c2', visibleIds: visible });
  expect(first).toEqual({ selected: ['c2'], anchor: 'c2' });
  const range = toggleRowSelection(first.selected, { id: 'c6', shift: true, anchor: first.anchor, visibleIds: visible });
  expect(range.selected).toEqual(['c2', 'c4', 'c6']);
  // shift-clicking a selected row switches the whole span off
  const off = toggleRowSelection(range.selected, { id: 'c4', shift: true, anchor: 'c2', visibleIds: visible });
  expect(off.selected).toEqual(['c6']);
  // a stale anchor (filtered away) falls back to a plain toggle
  expect(toggleRowSelection(['c2'], { id: 'c8', shift: true, anchor: 'gone', visibleIds: visible }).selected).toEqual(['c2', 'c8']);
  // the order auto patch uses is the channel order, whatever order the clicks came in
  const numbers = new Map([['a', 3], ['b', 1], ['c', 2]]);
  expect(orderByNumber(['a', 'b', 'c'], numbers)).toEqual(['b', 'c', 'a']);
});

test('range box, select-all and invert only touch the visible rows', async () => {
  const { idsInRanges, selectIds, deselectIds, invertIds, filterStripItems } = await import('../../src/utils/workspace');
  const items = Array.from({ length: 12 }, (_, i) => ({ id: `c${i + 1}`, kind: 'input', number: String(i + 1), label: i < 6 ? `Vox ${i + 1}` : `Gtr ${i + 1}` }));
  const visible = filterStripItems(items, { query: 'vox' });
  expect(visible).toHaveLength(6);
  const visibleIds = visible.map((i) => i.id);
  expect(idsInRanges(visible, '2-4, 11')).toEqual(['c2', 'c3', 'c4']); // 11 is hidden by the filter
  const all = selectIds(['c12'], visibleIds);
  expect(all).toEqual(['c12', ...visibleIds]);
  expect(invertIds(all, visibleIds)).toEqual(['c12']); // the hidden selection survives an invert
  expect(deselectIds(all, visibleIds)).toEqual(['c12']);
});

test('the built-in FX helpers', async () => {
  const { fxIsConfigured, fxConfiguredCount, fxResetEngine } = await import('../../src/utils/workspace');
  const placeholder = { id: 'fx1', name: 'FX 1', type: 'other', sends: [] };
  expect(fxIsConfigured(placeholder)).toBe(false);
  expect(fxIsConfigured({ ...placeholder, name: 'Plate' })).toBe(true);
  expect(fxIsConfigured({ ...placeholder, type: 'reverb' })).toBe(true);
  expect(fxIsConfigured({ ...placeholder, sends: ['c1'] })).toBe(true);
  expect(fxConfiguredCount([placeholder, { ...placeholder, id: 'fx2', type: 'delay' }])).toBe(1);
  const reset = fxResetEngine({ id: 'fx2', name: 'Plate', type: 'reverb', sends: ['c1'], stereo_return: false, send_mode: 'stereo' }, 2);
  expect(reset).toEqual({ id: 'fx2', name: 'FX 2', type: 'other', stereo_return: true, send_mode: 'mono', sends: [] });
  expect(fxIsConfigured(reset)).toBe(false);
});

test('auto patch bodies and bulk clears for inputs, direct outs and bus outputs', async () => {
  const { autoPatchBody, bulkClearBody, fieldOfMode, softFieldInfo } = await import('../../src/utils/workspace');
  expect(['in', 'out', 'bus'].map(fieldOfMode)).toEqual(['dsp_source', 'direct_out', 'out_socket']);
  expect(softFieldInfo('out_socket').idsKey).toBe('bus_ids');
  expect(softFieldInfo('direct_out').direction).toBe('out');
  const port = { device_id: 'd1', port_id: 'out-xlr3' };
  expect(autoPatchBody('direct_out', ['c1', 'c2'], port, { start: 5, skip: false, dry: true })).toEqual({
    field: 'direct_out',
    channel_ids: ['c1', 'c2'],
    device_id: 'd1',
    port_id: 'out-xlr3',
    start_socket: 5,
    skip_taken: false,
    dry_run: true,
  });
  const bus = autoPatchBody('out_socket', ['b1'], port, { start: 0 });
  expect(bus.bus_ids).toEqual(['b1']);
  expect('channel_ids' in bus).toBe(false);
  expect(bus.start_socket).toBe(1); // never below 1
  expect(bulkClearBody('out_socket', ['b1', 'b2'])).toEqual({
    field: 'out_socket',
    assignments: [{ bus_id: 'b1', ref: null }, { bus_id: 'b2', ref: null }],
  });
  expect(bulkClearBody('dsp_source', ['c1']).assignments[0]).toEqual({ channel_id: 'c1', ref: null });
});

test('output sockets show whether a direct out or a bus holds them', async () => {
  const { portSocketsOut, groupPortsByDevice } = await import('../../src/utils/workspace');
  const sockets = [
    { device_id: 'd1', port_id: 'out-xlr3', socket: 2, direct_out_channel_id: 'c1' },
    { device_id: 'd1', port_id: 'out-xlr3', socket: 1, out_socket_bus_id: 'b1' },
    { device_id: 'd1', port_id: 'out-xlr3', socket: 3 },
    { device_id: 'd2', port_id: 'out-xlr3', socket: 1 },
  ];
  const rows = portSocketsOut(sockets, { device_id: 'd1', port_id: 'out-xlr3' }, new Map([['c1', 7]]), new Map([['b1', 2]]));
  expect(rows.map((r) => [r.socket, r.ownerKind, r.ownerLabel])).toEqual([
    [1, 'bus', 'Mix 2'],
    [2, 'channel', 'Ch 7'],
    [3, null, ''],
  ]);
  expect(portSocketsOut(sockets, null, new Map(), new Map())).toEqual([]);
  // the port list for outputs includes 'both' ports and skips input-only ones
  const ports = [
    { device_id: 'd1', device_name: 'Box', port_id: 'in-xlr3', direction: 'in' },
    { device_id: 'd1', device_name: 'Box', port_id: 'out-xlr3', direction: 'out' },
    { device_id: 'd2', device_name: 'Card', port_id: 'dante', direction: 'both' },
  ];
  expect(groupPortsByDevice(ports, 'out').flatMap((g) => g.ports.map((p) => p.port_id))).toEqual(['out-xlr3', 'dante']);
});

// --- soft patch in the signal flow and the chain editor --------------------------------------

const softChannel = {
  id: 'ch1',
  kind: 'channel',
  name: 'Vox',
  attributes: {
    channel_number: 5,
    list_id: 'L',
    dsp_source: { device_id: 'box', port_id: 'in-xlr3', socket: 5 },
  },
};
const softDevices = [
  { id: 'box', name: 'AR2412', kind: 'analog_stagebox', ports: [{ id: 'in-xlr3', direction: 'in', connector: 'xlr3', channels: 24 }] },
  { id: 'snake', name: 'Snake', kind: 'analog_snake', ports: [] },
  { id: 'desk', name: 'GLD', kind: 'mixer', device_type: 'mixer', sound_list_id: 'L', ports: [] },
];

test('the soft-patched hop is found, kept last, and described', async () => {
  const { lockedStepIndex, withLockedLast, softPatchInfo, chainStepsWithLock } = await import('../../src/utils/workspace');
  const steps = [{ device_id: 'box' }, { device_id: 'snake' }];
  expect(lockedStepIndex(softChannel, steps)).toBe(0);
  expect(lockedStepIndex({ attributes: {} }, steps)).toBe(-1);
  expect(withLockedLast(softChannel, steps).map((s: { device_id: string }) => s.device_id)).toEqual(['snake', 'box']);
  // no soft patch / already last: order untouched
  expect(withLockedLast({ attributes: {} }, steps)).toEqual(steps);
  expect(withLockedLast(softChannel, [{ device_id: 'snake' }, { device_id: 'box' }]).map((s: { device_id: string }) => s.device_id)).toEqual(['snake', 'box']);
  expect(softPatchInfo(softChannel, softDevices)).toMatchObject({ socket: 5, connector: 'XLR3', label: 'In 5 (XLR3)', device_name: 'AR2412' });
  expect(softPatchInfo({ attributes: {} }, softDevices)).toBeNull();
  // the chain editor starts from: snake first, the locked stagebox last
  const form = chainStepsWithLock(softChannel, steps, softDevices);
  expect(form.map((s: { device_id: string; locked: boolean }) => [s.device_id, s.locked])).toEqual([['snake', false], ['box', true]]);
  // a chain that lost the hop gets it back (locked, labelled), so saving never drops it
  const restored = chainStepsWithLock(softChannel, [{ device_id: 'snake' }], softDevices);
  expect(restored.at(-1)).toMatchObject({ device_id: 'box', locked: true, patch_label: 'In 5', connector: 'xlr3' });
  // a channel without a soft patch is untouched
  expect(chainStepsWithLock({ attributes: {} }, steps, softDevices)).toEqual(steps);
});

test('the signal flow of a soft-patched channel shows the socket and ends on the console strip', async () => {
  const { channelFlowTree } = await import('../../src/utils/workspace');
  const edges = [
    { id: 'e0', signal: 'audio', src_device_id: 'snake', dst_device_id: 'box', src_port: 'out', dst_port: 'in-xlr3',
      attributes: { chain: 'ch1', position: 0, dst_socket: 5, connector: 'xlr3', patch_label: 'Out 2' } },
    { id: 'e1', signal: 'audio', src_device_id: 'box', dst_device_id: 'ch1', src_port: 'out', dst_port: 'in',
      attributes: { chain: 'ch1', position: 1, connector: 'xlr3', patch_label: 'In 5' } },
  ];
  const steps = [
    { device_id: 'snake', connector: '', patch_label: 'Out 2', in_port: '', out_port: '' },
    { device_id: 'box', connector: 'xlr3', patch_label: 'In 5', in_port: '', out_port: '' },
  ];
  const [root] = channelFlowTree(softChannel, edges, softDevices, 'Vox', steps);
  // route: snake -> box (soft patch) -> channel strip, source side first
  expect(root.label).toBe('Snake');
  const box = root.children[0];
  expect(box.label).toBe('AR2412');
  expect(box.soft_patch).toEqual({ connector: 'XLR3', socket: 5 });
  const strip = box.children[0];
  expect(strip.kind).toBe('channel');
  expect(strip.label).toBe('GLD · Ch 5 Vox');
  expect(strip.connector).toBe('xlr3');
  expect(strip.patch_label).toBe('In 5');
});

// --- bus endpoints, split sources, history names, grid picker, review fixes -----------------------------

test('a stereo bus needs two adjacent sockets and endpoints read as "AR2412 · Out 3–4"', async () => {
  const w = await import('../../src/utils/workspace');
  expect([w.busWidth('mono'), w.busWidth('stereo'), w.busWidth('lcr'), w.busWidth('odd')]).toEqual([1, 2, 3, 1]);
  expect(w.socketRunText([3, 4])).toBe('3–4');
  expect(w.socketRunText([3, 7])).toBe('3 / 7');
  expect(w.socketRunText([5])).toBe('5');
  const names = new Map([['box', 'AR2412']]);
  const stereo = { id: 'e1', refs: [{ device_id: 'box', port_id: 'out-xlr3', socket: 3 }, { device_id: 'box', port_id: 'out-xlr3', socket: 4 }] };
  expect(w.endpointLabel(stereo, names)).toBe('AR2412 · Out 3–4');
  expect(w.endpointLabel(stereo, names, { out: 'Ut' })).toBe('AR2412 · Ut 3–4');
  expect(w.endpointSides(stereo, 'stereo')).toBe('L 3, R 4');
  expect(w.endpointSides({ refs: [{ socket: 9 }] }, 'mono')).toBe('9');
  // a mono endpoint on a bus switched to stereo is short one socket
  const bus = { mode: 'stereo', out_endpoints: [{ id: 'e', refs: [{ socket: 3 }] }, stereo] };
  expect(w.endpointShortages(bus)).toEqual([{ endpoint: bus.out_endpoints[0], have: 1, need: 2 }]);
  expect(w.endpointShortages({ mode: 'mono', out_endpoints: [{ refs: [{ socket: 1 }] }] })).toEqual([]);
});

test('a tap claims a run of free adjacent sockets, or says it does not fit', async () => {
  const w = await import('../../src/utils/workspace');
  const rows = [1, 2, 3, 4].map((socket) => ({ socket, owner: socket === 3 ? 'other' : null }));
  expect(w.busRunAt(rows, 1, 2)?.map((r) => r.socket)).toEqual([1, 2]);
  expect(w.busRunAt(rows, 2, 2)).toBeNull(); // 3 is taken
  expect(w.busRunAt(rows, 4, 2)).toBeNull(); // runs off the port
  expect(w.busRunAt(rows, 3, 1, 'other')?.length).toBe(1); // a bus's own socket counts as free
  expect(w.planRowText({ channel_number: 2, name: 'IEM', sockets: [3, 4], socket: 3 }, 'Mix')).toBe('Mix 2 IEM → 3–4');
  expect(w.planRowText({ channel_number: 5, socket: 12 }, 'Ch')).toBe('Ch 5 → 12');
});

test('auto patch bodies carry append for buses and allow_shared for inputs only', async () => {
  const { autoPatchBody } = await import('../../src/utils/workspace');
  const port = { device_id: 'd', port_id: 'out-xlr3' };
  expect(autoPatchBody('out_socket', ['b'], port, { append: true, shared: true })).toMatchObject({ field: 'out_socket', bus_ids: ['b'], append: true });
  expect(autoPatchBody('out_socket', ['b'], port, { append: true, shared: true })).not.toHaveProperty('allow_shared');
  expect(autoPatchBody('dsp_source', ['c'], { device_id: 'd', port_id: 'in' }, { shared: true })).toMatchObject({ allow_shared: true });
  expect(autoPatchBody('dsp_source', ['c'], port, {})).not.toHaveProperty('allow_shared');
  expect(autoPatchBody('direct_out', ['c'], port, { append: true })).not.toHaveProperty('append');
});

test('a split source shows every owner of the socket and builds the hint names', async () => {
  const { portSockets, sharedChannelsText, numberedLabel } = await import('../../src/utils/workspace');
  const rows = portSockets(
    [
      { device_id: 'd', port_id: 'in', socket: 1, dsp_source_channel_ids: ['a', 'b'], dsp_source_channel_id: 'a' },
      { device_id: 'd', port_id: 'in', socket: 2, dsp_source_channel_ids: ['a'], dsp_source_channel_id: 'a' },
      { device_id: 'd', port_id: 'in', socket: 3 },
    ],
    { device_id: 'd', port_id: 'in' },
    'dsp_source',
    new Map([['a', 1], ['b', 7]]),
  );
  expect(rows.map((r) => [r.shared, r.owners.length])).toEqual([[true, 2], [false, 1], [false, 0]]);
  expect(rows[0].ownerLabel).toBe('Ch 1');
  expect(sharedChannelsText([{ channel_number: 3 }, { channel_number: 4 }])).toBe('Ch 3, Ch 4');
  expect(sharedChannelsText([])).toBe('');
  // "Ch 1 L" must not become "Ch 1 Ch 1 L"
  expect(numberedLabel('Ch', 1, 'Ch 1 L')).toBe('Ch 1 L');
  expect(numberedLabel('Ch', 1, 'Ch1')).toBe('Ch1');
  expect(numberedLabel('Ch', 12, 'Ch 1 L')).toBe('Ch 12 Ch 1 L');
  expect(numberedLabel('Ch', 3, 'Kick')).toBe('Ch 3 Kick');
  expect(numberedLabel('Mix', 2, '')).toBe('Mix 2');
});

test('history step names are translated by action, then verb + noun, then the English label', async () => {
  const { historyStepLabel } = await import('../../src/utils/workspace');
  const dict: Record<string, string> = {
    'history.actions.update_channel': 'Ändra kanal',
    'history.verbs.create': 'Skapa',
    'history.verbs.delete': 'Ta bort',
    'history.nouns.fixture': 'armatur',
  };
  const tr = { has: (k: string) => k in dict, t: (k: string) => dict[k] };
  expect(historyStepLabel({ action: 'update_channel', label: 'Update channel' }, tr)).toBe('Ändra kanal');
  expect(historyStepLabel({ action: 'create_fixture', label: 'Create fixture' }, tr)).toBe('Skapa armatur');
  // a noun without a translation falls back to the server's label, never a half-translated string
  expect(historyStepLabel({ action: 'create_mystery', label: 'Create mystery' }, tr)).toBe('Create mystery');
  expect(historyStepLabel({ action: 'frobnicate_x', label: 'Frobnicate x' }, tr)).toBe('Frobnicate x');
  expect(historyStepLabel({ action: '', label: 'Anything' }, tr)).toBe('Anything');
  expect(historyStepLabel({ action: 'odd_thing' }, tr)).toBe('odd thing');
});

test('every history action the Swedish and English dictionaries name has both translations', async () => {
  // the transpiler may wrap the ES default export once more
  const unwrap = (m: { default: any }) => (m.default?.history ? m.default : m.default?.default);
  const en = unwrap(await import('../../src/i18n/locales/en.js'));
  const sv = unwrap(await import('../../src/i18n/locales/sv.js'));
  for (const part of ['actions', 'verbs', 'nouns'] as const) {
    expect(Object.keys(sv.history[part]).sort()).toEqual(Object.keys(en.history[part]).sort());
  }
  for (const key of ['set_dcas', 'set_fx', 'bulk_soft_patch', 'auto_soft_patch', 'set_bus_socket', 'add_to_faders', 'set_fader_layout', 'replace_channel_chain', 'set_console_profile', 'link_channels']) {
    expect(sv.history.actions[key], key).toBeTruthy();
    expect(sv.history.actions[key]).not.toBe(en.history.actions[key]);
  }
});

test('the picker grid pages long lists and a shift-tap selects the run between two tiles', async () => {
  const { pageOf, toggleRowSelection } = await import('../../src/utils/workspace');
  const ids = Array.from({ length: 250 }, (_, i) => `s${i + 1}`);
  expect(pageOf(ids, 1, 120)).toHaveLength(120);
  expect(pageOf(ids, 3, 120)).toHaveLength(10);
  let state = toggleRowSelection([], { id: 's2', visibleIds: ids });
  state = toggleRowSelection(state.selected, { id: 's5', shift: true, anchor: state.anchor, visibleIds: ids });
  expect(state.selected).toEqual(['s2', 's3', 's4', 's5']);
  // tapping a selected tile again turns it off
  expect(toggleRowSelection(state.selected, { id: 's3', visibleIds: ids }).selected).not.toContain('s3');
});

test('the mixer proposal response becomes the need line and one suggestion per candidate', async () => {
  const { proposalFromResponse } = await import('../../src/utils/workspace');
  const out = proposalFromResponse({ need: { strips: 24, mixes: 6 }, candidates: [{ product_id: '7', name: 'GLD-80', fits: true }] });
  expect(out.need).toEqual({ strips: 24, mixes: 6 });
  expect(out.suggestions).toEqual([{ product_id: '7', name: 'GLD-80', fits: true, id: '7' }]);
  expect(proposalFromResponse(undefined)).toEqual({ need: null, suggestions: [] });
});

test('the flow starts at the typed source and never at the console link', async () => {
  const { channelFlowTree } = await import('../../src/utils/workspace');
  const gld = { id: 'gld', name: 'GLD-80', kind: 'mixer', sound_list_id: 'list', ports: [{ id: 'out-ethernet', direction: 'out', connector: 'ethernet' }] };
  const box = {
    id: 'box',
    name: 'AR2412',
    kind: 'analog_stagebox',
    ports: [
      { id: 'in-xlr3', direction: 'in', connector: 'xlr3', channels: 24 },
      { id: 'in-ethernet', direction: 'in', connector: 'ethernet' },
    ],
  };
  const channel = { id: 'ch1', kind: 'channel', name: 'Ch 1', attributes: { list_id: 'list', channel_number: 1, device: 'SM58' } };
  const edges = [
    // the console's own link into the stagebox: not where the signal comes from
    { id: 'link', signal: 'audio', src_device_id: 'gld', src_port: 'out-ethernet', dst_device_id: 'box', dst_port: 'in-ethernet', attributes: {} },
    { id: 'hop', signal: 'audio', src_device_id: 'box', src_port: 'out', dst_device_id: 'ch1', dst_port: 'in', attributes: { chain: 'ch1', position: 0 } },
  ];
  const tree = channelFlowTree(channel, edges, [gld, box, channel], 'Ch 1', [{ device_id: 'box', connector: 'xlr3', patch_label: 'In 1' }]);
  expect(tree[0].kind).toBe('source');
  expect(tree[0].label).toBe('SM58');
  expect(JSON.stringify(tree)).not.toContain('out-ethernet');
  // no typed source and no linked gear: the console link is still not invented as a source
  const bare = { ...channel, attributes: { list_id: 'list', channel_number: 1 } };
  const without = channelFlowTree(bare, edges, [gld, box, bare], 'Ch 1', [{ device_id: 'box', connector: 'xlr3', patch_label: 'In 1' }]);
  expect(without[0].kind).not.toBe('source');
});


test('a name typed into Edit patch becomes a pass-through device guessed from the name', () => {
  const snake = guessChainDevice('Snake 16');
  expect(snake.device_type).toBe('analog_stagebox');
  expect(snake.count).toBe(16);
  expect(snake.passive).toBe(true);
  expect(snake.ports).toEqual([
    { direction: 'in', connector: 'xlr3', count: 16 },
    { direction: 'out', connector: 'xlr3', count: 16 },
  ]);
  expect(guessChainDevice('Splitter').device_type).toBe('split');
  expect(guessChainDevice('Patch panel 24').device_type).toBe('patchbay');
  expect(guessChainDevice('Patch panel 24').count).toBe(24);
  expect(guessChainDevice('Dante stagebox 32').device_type).toBe('digital_stagebox');
  expect(guessChainDevice('Dante stagebox 32').passive).toBe(false);
  // a model number is not a channel count; an unknown name is a plain 1-in 1-out device
  const model = guessChainDevice('AR2412');
  expect(model.device_type).toBe('other');
  expect(model.count).toBe(1);
  expect(guessChainDevice('').ports).toHaveLength(2);
});

test('the typed chain device is created with exactly the typed name, both directions, no mains for a snake', () => {
  const body = newChainDeviceBody('  Snake 8 ');
  expect(body.name).toBe('Snake 8');
  expect(body.device_type).toBe('analog_stagebox');
  expect(body.power_inlet).toBe('none');
  expect(body.ports.map((p: { direction: string }) => p.direction).sort()).toEqual(['in', 'out']);
  expect(body.ports.every((p: { count: number }) => p.count === 8)).toBe(true);
  expect(newChainDeviceBody('Dante stagebox').power_inlet).not.toBe('none');
});

test('typing in the step picker offers Create unless a device with that exact name exists', () => {
  const options = [
    { label: 'AR2412', value: 'd1' },
    { label: 'Snake 16', value: 'd2' },
  ];
  const label = (text: string) => `Create "${text}"`;
  const fresh = chainDeviceOptions(options, 'Snake 8', label);
  expect(fresh[0]).toEqual({ label: 'Create "Snake 8"', value: 'new:Snake 8', create: true });
  expect(fresh.slice(1)).toEqual([]); // 'snake 8' matches no existing label
  // a partial match lists the match after the create option
  expect(chainDeviceOptions(options, 'snake', label).map((o: { value: string }) => o.value)).toEqual(['new:snake', 'd2']);
  // the exact name (any case) offers only that device: no duplicate
  expect(chainDeviceOptions(options, ' snake 16 ', label)).toEqual([options[1]]);
  // nothing typed lists everything
  expect(chainDeviceOptions(options, '', label)).toEqual(options);
  expect(findDeviceByName([{ id: 'd1', name: 'AR2412' }], ' ar2412 ')?.id).toBe('d1');
  expect(findDeviceByName([{ id: 'd1', name: 'AR2412' }], 'AR')).toBeNull();
  expect(isNewDeviceValue(newDeviceValue('X'))).toBe(true);
  expect(newDeviceName('new: Foo ')).toBe('Foo');
  expect(newDeviceName('uuid-1')).toBe('');
});


test('pair captions and short names fit a tile', async () => {
  const { pairCaption, shortDeviceName } = await import('../../src/utils/workspace');
  expect(pairCaption('Drums L', 'Drums R')).toBe('Drums L/R');
  expect(pairCaption('Kick', 'Snare')).toBe('Kick · Snare');
  expect(pairCaption('Kick', '')).toBe('Kick');
  expect(pairCaption('', '')).toBe('');
  // an unsuffixed shared name is not collapsed: two channels that merely have the same name
  expect(pairCaption('Keys', 'Keys')).toBe('Keys L/R');
  expect(shortDeviceName('AR2412')).toBe('AR2412');
  expect(shortDeviceName('Allen & Heath AR2412')).toBe('Allen');
  expect(shortDeviceName('Digital stagebox rack')).toBe('Digital');
  expect(shortDeviceName('ABCDEFGHIJKLMNOP')).toBe('ABCDEFGH…');
  expect(shortDeviceName('')).toBe('?');
});

test('soft patch tiles show number, name, routing, pairing and split badge; pairs are bridged', async () => {
  const { softPatchTiles, routingShort, busRoutingShort, softTileTitle } = await import('../../src/utils/workspace');
  const names = new Map([['box', 'AR2412'], ['dante', 'Allen & Heath Dante card']]);
  const ref = (device, port, socket) => ({ device_id: device, port_id: port, socket });
  const strips = [
    { id: 'c1', channel_number: 1, source_label: 'Keys L', dsp_source: ref('box', 'in-xlr3', 5), is_stereo_linked: true, stereo_link_role: 'primary', stereo_partner_id: 'c2', shared_with: [{ channel_id: 'c9', channel_number: 9 }] },
    { id: 'c2', channel_number: 2, source_label: 'Keys R', dsp_source: ref('dante', 'in-dante', 12), is_stereo_linked: true, stereo_link_role: 'secondary', stereo_partner_id: 'c1', shared_with: [] },
    { id: 'c3', channel_number: 3, source_label: '', dsp_source: null, direct_out: ref('box', 'out-xlr3', 2), dsp_source_orphaned: false },
    { id: 'c4', channel_number: 4, source_label: 'Gone', dsp_source: ref('ghost', 'in-x', 1), dsp_source_orphaned: true },
  ];
  const tiles = softPatchTiles(strips, { mode: 'in', deviceNames: names });
  expect(tiles.map((t) => [t.number, t.name, t.routing, t.patched, t.pair, t.bridge, t.shared])).toEqual([
    [1, 'Keys L', 'AR2412 · 5', true, 'L', 'start', 2],
    [2, 'Keys R', 'Allen · 12', true, 'R', 'end', 0],
    [3, '', '—', false, null, null, 0],
    [4, 'Gone', '? · 1', true, null, null, 0],
  ]);
  expect(tiles[3].orphaned).toBe(true); // a socket whose device is gone is flagged
  expect(tiles[1].routingTitle).toBe('Allen & Heath Dante card · in-dante #12');
  expect(softTileTitle(tiles[0])).toBe('Ch 1 Keys L · AR2412 · in-xlr3 #5 · L (stereo)');
  // direct-out mode reads the other field and has no split badge
  const outs = softPatchTiles(strips, { mode: 'out', deviceNames: names });
  expect(outs[2].routing).toBe('AR2412 · 2');
  expect(outs[3].orphaned).toBe(false); // the orphan flag follows the field of the mode
  expect(outs.every((t) => t.shared === 0)).toBe(true);
  // a pair is bridged only when its legs are neighbours in the shown order
  const apart = softPatchTiles([strips[0], strips[2], strips[1]], { mode: 'in', deviceNames: names });
  expect(apart.map((t) => t.bridge)).toEqual([null, null, null]);
  expect(routingShort(null, names).text).toBe('—');
});

test('bus tiles show the first endpoint, extra endpoints and a mismatch', async () => {
  const { softPatchTiles, busRoutingShort } = await import('../../src/utils/workspace');
  const names = new Map([['box', 'AR2412']]);
  const ep = (...sockets) => ({ id: `e${sockets[0]}`, refs: sockets.map((s) => ({ device_id: 'box', port_id: 'out-xlr3', socket: s })) });
  const buses = [
    { id: 'b1', channel_number: 1, source_label: 'Main', mode: 'stereo', out_endpoints: [ep(3, 4), ep(9, 10)] },
    { id: 'b2', channel_number: 2, source_label: 'Aux', mode: 'mono', out_endpoints: [] },
    { id: 'b3', channel_number: 3, source_label: 'IEM', mode: 'stereo', out_endpoints: [ep(7)] },
  ];
  const tiles = softPatchTiles(buses, { mode: 'bus', deviceNames: names });
  expect(tiles.map((t) => [t.routing, t.modeBadge, t.endpoints, t.shortage, t.patched])).toEqual([
    ['AR2412 · 3–4 +1', 'ST', 2, false, true],
    ['—', 'M', 0, false, false],
    ['AR2412 · 7', 'ST', 1, true, true], // a stereo bus with one socket needs two
  ]);
  expect(busRoutingShort(buses[0], names).title).toBe('AR2412 · Out 3–4  ·  AR2412 · Out 9–10');
  expect(tiles.every((t) => t.pair === null && t.shared === 0)).toBe(true);
});
