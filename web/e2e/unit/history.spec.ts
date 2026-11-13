import { test, expect } from '@playwright/test';
import {
  entryTitle,
  isHistoryConflict,
  isNothingToDo,
  isScopedWrite,
  nextRedo,
  nextUndo,
  relativeTime,
  shortcutAction,
} from '../../src/utils/history';

const entries = [
  { seq: 5, label: 'Update channel', summary: 'Vox', undone: true },
  { seq: 4, label: 'Create channel', summary: '', undone: true },
  { seq: 3, label: 'Delete device', summary: 'Box +1', undone: false },
  { seq: 2, label: 'Create channel list', summary: 'FOH', undone: false },
];

test('the next undo is the newest applied entry and the next redo the oldest undone one', () => {
  expect(nextUndo(entries)?.seq).toBe(3);
  expect(nextRedo(entries)?.seq).toBe(4);
  expect(nextUndo([])).toBeNull();
  expect(nextRedo(entries.filter((e) => !e.undone))).toBeNull();
  expect(entryTitle(entries[0])).toBe('Update channel — Vox');
  expect(entryTitle(entries[1])).toBe('Create channel');
  expect(entryTitle(null)).toBe('');
});

test('undo / redo shortcuts ignore typing in fields and need a modifier', () => {
  const key = (init: object, tag = 'div') => ({ ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, key: '', target: { tagName: tag }, ...init });
  expect(shortcutAction(key({ ctrlKey: true, key: 'z' }))).toBe('undo');
  expect(shortcutAction(key({ metaKey: true, key: 'Z' }))).toBe('undo');
  expect(shortcutAction(key({ ctrlKey: true, shiftKey: true, key: 'z' }))).toBe('redo');
  expect(shortcutAction(key({ ctrlKey: true, key: 'y' }))).toBe('redo');
  expect(shortcutAction(key({ key: 'z' }))).toBeNull();
  expect(shortcutAction(key({ ctrlKey: true, altKey: true, key: 'z' }))).toBeNull();
  expect(shortcutAction(key({ ctrlKey: true, key: 'z' }, 'INPUT'))).toBeNull();
  expect(shortcutAction(key({ ctrlKey: true, key: 'z' }, 'textarea'))).toBeNull();
  expect(shortcutAction({ ...key({ ctrlKey: true, key: 'z' }), target: { tagName: 'DIV', isContentEditable: true } })).toBeNull();
  expect(shortcutAction(key({ ctrlKey: true, key: 'c' }))).toBeNull();
});

test('409 answers: a conflict list versus nothing to undo', () => {
  const conflict = { response: { status: 409, data: { detail: { message: 'x', conflicts: ['graph_devices Vox'] } } } };
  const nothing = { response: { status: 409, data: { detail: 'Nothing to undo' } } };
  expect(isHistoryConflict(conflict)).toBe(true);
  expect(isNothingToDo(conflict)).toBe(false);
  expect(isHistoryConflict(nothing)).toBe(false);
  expect(isNothingToDo(nothing)).toBe(true);
  expect(isHistoryConflict({ response: { status: 500 } })).toBe(false);
});

test('only successful writes inside the open scope make the history list stale', () => {
  const id = 'abc';
  expect(isScopedWrite({ method: 'patch', url: `/jobs/${id}/channels/1` }, 200, 'job', id)).toBe(true);
  expect(isScopedWrite({ method: 'put', url: `/jobs/${id}/channel-lists/x/fx` }, 200, 'job', id)).toBe(true);
  expect(isScopedWrite({ method: 'get', url: `/jobs/${id}/graph` }, 200, 'job', id)).toBe(false);
  expect(isScopedWrite({ method: 'post', url: `/jobs/${id}/history/undo` }, 200, 'job', id)).toBe(false);
  expect(isScopedWrite({ method: 'post', url: `/jobs/${id}/channels` }, 422, 'job', id)).toBe(false);
  expect(isScopedWrite({ method: 'post', url: `/jobs/other/channels` }, 200, 'job', id)).toBe(false);
  expect(isScopedWrite({ method: 'patch', url: `/venues/${id}` }, 200, 'venue', id)).toBe(true);
  expect(isScopedWrite({ method: 'patch', url: `/venues/${id}` }, 200, 'job', id)).toBe(false);
});

test('relative times read naturally', () => {
  const now = Date.parse('2026-11-13T12:00:00Z');
  expect(relativeTime('2026-11-13T11:59:50Z', now, 'en')).toBe('now');
  expect(relativeTime('2026-11-13T11:55:00Z', now, 'en')).toBe('5 minutes ago');
  expect(relativeTime('2026-11-13T09:00:00Z', now, 'en')).toBe('3 hours ago');
  expect(relativeTime('2026-11-12T12:00:00Z', now, 'en')).toBe('yesterday');
  expect(relativeTime(null, now, 'en')).toBe('');
});

test('entryTitle translates the step name when given a translator and keeps the summary', async () => {
  const { entryTitle } = await import('../../src/utils/history');
  const dict: Record<string, string> = { 'history.actions.update_channel': 'Ändra kanal' };
  const tr = { has: (k: string) => k in dict, t: (k: string) => dict[k] };
  const entry = { action: 'update_channel', label: 'Update channel', summary: 'Vox' };
  expect(entryTitle(entry, tr)).toBe('Ändra kanal — Vox');
  expect(entryTitle(entry)).toBe('Update channel — Vox');
  expect(entryTitle(null, tr)).toBe('');
});
