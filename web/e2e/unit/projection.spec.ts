import { test, expect } from '@playwright/test';
import { fillDistanceRangeM, fitStatus } from '../../src/utils/projection';

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
