import { computed, reactive, watch } from 'vue';

// Column order and visibility per table, kept in localStorage.
// `defaults` is the full column list (q-table column objects, each with a unique `name`).
export function useColumnPrefs(storageKey, defaults) {
  const names = defaults.map((c) => c.name);
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
  } catch {
    saved = null;
  }
  const order = (saved?.order || []).filter((n) => names.includes(n));
  for (const n of names) if (!order.includes(n)) order.push(n);
  // Columns marked defaultHidden start hidden, including ones added after the user saved a layout.
  const defaultHidden = defaults.filter((c) => c.defaultHidden).map((c) => c.name);
  const knownBefore = saved?.order || [];
  const newHidden = defaultHidden.filter((n) => !knownBefore.includes(n));
  const savedHidden = (saved?.hidden || []).filter((n) => names.includes(n));
  const state = reactive({
    order,
    hidden: [...new Set(saved ? [...savedHidden, ...newHidden] : defaultHidden)],
  });

  watch(
    state,
    (val) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify({ order: val.order, hidden: val.hidden }));
      } catch {
        /* storage unavailable */
      }
    },
    { deep: true },
  );

  const byName = Object.fromEntries(defaults.map((c) => [c.name, c]));
  const visible = computed(() =>
    state.order
      .filter((n) => !state.hidden.includes(n) || byName[n].locked)
      .map((n) => byName[n]),
  );
  const ordered = computed(() =>
    state.order.map((n) => ({
      name: n,
      label: byName[n].label,
      locked: !!byName[n].locked,
      shown: byName[n].locked || !state.hidden.includes(n),
    })),
  );

  function toggle(name) {
    if (byName[name]?.locked) return;
    const i = state.hidden.indexOf(name);
    if (i >= 0) state.hidden.splice(i, 1);
    else state.hidden.push(name);
  }

  function move(name, dir) {
    const i = state.order.indexOf(name);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= state.order.length) return;
    const tmp = state.order[i];
    state.order[i] = state.order[j];
    state.order[j] = tmp;
  }

  function reset() {
    state.order.splice(0, state.order.length, ...names);
    state.hidden.splice(0, state.hidden.length, ...defaultHidden);
  }

  return { visible, ordered, toggle, move, reset };
}
