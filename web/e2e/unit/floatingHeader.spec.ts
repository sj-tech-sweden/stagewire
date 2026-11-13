import { test, expect } from '@playwright/test';
import { floatingHeaderState, floatingOffset } from '../../src/utils/floatingHeader';

const rect = (top: number, height: number, width = 800) => ({
  top,
  bottom: top + height,
  left: 20,
  right: 20 + width,
  width,
  height,
});
const OFFSET = 50; // the app header's bottom edge
const HEADER_H = 36;

// the table header is the first HEADER_H pixels of the table (as it is when the table is not scrolled
// inside its own box)
const state = (tableTop: number, tableHeight = 2000) =>
  floatingHeaderState({
    table: rect(tableTop, tableHeight),
    header: rect(tableTop, HEADER_H),
    offsetTop: OFFSET,
    floatHeight: HEADER_H,
  });

test('the header does not float while the real header is in view', () => {
  expect(state(300).visible).toBe(false); // table well below the top
  expect(state(OFFSET).visible).toBe(false); // header just under the app header
  expect(state(OFFSET - 10).visible).toBe(false); // header partly hidden: still the real one
});

test('it floats once the real header has scrolled up under the app header, at that offset', () => {
  expect(state(OFFSET - HEADER_H)).toEqual({ visible: true, top: OFFSET });
  expect(state(-500)).toEqual({ visible: true, top: OFFSET });
});

test('it slides up with the table end and is gone when the table has left', () => {
  // the last rows are scrolling away: the table bottom is closer than the header height
  const near = state(OFFSET - 2000 + HEADER_H - 10, 2000);
  expect(near.visible).toBe(true);
  expect(near.top).toBeLessThan(OFFSET);
  // table bottom exactly at / above the app header: nothing left to label
  expect(state(OFFSET - 2000, 2000).visible).toBe(false);
  expect(state(-5000, 2000).visible).toBe(false);
});

test('a hidden table (tab switch, collapsed section, v-show) never floats', () => {
  expect(floatingHeaderState({ table: rect(-300, 0), header: rect(-300, 0), offsetTop: OFFSET, floatHeight: HEADER_H }).visible).toBe(false);
  expect(floatingHeaderState({ table: rect(-300, 500, 0), header: rect(-300, 36, 0), offsetTop: OFFSET, floatHeight: HEADER_H }).visible).toBe(false);
  expect(floatingHeaderState({ table: null, header: null, offsetTop: OFFSET, floatHeight: HEADER_H }).visible).toBe(false);
});

test('the offset is the lowest of the app header and a scrolling container', () => {
  expect(floatingOffset({ layoutHeaderBottom: 50, scrollParentTop: 0 })).toBe(50);
  expect(floatingOffset({ layoutHeaderBottom: 50, scrollParentTop: 120 })).toBe(120);
  expect(floatingOffset({})).toBe(0);
});
