import { historyStepLabel } from './workspace';
// Pure helpers for the undo / redo / version history UI (see components/HistoryControls.vue).
//
// The server keeps one linear history per job or venue: entries newest first, `undone` ones are the
// redo stack. `cursor` is the newest entry that is applied (0 = nothing applied).

// "Update channel — Vox": the step's label plus what it touched, for tooltips and the list.
// With a translator (`tr` = { has, t }) the step name is translated from its `action` key; without
// one the server's English label is used.
export const entryTitle = (entry, tr = null) => {
  if (!entry) return '';
  const name = tr ? historyStepLabel(entry, tr) : entry.label;
  return entry.summary ? `${name} — ${entry.summary}` : name;
};

// The step Undo would revert: the newest entry that is still applied.
export const nextUndo = (entries) => (entries || []).find((e) => !e.undone) || null;

// The step Redo would re-apply: the OLDEST undone entry (undo walked down from the newest).
export const nextRedo = (entries) => {
  const undone = (entries || []).filter((e) => e.undone);
  return undone.length ? undone.reduce((a, b) => (a.seq < b.seq ? a : b)) : null;
};

// 409 from undo / redo / restore with an object detail = rows changed outside the history.
export const isHistoryConflict = (err) => err?.response?.status === 409 && !!err.response.data?.detail?.conflicts;
// 409 with a plain string = nothing to undo / redo.
export const isNothingToDo = (err) => err?.response?.status === 409 && typeof err.response.data?.detail === 'string';

// Ctrl/Cmd+Z = undo, Ctrl/Cmd+Shift+Z or Ctrl+Y = redo. Typing in a field keeps the browser's own
// text undo, so fields, selects and contenteditable areas are left alone.
export function shortcutAction(event) {
  const mod = event.ctrlKey || event.metaKey;
  if (!mod || event.altKey) return null;
  const el = event.target;
  const tag = el?.tagName?.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || el?.isContentEditable) return null;
  const key = String(event.key || '').toLowerCase();
  if (key === 'z') return event.shiftKey ? 'redo' : 'undo';
  if (key === 'y' && !event.shiftKey) return 'redo';
  return null;
}

// "3 min ago" / "yesterday" in the user's language.
export function relativeTime(iso, now = Date.now(), locale = undefined) {
  if (!iso) return '';
  const diff = (new Date(iso).getTime() - now) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const abs = Math.abs(diff);
  if (abs < 45) return rtf.format(0, 'second');
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
  return rtf.format(Math.round(diff / 86400), 'day');
}

// Is this request a successful WRITE that changes the history of the scope (so the list is stale)?
export function isScopedWrite(config, status, kind, id) {
  const method = String(config?.method || 'get').toLowerCase();
  if (method === 'get' || method === 'head' || status >= 400) return false;
  const url = String(config?.url || '');
  if (url.includes('/history')) return false; // undo / redo / restore answer with the new state
  return url.includes(`/${kind === 'venue' ? 'venues' : 'jobs'}/${id}`);
}
