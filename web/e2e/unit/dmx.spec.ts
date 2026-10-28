import { test, expect } from '@playwright/test';
import { firstFreeAddress, occupiedChannels } from '../../src/utils/dmx';

const fixtures = [
  { id: 'a', universe: 1, dmx_address: 1, footprint: 16 },
  { id: 'b', universe: 1, dmx_address: 20, footprint: 4 },
  { id: 'c', universe: 2, dmx_address: 1, footprint: 8 },
];

test('the first free address leaves room for the whole footprint', () => {
  expect(firstFreeAddress(fixtures, 1, 3)).toBe(17);
  expect(firstFreeAddress(fixtures, 1, 4)).toBe(24);
  expect(firstFreeAddress(fixtures, 1, 5)).toBe(24);
  expect(firstFreeAddress(fixtures, 2, 1)).toBe(9);
  expect(firstFreeAddress(fixtures, 3, 16)).toBe(1);
});

test('the fixture being edited does not block its own address', () => {
  expect(firstFreeAddress(fixtures, 1, 16, 'a')).toBe(1);
  expect(occupiedChannels(fixtures, 1, 'a').has(1)).toBe(false);
  expect(occupiedChannels(fixtures, 1).get(20)?.id).toBe('b');
});

test('no free run returns null', () => {
  const full = [{ id: 'x', universe: 1, dmx_address: 1, footprint: 512 }];
  expect(firstFreeAddress(full, 1, 1)).toBeNull();
});
