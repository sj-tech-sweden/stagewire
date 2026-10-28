import { test, expect } from '@playwright/test';
import {
  SENSOR_PRESETS,
  diagonalToMm,
  mmToDiagonal,
  parseAspect,
  parseLength,
  sensorDiagonalMm,
  sensorWidthFromDiagonal,
} from '../../src/utils/sensor';

test('lengths accept decimals, comma decimals, fractions and mixed numbers', () => {
  expect(parseLength('21.6')).toBe(21.6);
  expect(parseLength('21,6')).toBe(21.6);
  expect(parseLength('7/8')).toBe(0.875);
  expect(parseLength('1 1/2')).toBe(1.5);
  expect(parseLength('0')).toBeNull();
  expect(parseLength('1/0')).toBeNull();
  expect(parseLength('abc')).toBeNull();
});

test('aspect ratios accept a colon, a slash or an x', () => {
  expect(parseAspect('16:9')).toEqual({ w: 16, h: 9 });
  expect(parseAspect('4/3')).toEqual({ w: 4, h: 3 });
  expect(parseAspect('2.39x1')).toEqual({ w: 2.39, h: 1 });
  expect(parseAspect('16')).toBeNull();
  expect(parseAspect('0:9')).toBeNull();
});

test('inches convert to mm and back', () => {
  expect(diagonalToMm(1, 'in')).toBeCloseTo(25.4, 6);
  expect(diagonalToMm(12, 'mm')).toBe(12);
  expect(mmToDiagonal(25.4, 'in')).toBeCloseTo(1, 6);
});

test('the width follows from the diagonal and the aspect ratio', () => {
  // Full frame: 36 x 24 mm has a 43.27 mm diagonal and a 3:2 ratio.
  expect(sensorWidthFromDiagonal(43.27, { w: 3, h: 2 })).toBeCloseTo(36, 1);
  // A one-inch diagonal at 16:9.
  expect(sensorWidthFromDiagonal(diagonalToMm(1, 'in'), { w: 16, h: 9 })).toBeCloseTo(22.14, 1);
  expect(sensorWidthFromDiagonal(null, { w: 16, h: 9 })).toBeNull();
});

test('every preset matches its own aspect ratio and diagonal', () => {
  for (const p of SENSOR_PRESETS) {
    const aspect = parseAspect(p.aspect);
    expect(aspect, p.id).not.toBeNull();
    expect(p.width / p.height, p.id).toBeCloseTo(aspect.w / aspect.h, 1);
    expect(sensorWidthFromDiagonal(sensorDiagonalMm(p.width, p.height), aspect), p.id).toBeCloseTo(p.width, 0);
  }
});
