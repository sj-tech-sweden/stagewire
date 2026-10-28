import { test, expect } from '@playwright/test';
import {
  fillDistanceRangeM,
  fitStatus,
  projectionGeometry,
  projectorEnds,
  targetScreen,
  throwAngleDeg,
} from '../../src/utils/projection';

test('the fill range comes from the throw ratio and the largest 16:9 image on the screen', () => {
  // 200 x 112.5 cm screen: the 16:9 image is 2.0 m wide.
  const range = fillDistanceRangeM({ throwMin: 1.2, throwMax: 2.4, screenWidthCm: 200, screenHeightCm: 112.5 });
  expect(range!.minM).toBeCloseTo(2.4, 6);
  expect(range!.maxM).toBeCloseTo(4.8, 6);
  // A taller screen is limited by its width.
  const wide = fillDistanceRangeM({ throwMin: 1, throwMax: 1, screenWidthCm: 200, screenHeightCm: 300 });
  expect(wide!.minM).toBeCloseTo(2, 6);
  expect(fillDistanceRangeM({ throwMin: null, throwMax: null, screenWidthCm: 200 })).toBeNull();
});

test('a distance is too close, too far, or fitting the zoom range', () => {
  const range = { minM: 2.4, maxM: 4.8 };
  expect(fitStatus(2.0, range)).toBe('close');
  expect(fitStatus(3.6, range)).toBe('fits');
  expect(fitStatus(5.0, range)).toBe('far');
  expect(fitStatus(null, range)).toBeNull();
});

test('a fixed lens fits within a small tolerance of its distance', () => {
  const range = { minM: 3, maxM: 3 };
  expect(fitStatus(3.1, range)).toBe('fits');
  expect(fitStatus(2.8, range)).toBe('close');
  expect(fitStatus(3.3, range)).toBe('far');
});

test('the image width on a screen comes from the throw distance and the throw ratio', () => {
  // Screen 400 cm away, throw ratio 1.2: the image is 400 / 1.2 = 333.3 cm wide.
  const screen = { x: 500, y: 0, rotationDeg: 0, widthCm: 200, heightCm: 112.5 };
  const geo = projectionGeometry({ apex: { x: 500, y: 400 }, screen, throwRatio: 1.2 });
  expect(geo.distanceCm).toBeCloseTo(400, 6);
  expect(geo.imageWidthCm).toBeCloseTo(333.33, 1);
  expect(geo.cone[0]).toEqual([500, 400]);
  expect(geo.zone[0][0]).toBeCloseTo(333.33, 1);
  expect(geo.zone[1][0]).toBeCloseTo(666.67, 1);
  // The image is on the screen face, which is the screen's centre line.
  expect(geo.zone[0][1]).toBeCloseTo(0, 6);
  // A screen turned to 180 degrees keeps the same zone, ends swapped.
  const turned = projectionGeometry({ apex: { x: 500, y: 400 }, screen: { ...screen, rotationDeg: 180 }, throwRatio: 1.2 });
  expect(turned.zone[0][0]).toBeCloseTo(666.67, 1);
  expect(turned.zone[1][0]).toBeCloseTo(333.33, 1);
});

test('the throw angle and the ends of a zoom come from the throw ratio range', () => {
  expect(throwAngleDeg(1.5)).toBeCloseTo(36.87, 2);
  expect(projectorEnds(1.2, 2.4)).toEqual([
    { throwRatio: 1.2, filled: true },
    { throwRatio: 2.4, filled: false },
  ]);
  expect(projectorEnds(1.5, null)).toEqual([{ throwRatio: 1.5, filled: true }]);
  expect(projectorEnds(null, 2)).toEqual([]);
});

test('a projector targets only a screen inside its throw angle', () => {
  const ahead = { id: 'screen', element_type: 'screen', position_x: 500, position_y: 0, width_cm: 200, height_cm: 112, rotation: 0 };
  const projector = { id: 'p', element_type: 'projector', position_x: 500, position_y: 600, width_cm: 40, height_cm: 25, rotation: 0 };
  expect(targetScreen(projector, [ahead], 1.2)).toBe(ahead);
  // Facing left, the screen is about 47 degrees off. A 1.5 throw is about 37 degrees wide.
  const wall = { ...projector, position_x: 1100, rotation: 270 };
  const off = { ...ahead, position_x: 550, position_y: 100 };
  expect(targetScreen(wall, [off], 1.5)).toBeNull();
  expect(targetScreen(projector, [ahead], null)).toBeNull();
  expect(targetScreen(projector, [{ ...ahead, position_y: 900 }], 1.2)).toBeNull();
});
