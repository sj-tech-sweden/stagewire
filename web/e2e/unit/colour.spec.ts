import { test, expect } from '@playwright/test';
import { PRESET_COLOURS, colourToHex, normalizeHex, readableTextColour } from '../../src/utils/colour';

test('normalizeHex accepts 3 and 6 digit hex with or without #, in any case, and nothing else', () => {
  expect(normalizeHex('#AABBCC')).toBe('#aabbcc');
  expect(normalizeHex('abc')).toBe('#aabbcc');
  expect(normalizeHex(' #0F0 ')).toBe('#00ff00');
  for (const bad of ['', null, undefined, 'red', '#12', '#12345', '#1234567', '#gggggg', 12345]) {
    expect(normalizeHex(bad as string)).toBeNull();
  }
});

test('colourToHex maps old colour names, keeps hex, and leaves unknown text unresolved', () => {
  expect(colourToHex('#E53935')).toBe('#e53935');
  expect(colourToHex('Red')).toBe('#ff0000');
  expect(colourToHex(' grey ')).toBe('#808080');
  expect(colourToHex('gray')).toBe('#808080');
  expect(colourToHex('chartreuse-ish')).toBeNull(); // shown as a neutral swatch, text in the tooltip
  expect(colourToHex(null)).toBeNull();
});

test('the swatch text is black on light colours and white on dark ones', () => {
  expect(readableTextColour('#ffffff')).toBe('#000000');
  expect(readableTextColour('#f9a825')).toBe('#000000'); // amber
  expect(readableTextColour('#000000')).toBe('#ffffff');
  expect(readableTextColour('#3949ab')).toBe('#ffffff'); // indigo
  expect(readableTextColour('nonsense')).toBe('#000000');
});

test('the presets are twelve distinct valid hex colours', () => {
  expect(PRESET_COLOURS).toHaveLength(12);
  expect(new Set(PRESET_COLOURS).size).toBe(12);
  for (const c of PRESET_COLOURS) expect(normalizeHex(c)).toBe(c);
});
