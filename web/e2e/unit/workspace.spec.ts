import { test, expect } from '@playwright/test';
import {
  catalogQuery,
  deviceFromProduct,
  boxFor,
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
