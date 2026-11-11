import { test, expect } from '@playwright/test';
import {
  channelFlowTree,
  directConnections,
  feedingStageboxes,
  mixerInputChoices,
  patchSummary,
  portLabelOf,
  socketOptions,
  splitSocket,
} from '../../src/utils/workspace';

// A console with one channel list, a stagebox on stage and an ethernet switch between them.
const mixer = {
  id: 'mixer',
  name: 'Desk',
  kind: 'mixer',
  domain: 'audio',
  sound_list_id: 'list',
  ports: [
    { id: 'in-xlr3', direction: 'in', signal: 'audio', connector: 'xlr3', channels: 16 },
    { id: 'out-xlr3', direction: 'out', signal: 'audio', connector: 'xlr3', channels: 8 },
  ],
};
const stagebox = {
  id: 'box',
  name: 'Stagebox',
  kind: 'digital_stagebox',
  domain: 'audio',
  ports: [
    { id: 'in-xlr3', direction: 'in', signal: 'audio', connector: 'xlr3', channels: 32 },
    { id: 'out-dante', direction: 'out', signal: 'audio', connector: 'dante', channels: 64 },
  ],
};
const switchNode = {
  id: 'sw',
  name: 'Switch',
  kind: 'network_switch',
  domain: 'audio',
  ports: [
    { id: 'p1', direction: 'in', signal: 'data', connector: 'rj45' },
    { id: 'p2', direction: 'out', signal: 'data', connector: 'rj45' },
  ],
};
const channel = (id, n) => ({
  id,
  name: `Ch ${n}`,
  kind: 'channel',
  domain: 'audio',
  attributes: { list_id: 'list', channel_number: n },
  ports: [
    { id: 'in', direction: 'in', signal: 'audio' },
    { id: 'out', direction: 'out', signal: 'audio' },
  ],
});
const devices = [mixer, stagebox, switchNode, channel('ch2', 2), channel('ch3', 3)];
const edge = (id, src, srcPort, dst, dstPort, signal = 'audio', extra = {}) => ({
  id,
  signal,
  src_device_id: src,
  src_port: srcPort,
  dst_device_id: dst,
  dst_port: dstPort,
  attributes: {},
  ...extra,
});

test('a stagebox patched straight into the mixer is a feeding stagebox', () => {
  const edges = [edge('e1', 'box', 'out-dante', 'mixer', 'in-xlr3', 'audio')];
  expect(feedingStageboxes(mixer, devices, edges).map((d) => d.id)).toEqual(['box']);
});

test('a stagebox that reaches the mixer through an ethernet switch is also a feeding stagebox', () => {
  const edges = [
    edge('e1', 'box', 'out-dante', 'sw', 'p1', 'data'),
    edge('e2', 'sw', 'p2', 'mixer', 'in-xlr3', 'data'),
  ];
  expect(feedingStageboxes(mixer, devices, edges).map((d) => d.id)).toEqual(['box']);
});

test('a stagebox cabled to a channel of the mixer counts as feeding it', () => {
  const edges = [edge('e1', 'box', 'out-dante', 'ch3', 'in', 'audio')];
  expect(feedingStageboxes(mixer, devices, edges).map((d) => d.id)).toEqual(['box']);
});

test('a stagebox feeding a different mixer is not claimed by this one', () => {
  const other = { ...mixer, id: 'mixer2', sound_list_id: 'list2' };
  const edges = [edge('e1', 'box', 'out-dante', 'mixer2', 'in-xlr3', 'audio')];
  expect(feedingStageboxes(mixer, [...devices, other], edges)).toEqual([]);
});

test('the mixer input choices list the mixer inputs and the reaching stagebox inputs', () => {
  const edges = [edge('e1', 'box', 'out-dante', 'sw', 'p1', 'data'), edge('e2', 'sw', 'p2', 'mixer', 'in-xlr3', 'data')];
  const labels = mixerInputChoices(devices[3], devices, edges).map((c) => c.label);
  expect(labels).toContain('XLR3 in 1');
  expect(labels).toContain('XLR3 in 16');
  expect(labels).toContain('XLR3 in 1 (Stagebox)');
  expect(labels).toContain('XLR3 in 32 (Stagebox)');
  expect(labels.some((l) => l.includes('legacy'))).toBe(false);
});

test('a port label falls back to its connector, never the raw generated id alone', () => {
  expect(portLabelOf(mixer, 'out-xlr3')).toBe('XLR3 out');
  expect(portLabelOf(mixer, 'missing')).toBe('missing');
});

test('the channel flow shows the upstream feed and the inspector cable it was connected with', () => {
  const edges = [
    edge('feed1', 'box', 'out-dante', 'sw', 'p1', 'data'),
    edge('feed2', 'sw', 'p2', 'ch2', 'in', 'data'),
    edge('direct', 'ch2', 'out', 'box', 'in-xlr3', 'audio'),
  ];
  const tree = channelFlowTree(devices[3], [], edges, devices, 'Ch 2');
  expect(tree).toHaveLength(1);
  const labels = (nodes) => nodes.flatMap((n) => [n.label, ...labels(n.children || [])]);
  const all = labels(tree);
  expect(all).toContain('Stagebox');
  expect(all).toContain('Switch');
  expect(all).toContain('Ch 2');
});

test('a multi-channel input port is offered as one socket per physical input', () => {
  const options = socketOptions(stagebox, 'in');
  expect(options[0]).toEqual({ label: 'XLR3 in 1', value: 'in-xlr3#1' });
  expect(options).toHaveLength(32);
  expect(splitSocket('in-xlr3#5')).toEqual({ port: 'in-xlr3', socket: 5 });
  expect(splitSocket('in-xlr3')).toEqual({ port: 'in-xlr3', socket: null });
});

test('a socket shows in the port label of a cable', () => {
  expect(portLabelOf(stagebox, 'in-xlr3', 5)).toBe('XLR3 in 5');
});

test('an inspector cable into a stagebox socket is named by that socket', () => {
  const edges = [
    edge('mic', 'mic', 'out-xlr3', 'box', 'in-xlr3', 'audio', { attributes: { dst_socket: 5 } }),
  ];
  const mic = { id: 'mic', name: 'SM58', kind: 'other', ports: [{ id: 'out-xlr3', direction: 'out', connector: 'xlr3' }] };
  const lines = directConnections(stagebox, edges, [...devices, mic]);
  expect(lines.map((l) => l.text)).toEqual(['SM58 XLR3 out → Stagebox XLR3 in 5']);
});

test('the Patch column names a channel connected directly to the mixer, not "Not patched"', () => {
  const edges = [edge('direct', 'mixer', 'out-xlr3', 'ch2', 'in', 'audio')];
  const text = patchSummary(devices[3], edges, devices);
  expect(text).toBe('Desk → Ch 2');
  expect(text).not.toBe('');
});

test('a channel with no cables and no chain has an empty Patch column', () => {
  expect(patchSummary(devices[4], [], devices)).toBe('');
});
