import { test, expect } from '@playwright/test';
import {
  catalogQuery,
  deviceFromProduct,
  domainForCategory,
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
