import { test, expect } from '@playwright/test';
import {
  CHANNEL_COLUMNS,
  clampWidth,
  computeWidths,
  defaultLayout,
  loadLayout,
  normalizeLayout,
  resetLayout,
  saveLayout,
  storageKey,
  visibleColumns,
} from '../../src/utils/columnLayout';

const all = CHANNEL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.name); // the columns shown by default (the optional ones start hidden)
const byName = (name: string) => CHANNEL_COLUMNS.find((c) => c.name === name)!;

function memory() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

test('compact columns keep their default width and flexible ones share what is left by weight', () => {
  const { widths, total, overflow } = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1600, visible: all });
  expect([widths.number, widths.phantom_power, widths.stereo, widths.stand_type, widths.actions]).toEqual([64, 64, 72, 170, 96]);
  // the whole container is used, and Name (the heaviest) gets the most of the flexible space
  expect(total).toBeGreaterThanOrEqual(1590);
  expect(total).toBeLessThanOrEqual(1600);
  expect(overflow).toBe(false);
  expect(widths.name).toBeGreaterThan(widths.chain);
  expect(widths.chain).toBeGreaterThan(widths.device);
  expect(widths.device).toBeGreaterThan(widths.notes);
  expect(widths.name).toBeGreaterThanOrEqual(byName('name').min);
});

test('a short name fits by default on a normal desktop width', () => {
  const { widths } = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1280, visible: all });
  expect(widths.name).toBeGreaterThanOrEqual(150); // ~16 characters
});

test('minimums are respected; when they cannot fit the table scrolls instead of squeezing', () => {
  const narrow = computeWidths(CHANNEL_COLUMNS, { containerWidth: 700, visible: all });
  for (const c of CHANNEL_COLUMNS.filter((x) => x.defaultVisible)) expect(narrow.widths[c.name]).toBeGreaterThanOrEqual(c.min);
  expect(narrow.overflow).toBe(true);
  expect(narrow.total).toBeGreaterThan(700);
  // an unknown container (not measured yet) behaves like "no space": minimums
  expect(computeWidths(CHANNEL_COLUMNS, { visible: all }).widths.name).toBe(byName('name').min);
});

test('a column pushed to its minimum frees the rest for the others', () => {
  // just enough room that Notes (weight 1, min 120) would fall below its minimum by pure weight
  const { widths } = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1300, visible: all });
  for (const c of CHANNEL_COLUMNS.filter((x) => x.defaultVisible)) expect(widths[c.name]).toBeGreaterThanOrEqual(c.min);
  expect(Math.abs(Object.values(widths).reduce((a, b) => a + b, 0) - 1300)).toBeLessThan(8);
});

test('hidden columns take no space and required columns cannot be hidden', () => {
  const visible = ['input_type', 'notes']; // number / name / actions are required
  const names = visibleColumns(CHANNEL_COLUMNS, visible).map((c) => c.name);
  expect(names).toEqual(['number', 'name', 'input_type', 'notes', 'actions']);
  const { widths, total } = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1000, visible });
  expect(Object.keys(widths).sort()).toEqual([...names].sort());
  expect(Math.abs(total - 1000)).toBeLessThan(5);
  expect(computeWidths(CHANNEL_COLUMNS, { containerWidth: 1000, visible: [] }).names).toEqual(['number', 'name', 'actions']);
});

test('a dragged width wins (clamped to the minimum) and the others share the remainder', () => {
  const auto = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1600, visible: all });
  const wide = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1600, visible: all, overrides: { name: 400 } });
  expect(wide.widths.name).toBe(400);
  expect(wide.widths.notes).toBeLessThan(auto.widths.notes); // the rest got less
  expect(Math.abs(wide.total - 1600)).toBeLessThan(8);
  // below the minimum is clamped up; a compact column can be dragged too
  const small = computeWidths(CHANNEL_COLUMNS, { containerWidth: 1600, visible: all, overrides: { name: 10, stereo: 120 } });
  expect(small.widths.name).toBe(byName('name').min);
  expect(small.widths.stereo).toBe(120);
  expect(clampWidth(byName('number'), 10)).toBe(56);
  expect(clampWidth(byName('number'), 'abc')).toBeNull();
  expect(clampWidth(byName('number'), 99999)).toBe(1200);
});

test('the stored layout round-trips per user and survives bad data', () => {
  const storage = memory();
  expect(storageKey(7)).toBe('sw_channel_cols_v1_7');
  expect(loadLayout(7, CHANNEL_COLUMNS, storage)).toEqual(defaultLayout());
  const mine = { visible: ['input_type', 'notes', 'number', 'name', 'actions'], widths: { name: 300 } };
  expect(saveLayout(7, mine, CHANNEL_COLUMNS, storage)).toBe(true);
  expect(loadLayout(7, CHANNEL_COLUMNS, storage).widths).toEqual({ name: 300 });
  expect(loadLayout(7, CHANNEL_COLUMNS, storage).visible).not.toContain('device');
  expect(loadLayout(8, CHANNEL_COLUMNS, storage)).toEqual(defaultLayout()); // another user
  expect(resetLayout(7, CHANNEL_COLUMNS, storage)).toEqual(defaultLayout());
  expect(storage.getItem(storageKey(7))).toBeNull();
  // broken JSON, wrong version, junk everywhere
  storage.setItem(storageKey(9), '{not json');
  expect(loadLayout(9, CHANNEL_COLUMNS, storage)).toEqual(defaultLayout());
  expect(normalizeLayout({ v: 99, visible: ['notes'] })).toEqual(defaultLayout());
  const cleaned = normalizeLayout({
    v: 1,
    known: all,
    visible: ['notes', 'ghost', 42],
    widths: { name: 'wide', notes: 5, ghost: 300, chain: 333, stereo: NaN },
  });
  expect(cleaned.visible).toEqual(['number', 'name', 'notes', 'actions']); // required kept, ghost dropped
  expect(cleaned.widths).toEqual({ notes: 110, chain: 333 }); // bad numbers ignored, the rest clamped
});

