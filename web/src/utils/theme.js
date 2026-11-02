// Theme mode helpers. The app supports three modes:
//   - 'light': always light
//   - 'dark':  always dark
//   - 'auto':  follows the OS `prefers-color-scheme` setting (the default)
//
// The actual class toggling on <html>/<body> is done by Quasar's Dark plugin in
// the theme store; this module keeps the mode <-> isDark mapping and persistence
// as pure, testable logic so it does not depend on Quasar or the DOM.

export const THEME_MODES = ['light', 'dark', 'auto'];
export const DEFAULT_THEME_MODE = 'auto';
export const THEME_STORAGE_KEY = 'sw_theme_mode';

// Maps a mode plus the current OS preference to the boolean Quasar's Dark plugin
// expects. `auto` defers to `systemPrefersDark`; when the stored value is
// missing/unknown the app falls back to DEFAULT_THEME_MODE (auto).
export function resolveDark(mode, systemPrefersDark) {
  if (mode === 'light') return false;
  if (mode === 'dark') return true;
  // 'auto' (or anything unexpected) follows the system, defaulting to dark.
  return systemPrefersDark !== false;
}

export function isValidMode(value) {
  return THEME_MODES.includes(value);
}

// Reads the persisted mode, falling back to the default when nothing valid is
// stored. Guarded for non-browser (SSR/test) environments.
export function readStoredMode() {
  if (typeof localStorage === 'undefined') return DEFAULT_THEME_MODE;
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  return isValidMode(stored) ? stored : DEFAULT_THEME_MODE;
}

export function persistMode(mode) {
  if (typeof localStorage === 'undefined') return;
  if (!isValidMode(mode)) return;
  localStorage.setItem(THEME_STORAGE_KEY, mode);
}

// True when the OS reports a dark color scheme. Guarded for environments without
// matchMedia (older browsers, SSR, tests) — defaults to true so the app stays
// dark rather than flickering to light when the preference cannot be read.
export function getSystemPrefersDark() {
  if (typeof window === 'undefined' || !window.matchMedia) return true;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

// Icon name for each mode, used by the theme switcher in the header.
export function modeIcon(mode) {
  if (mode === 'light') return 'light_mode';
  if (mode === 'dark') return 'dark_mode';
  return 'brightness_auto';
}
