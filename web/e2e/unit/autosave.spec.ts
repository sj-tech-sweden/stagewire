import { test, expect } from '@playwright/test';
import { combineStatus, createAutosaver } from '../../src/utils/autosave';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

test('typing is debounced into one save that carries the latest draft', async () => {
  let draft = '';
  const sent: string[] = [];
  const saver = createAutosaver(async () => {
    sent.push(draft);
    return true;
  }, { delay: 30 });
  for (const ch of ['a', 'ab', 'abc']) {
    draft = ch;
    saver.schedule();
    await sleep(5);
  }
  expect(sent).toEqual([]); // still within the quiet period
  await sleep(80);
  expect(sent).toEqual(['abc']);
  expect(saver.dirty).toBe(false);
});

test('requests never overlap: an edit during a save triggers exactly one follow-up with the newest draft', async () => {
  let draft = 'one';
  let inFlight = 0;
  let maxInFlight = 0;
  const sent: string[] = [];
  const saver = createAutosaver(async () => {
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    sent.push(draft);
    await sleep(40);
    inFlight -= 1;
    return true;
  }, { delay: 0 });
  const first = saver.flush();
  await sleep(10);
  draft = 'two';
  saver.flush();
  draft = 'three';
  saver.flush(); // coalesced with the previous follow-up
  await first;
  await sleep(120);
  expect(maxInFlight).toBe(1);
  expect(sent).toEqual(['one', 'three']);
  expect(saver.dirty).toBe(false);
});

test('a typed edit that lands while a save is running keeps the saver dirty until it is saved too', async () => {
  let draft = 'a';
  const sent: string[] = [];
  const saver = createAutosaver(async () => {
    sent.push(draft);
    await sleep(40);
    return true;
  }, { delay: 100 });
  const running = saver.flush();
  await sleep(10);
  draft = 'ab';
  saver.schedule(); // timer, not a flush
  await running;
  expect(saver.dirty).toBe(true); // the first save did not carry 'ab'
  await sleep(220);
  expect(sent).toEqual(['a', 'ab']);
  expect(saver.dirty).toBe(false);
});

test('a failed save keeps the draft dirty and reports the error; retry resends', async () => {
  let fail = true;
  let calls = 0;
  const states: string[] = [];
  const saver = createAutosaver(async () => {
    calls += 1;
    return !fail;
  }, { delay: 0, onStatus: (s) => states.push(s.error ? 'error' : s.saving ? 'saving' : 'idle') });
  await saver.flush();
  expect(saver.state.error).toBeTruthy();
  expect(saver.dirty).toBe(true);
  expect(calls).toBe(1); // no retry loop on its own
  fail = false;
  await saver.retry();
  expect(saver.state.error).toBeNull();
  expect(saver.dirty).toBe(false);
  expect(states).toContain('error');
});

test('settle writes a pending debounced edit at once; reset drops pending edits', async () => {
  let calls = 0;
  const saver = createAutosaver(async () => {
    calls += 1;
    return true;
  }, { delay: 10_000 });
  saver.schedule();
  await saver.settle();
  expect(calls).toBe(1);
  saver.schedule();
  saver.reset();
  await sleep(20);
  await saver.settle();
  expect(calls).toBe(1);
  expect(saver.dirty).toBe(false);
});

test('combineStatus summarises several savers', () => {
  const idle = { dirty: false, saving: false, error: null, everSaved: false };
  expect(combineStatus({ a: idle, b: idle })).toBe('idle');
  expect(combineStatus({ a: { ...idle, everSaved: true }, b: idle })).toBe('saved');
  expect(combineStatus({ a: { ...idle, saving: true }, b: idle })).toBe('saving');
  expect(combineStatus({ a: { ...idle, dirty: true }, b: idle })).toBe('saving');
  expect(combineStatus({ a: { ...idle, error: new Error('x') }, b: { ...idle, saving: false } })).toBe('error');
});
