import { test, expect } from '@playwright/test';
import {
  THEME_MODES,
  DEFAULT_THEME_MODE,
  resolveDark,
  isValidMode,
  readStoredMode,
  getSystemPrefersDark,
  modeIcon,
} from '../../src/utils/theme';

test('THEME_MODES lists the three supported modes', () => {
  expect(THEME_MODES).toEqual(['light', 'dark', 'auto']);
});

test('isValidMode only accepts the three modes', () => {
  expect(isValidMode('light')).toBe(true);
  expect(isValidMode('dark')).toBe(true);
  expect(isValidMode('auto')).toBe(true);
  expect(isValidMode('blue')).toBe(false);
  expect(isValidMode('')).toBe(false);
  expect(isValidMode(null)).toBe(false);
  expect(isValidMode(undefined)).toBe(false);
});

test('resolveDark maps modes and auto to a boolean', () => {
  expect(resolveDark('light', true)).toBe(false);
  expect(resolveDark('light', false)).toBe(false);
  expect(resolveDark('dark', true)).toBe(true);
  expect(resolveDark('dark', false)).toBe(true);
  expect(resolveDark('auto', true)).toBe(true);
  expect(resolveDark('auto', false)).toBe(false);
});

test('resolveDark treats unknown modes as auto (follows the OS)', () => {
  expect(resolveDark('banana', false)).toBe(false);
  expect(resolveDark('banana', true)).toBe(true);
});

test('modeIcon returns the right material icon per mode', () => {
  expect(modeIcon('light')).toBe('light_mode');
  expect(modeIcon('dark')).toBe('dark_mode');
  expect(modeIcon('auto')).toBe('brightness_auto');
});

test('readStoredMode returns the stored valid mode, else the default', () => {
  const store: Record<string, string> = {};
  const original = globalThis.localStorage;
  // @ts-expect-error - minimal localStorage mock for the test
  globalThis.localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
  };
  try {
    expect(readStoredMode()).toBe(DEFAULT_THEME_MODE);
    store.sw_theme_mode = 'light';
    expect(readStoredMode()).toBe('light');
    store.sw_theme_mode = 'not-a-mode';
    expect(readStoredMode()).toBe(DEFAULT_THEME_MODE);
  } finally {
    // @ts-expect-error - restore original (possibly undefined in Node)
    globalThis.localStorage = original;
  }
});

test('getSystemPrefersDark follows matchMedia', () => {
  const original = globalThis.window;
  // @ts-expect-error - minimal window mock
  globalThis.window = {
    matchMedia: (q: string) => ({ matches: q.includes('dark') }),
  };
  try {
    expect(getSystemPrefersDark()).toBe(true);
  } finally {
    // @ts-expect-error - restore original (possibly undefined in Node)
    globalThis.window = original;
  }
});
