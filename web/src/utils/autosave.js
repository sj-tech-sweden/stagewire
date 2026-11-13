// Autosave without lost updates.
//
// Every editor field that persists on its own goes through one saver per resource (one for the DCAs,
// one for the FX engines, ...). A saver guarantees:
//  - requests for ONE resource never overlap: while one is in flight a newer edit only marks the saver
//    "again" and a single follow-up request runs after it, so the server never sees two writes race;
//  - the follow-up always sends the LATEST draft (`save()` reads the draft when it runs, not when the
//    edit happened), so a burst of keystrokes costs one request and the last value wins;
//  - `schedule()` debounces typing, `flush()` saves now (toggles, picker Done, leaving the tab);
//  - `dirty` is true from the first edit until the request that carried the latest edit succeeded, so
//    the caller can refuse to overwrite a field the user is typing in with a stale server summary.
//
// `save` returns false (or throws) on failure: the saver then reports `error` and stays dirty so a
// retry resends the draft.
export function createAutosaver(save, { delay = 600, onStatus = () => {} } = {}) {
  let timer = null;
  let running = null;
  let again = false;
  let edits = 0; // bumped by every schedule()/flush(): tells run() whether newer edits arrived
  const state = { dirty: false, saving: false, error: null, everSaved: false };

  const emit = () => onStatus({ ...state });

  async function run() {
    if (running) {
      again = true;
      return running;
    }
    running = (async () => {
      do {
        again = false;
        const seen = edits;
        state.saving = true;
        state.error = null;
        emit();
        let ok = false;
        try {
          ok = (await save()) !== false;
        } catch (err) {
          state.error = err;
        }
        state.saving = false;
        if (ok) {
          state.everSaved = true;
          // an edit that arrived during the request keeps the saver dirty and triggers the follow-up
          if (!again && edits === seen) state.dirty = false;
        } else {
          if (!state.error) state.error = new Error('save failed');
          again = false; // stop looping on a failing request; retry() or the next edit resends
        }
        emit();
      } while (again);
    })().finally(() => {
      running = null;
    });
    return running;
  }

  return {
    state,
    // the field changed: save after `delay` ms of quiet
    schedule() {
      edits += 1;
      state.dirty = true;
      clearTimeout(timer);
      timer = setTimeout(run, delay);
      emit();
    },
    // the field changed: save right now (still serialised behind a request in flight)
    flush() {
      edits += 1;
      state.dirty = true;
      clearTimeout(timer);
      return run();
    },
    // save only if something is pending (tab change, unmount)
    async settle() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
        if (state.dirty) await run();
      } else if (running) {
        await running;
      }
    },
    retry() {
      edits += 1;
      state.dirty = true;
      return run();
    },
    cancel() {
      clearTimeout(timer);
      timer = null;
    },
    // drop pending edits and the error (the caller re-read the server state)
    reset() {
      clearTimeout(timer);
      timer = null;
      edits += 1;
      state.dirty = false;
      state.error = null;
      emit();
    },
    get dirty() {
      return state.dirty;
    },
  };
}

// One status line for several savers: "saving" while any is in flight, "error" if any failed,
// else "saved" once something has been saved, else "idle".
export function combineStatus(states) {
  const list = Object.values(states);
  if (list.some((s) => s.saving)) return 'saving';
  if (list.some((s) => s.error)) return 'error';
  if (list.some((s) => s.dirty)) return 'saving';
  return list.some((s) => s.everSaved) ? 'saved' : 'idle';
}
