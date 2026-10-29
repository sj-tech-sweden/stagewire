import { test, expect } from '@playwright/test';
import { applyGraphEvent, placeUnplaced, threeWayMerge, upsertVersioned } from '../../src/utils/graph';

test('an older revision never overwrites a newer row', () => {
  const rows = [{ id: 'a', revision: 3, name: 'new' }];
  expect(upsertVersioned(rows, { id: 'a', revision: 2, name: 'old' })).toBe(rows);
  expect(upsertVersioned(rows, { id: 'a', revision: 4, name: 'newer' })[0].name).toBe('newer');
  expect(upsertVersioned(rows, { id: 'b', revision: 1 })).toHaveLength(2);
});

test('deleting a device drops the edges the server removed with it', () => {
  const state = {
    devices: [{ id: 'd1', revision: 1 }],
    edges: [
      { id: 'e1', revision: 1 },
      { id: 'e2', revision: 1 },
    ],
  };
  const next = applyGraphEvent(state, {
    type: 'graph.device.delete',
    payload: { id: 'd1', edge_ids: ['e1'] },
  });
  expect(next.devices).toEqual([]);
  expect(next.edges.map((e) => e.id)).toEqual(['e2']);
  expect(applyGraphEvent(state, { type: 'channel.update', payload: {} })).toBe(state);
});

test('edits to different fields merge, edits to the same field conflict', () => {
  const base = { name: 'Box', notes: '', canvas_x_cm: 10, revision: 1 };
  const theirs = { name: 'Box', notes: 'rack 2', canvas_x_cm: 10, revision: 2 };

  const clean = threeWayMerge(base, { canvas_x_cm: 50 }, theirs);
  expect(clean.conflicts).toEqual([]);
  expect(clean.merged).toEqual({ canvas_x_cm: 50 });

  const clash = threeWayMerge(base, { notes: 'rack 9', canvas_x_cm: 50 }, theirs);
  expect(clash.conflicts).toEqual([
    { field: 'notes', base: '', mine: 'rack 9', theirs: 'rack 2' },
  ]);
  expect(clash.merged).toEqual({ canvas_x_cm: 50 });

  const converged = threeWayMerge(base, { notes: 'rack 2' }, theirs);
  expect(converged.conflicts).toEqual([]);
});

test('switching to canvas places only unplaced devices and keeps existing positions', () => {
  const placed = placeUnplaced(
    [
      { id: 'a', canvas_x_cm: 5, canvas_y_cm: 6 },
      { id: 'b', canvas_x_cm: null, canvas_y_cm: null },
      { id: 'c' },
    ],
    { originX: 0, originY: 0, step: 100, perRow: 2 },
  );
  expect(placed[0]).toMatchObject({ canvas_x_cm: 5, canvas_y_cm: 6 });
  expect(placed[1]).toMatchObject({ canvas_x_cm: 0, canvas_y_cm: 0 });
  expect(placed[2]).toMatchObject({ canvas_x_cm: 100, canvas_y_cm: 0 });
});