test('a column added after the layout was saved takes its default visibility', () => {
  const older = CHANNEL_COLUMNS.filter((c) => c.name !== 'chain');
  const storage = memory();
  saveLayout(1, { visible: ['notes'], widths: {} }, older, storage); // saved before `chain` existed
  const loaded = loadLayout(1, CHANNEL_COLUMNS, storage);
  expect(loaded.visible).toContain('chain'); // appears by default
  expect(loaded.visible).not.toContain('device'); // an explicit choice is kept
});

test('blocked storage never throws', () => {
  const blocked = {
    getItem: () => {
      throw new Error('denied');
    },
    setItem: () => {
      throw new Error('denied');
    },
    removeItem: () => {
      throw new Error('denied');
    },
  };
  expect(loadLayout(1, CHANNEL_COLUMNS, blocked)).toEqual(defaultLayout());
  expect(saveLayout(1, defaultLayout(), CHANNEL_COLUMNS, blocked)).toBe(false);
  expect(resetLayout(1, CHANNEL_COLUMNS, blocked)).toEqual(defaultLayout());
});

// --- any table, not only the channel list ---------------------------------------------------------

import { withDefaults } from '../../src/utils/columnLayout';

test('a table only declares what matters: the rest of the layout meta has defaults', () => {
  expect(withDefaults({ name: 'notes' })).toMatchObject({ min: 80, width: 140, grow: 1, defaultVisible: true, required: false });
  // the row's buttons can never be hidden, whatever the table says
  expect(withDefaults({ name: 'actions' }).required).toBe(true);
  expect(withDefaults({ name: 'actions', required: false }).required).toBe(false);
  // explicit values win
  expect(withDefaults({ name: 'id', min: 40, width: 50, grow: 0 })).toMatchObject({ min: 40, width: 50, grow: 0 });
});

test('widths work for columns that declare little', () => {
  const columns = [{ name: 'name', min: 150, grow: 3, required: true }, { name: 'notes' }, { name: 'actions' }];
  const { widths, names } = computeWidths(columns, { containerWidth: 1000 });
  expect(names).toEqual(['name', 'notes', 'actions']);
  // actions has the default flexible weight here, so the rule "compact columns say grow: 0" is the table's to set
  expect(widths.name).toBeGreaterThanOrEqual(150);
  expect(Object.values(widths).reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(1000);
});

test('every table has its own storage key and the channel list keeps the one it always had', () => {
  expect(storageKey(7)).toBe('sw_channel_cols_v1_7'); // existing saved layouts keep working
  expect(storageKey(7, 'channels')).toBe('sw_channel_cols_v1_7');
  expect(storageKey(7, 'gear')).toBe('sw_table_gear_v1_7');
  expect(storageKey(null, 'lights')).toBe('sw_table_lights_v1_anon');
  expect(storageKey(7, 'gear')).not.toBe(storageKey(8, 'gear')); // per user
});

test('hiding a column in one table does not touch another', () => {
  const store = memory();
  const gear = [{ name: 'name', required: true }, { name: 'notes' }, { name: 'kind' }];
  const lights = [{ name: 'name', required: true }, { name: 'notes' }, { name: 'gel' }];
  saveLayout(1, { visible: ['name', 'kind'], widths: { name: 222 } }, gear, store, 'gear');
  // the other table, and the channel list, are untouched and start from their defaults
  expect(loadLayout(1, lights, store, 'lights')).toEqual({ visible: ['name', 'notes', 'gel'], widths: {} });
  expect(loadLayout(1, CHANNEL_COLUMNS, store)).toEqual(defaultLayout(CHANNEL_COLUMNS));
  // and the gear layout comes back as saved, with a column added later taking its default
  const grown = [...gear, { name: 'extra' }];
  expect(loadLayout(1, grown, store, 'gear')).toEqual({ visible: ['name', 'kind', 'extra'], widths: { name: 222 } });
  resetLayout(1, gear, store, 'gear');
  expect(loadLayout(1, gear, store, 'gear')).toEqual(defaultLayout(gear));
});


test('the instrument group, colour and performer columns are optional and start hidden', () => {
  const optional = CHANNEL_COLUMNS.filter((c) => !c.defaultVisible).map((c) => c.name);
  expect(optional).toEqual(['instrument_group', 'color_code', 'performer_name']);
  expect(visibleColumns(CHANNEL_COLUMNS, all).map((c) => c.name)).not.toContain('color_code');
  // chosen in the Columns menu, they show up (and take space) like any other column
  const names = visibleColumns(CHANNEL_COLUMNS, [...all, 'color_code']).map((c) => c.name);
  expect(names).toContain('color_code');
  // a layout saved before these columns existed has no opinion on them: they stay hidden
  const storage = memory();
  storage.setItem(storageKey(7), JSON.stringify({ v: 1, visible: all, widths: {} }));
  expect(loadLayout(7, CHANNEL_COLUMNS, storage).visible).not.toContain('performer_name');
});
