import { test, expect } from '@playwright/test';
import { legacyId } from '../../src/utils/graphLegacy';
import { applyGraphEvent, isRevisionConflict, threeWayMerge, upsertVersioned } from '../../src/utils/graph';

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

test('only a revision conflict is a conflict; other 409s are real errors to show', () => {
  const conflict = { response: { status: 409, data: { detail: { code: 'revision_conflict' } } } };
  const refusal = { response: { status: 409, data: { detail: 'Move the nodes fed from this one first' } } };
  expect(isRevisionConflict(conflict)).toBe(true);
  expect(isRevisionConflict(refusal)).toBe(false);
  expect(isRevisionConflict(new Error('offline'))).toBe(false);
});

test('edits to different attribute keys merge, the same key changed twice still conflicts', () => {
  const base = { revision: 1, attributes: { wireless_pack: '', wireless_frequency_mhz: null } };
  const theirs = { revision: 2, attributes: { wireless_pack: 'P10T', wireless_frequency_mhz: null } };
  const clean = threeWayMerge(base, { attributes: { wireless_frequency_mhz: 606.25 } }, theirs);
  expect(clean.conflicts).toEqual([]);
  expect(clean.merged).toEqual({ attributes: { wireless_frequency_mhz: 606.25 } });
  const clash = threeWayMerge(base, { attributes: { wireless_pack: 'P9R' } }, theirs);
  expect(clash.conflicts.map((c) => c.field)).toEqual(['attributes']);
});

test('a node is known by its legacy id, then the legacy id kept as an attribute, then its own id', () => {
  expect(legacyId({ id: 'n1', legacy_ref: 'device:abc' })).toBe('abc');
  expect(legacyId({ id: 'n2', legacy_ref: null, attributes: { legacy_id: 'old-input' } })).toBe('old-input');
  expect(legacyId({ id: 'n3', legacy_ref: null, attributes: {} })).toBe('n3');
});
