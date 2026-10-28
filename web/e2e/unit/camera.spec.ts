import { test, expect } from '@playwright/test';
import { coverageFocals, horizontalFovDeg, viewPolygon } from '../../src/utils/camera';

test('horizontal field of view follows the sensor and focal length', () => {
  expect(horizontalFovDeg(35, 55)).toBeCloseTo(35.3, 1);
  expect(horizontalFovDeg(35, 200)).toBeCloseTo(10.0, 1);
  expect(horizontalFovDeg(null, 50)).toBeNull();
});

test('the view ends at the venue wall when no maximum distance is set', () => {
  // Camera at the top of a 1000 x 800 cm room, facing down, 60 degree field of view.
  const box = { minX: 0, minY: 0, maxX: 1000, maxY: 800 };
  const poly = viewPolygon({ apex: { x: 500, y: 0 }, rotationDeg: 180, fovDeg: 60, box });
  const far = poly.slice(1);
  // The centre ray reaches the bottom wall.
  const centre = far[Math.floor(far.length / 2)];
  expect(centre[1]).toBeCloseTo(800, 0);
  // Every point stays inside the room.
  for (const [x, y] of poly) {
    expect(x).toBeGreaterThanOrEqual(-1e-6);
    expect(x).toBeLessThanOrEqual(1000 + 1e-6);
    expect(y).toBeLessThanOrEqual(800 + 1e-6);
  }
});

test('the view stops at the maximum distance when one is set', () => {
  const box = { minX: -5000, minY: -5000, maxX: 5000, maxY: 5000 };
  const poly = viewPolygon({ apex: { x: 0, y: 0 }, rotationDeg: 180, fovDeg: 30, maxDistanceCm: 300, box });
  for (const [x, y] of poly.slice(1)) {
    expect(Math.hypot(x, y)).toBeLessThanOrEqual(300 + 1e-6);
  }
  const centre = poly[Math.floor(poly.length / 2)];
  expect(centre[1]).toBeCloseTo(300, 0);
});

test('a zoom draws its widest and narrowest ends, a fixed lens only one', () => {
  expect(coverageFocals(2.84, 34.1)).toEqual([
    { focalMm: 2.84, filled: true },
    { focalMm: 34.1, filled: false },
  ]);
  expect(coverageFocals(50, null)).toEqual([{ focalMm: 50, filled: true }]);
  expect(coverageFocals(50, 50)).toEqual([{ focalMm: 50, filled: true }]);
  expect(coverageFocals(null, 50)).toEqual([]);
});

test('the chosen focal mode draws only the focal length in use', () => {
  expect(coverageFocals(2.84, 34.1, { mode: 'chosen', chosenMm: 12 })).toEqual([{ focalMm: 12, filled: true }]);
  expect(coverageFocals(2.84, 34.1, { mode: 'chosen' })).toEqual([{ focalMm: 2.84, filled: true }]);
});
