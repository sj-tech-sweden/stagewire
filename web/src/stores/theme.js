import { defineStore } from 'pinia';
import { Dark } from 'quasar';
import {
  THEME_MODES,
  DEFAULT_THEME_MODE,
  resolveDark,
  readStoredMode,
  persistMode,
  getSystemPrefersDark,
} from '@/utils/theme';

// One media-query listener is shared across the lifetime of the app; it only
// matters while mode is 'auto', but keeping it attached is cheap and keeps the
// isDark getter reactive to OS changes without re-binding on every toggle.
let mediaQuery = null;
let mediaHandler = null;

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: readStoredMode(),
    systemPrefersDark: getSystemPrefersDark(),
  }),
  getters: {
    // The three selectable modes, in display order.
    modes: () => THEME_MODES,
    // Whether Quasar's Dark plugin should be on, given the current mode and OS
    // preference. This is what drives the q-dark / body--dark classes.
    isDark: (state) => resolveDark(state.mode, state.systemPrefersDark),
    defaultMode: () => DEFAULT_THEME_MODE,
  },
  actions: {
    setMode(mode) {
      if (!THEME_MODES.includes(mode)) return;
      this.mode = mode;
      persistMode(mode);
      this.apply();
    },
    // Push the current isDark value into Quasar's Dark plugin.
    apply() {
      Dark.set(this.isDark);
    },
    // Called once from the theme boot file. Wires up the OS preference listener
    // (so 'auto' tracks the system live) and applies the initial mode.
    init() {
      if (typeof window !== 'undefined' && window.matchMedia) {
        mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaHandler = (event) => {
          this.systemPrefersDark = event.matches;
          this.apply();
        };
        if (typeof mediaQuery.addEventListener === 'function') {
          mediaQuery.addEventListener('change', mediaHandler);
        } else if (typeof mediaQuery.addListener === 'function') {
          // Safari < 14 fallback.
          mediaQuery.addListener(mediaHandler);
        }
      }
      this.apply();
    },
  },
});
