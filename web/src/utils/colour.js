// Colours of a channel (`attributes.color_code`). New values are always '#rrggbb' hex (what the
// colour picker writes and what the instrument-group helpers expect); older rows may hold a plain
// colour name typed by hand ("red"), which is shown best-effort and never rewritten unless the user
// picks a colour.

// Twelve presets for a quick choice (the instrument-group palette plus neutrals).
export const PRESET_COLOURS = Object.freeze([
  '#e53935',
  '#fb8c00',
  '#f9a825',
  '#43a047',
  '#00897b',
  '#039be5',
  '#3949ab',
  '#8e24aa',
  '#d81b60',
  '#546e7a',
  '#8d6e63',
  '#212121',
]);

// The common CSS colour names a person is likely to have typed.
const NAMES = Object.freeze({
  red: '#ff0000',
  orange: '#ffa500',
  yellow: '#ffff00',
  green: '#008000',
  lime: '#00ff00',
  blue: '#0000ff',
  navy: '#000080',
  purple: '#800080',
  violet: '#ee82ee',
  pink: '#ffc0cb',
  magenta: '#ff00ff',
  cyan: '#00ffff',
  teal: '#008080',
  brown: '#a52a2a',
  white: '#ffffff',
  black: '#000000',
  grey: '#808080',
  gray: '#808080',
  silver: '#c0c0c0',
  gold: '#ffd700',
});

/** '#abc', 'abc', '#AABBCC' or 'aabbcc' -> '#aabbcc'; anything else -> null. */
export function normalizeHex(value) {
  const text = String(value ?? '').trim().toLowerCase();
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/.exec(text);
  if (!m) return null;
  const digits = m[1].length === 3 ? [...m[1]].map((c) => c + c).join('') : m[1];
  return `#${digits}`;
}

/** A hex for a stored colour: hex as is, a known name mapped, otherwise null (shown neutral). */
export function colourToHex(value) {
  const hex = normalizeHex(value);
  if (hex) return hex;
  return NAMES[String(value ?? '').trim().toLowerCase()] || null;
}

/** Black or white, whichever reads better on the colour (WCAG relative luminance). */
export function readableTextColour(hex) {
  const n = normalizeHex(hex);
  if (!n) return '#000000';
  const channel = (i) => {
    const v = parseInt(n.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
  return luminance > 0.4 ? '#000000' : '#ffffff';
}
