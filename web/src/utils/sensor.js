// Standard camera sensor sizes, width and height in mm. The aspect ratio is the one
// the sensor is shot in.
export const SENSOR_PRESETS = [
  { id: '1/3', label: '1/3"', width: 4.8, height: 3.6, aspect: '4:3' },
  { id: '1/2.3', label: '1/2.3"', width: 6.17, height: 4.55, aspect: '4:3' },
  { id: '1/2', label: '1/2"', width: 6.4, height: 4.8, aspect: '4:3' },
  { id: '1/1.8', label: '1/1.8"', width: 7.18, height: 5.32, aspect: '4:3' },
  { id: '2/3', label: '2/3"', width: 8.8, height: 6.6, aspect: '4:3' },
  { id: '1', label: '1"', width: 13.2, height: 8.8, aspect: '3:2' },
  { id: '4/3', label: 'Four Thirds', width: 17.3, height: 13, aspect: '4:3' },
  { id: 'aps-c-sony', label: 'APS-C (Sony, Nikon)', width: 23.5, height: 15.6, aspect: '3:2' },
  { id: 'aps-c-canon', label: 'APS-C (Canon)', width: 22.3, height: 14.9, aspect: '3:2' },
  { id: 'super35', label: 'Super 35', width: 24.9, height: 18.7, aspect: '4:3' },
  { id: 'full-frame', label: 'Full frame', width: 36, height: 24, aspect: '3:2' },
  { id: 'medium-format', label: 'Medium format', width: 43.8, height: 32.9, aspect: '4:3' },
];

const MM_PER_INCH = 25.4;

export function findPreset(id) {
  return SENSOR_PRESETS.find((p) => p.id === id) || null;
}

// "16:9", "16/9" or "16x9" to { w, h }, or null.
export function parseAspect(text) {
  const m = String(text || '')
    .trim()
    .match(/^(\d+(?:[.,]\d+)?)\s*[:/x]\s*(\d+(?:[.,]\d+)?)$/i);
  if (!m) return null;
  const w = Number(m[1].replace(',', '.'));
  const h = Number(m[2].replace(',', '.'));
  return w > 0 && h > 0 ? { w, h } : null;
}

// "21.6", "21,6", "7/8" or "1 1/2" to a number, or null.
export function parseLength(text) {
  const s = String(text || '')
    .trim()
    .replace(',', '.');
  let value;
  let m = s.match(/^(\d+)\s+(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)$/);
  if (m) {
    value = Number(m[1]) + Number(m[2]) / Number(m[3]);
  } else if ((m = s.match(/^(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)$/))) {
    value = Number(m[1]) / Number(m[2]);
  } else if (/^\d+(\.\d+)?$/.test(s)) {
    value = Number(s);
  } else {
    return null;
  }
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function diagonalToMm(value, unit) {
  return unit === 'in' ? value * MM_PER_INCH : value;
}

export function mmToDiagonal(mm, unit) {
  return unit === 'in' ? mm / MM_PER_INCH : mm;
}

// Sensor width from its diagonal and aspect ratio: the diagonal is split in the ratio.
export function sensorWidthFromDiagonal(diagonalMm, aspect) {
  if (!diagonalMm || !aspect) return null;
  return (diagonalMm * aspect.w) / Math.hypot(aspect.w, aspect.h);
}

export function sensorDiagonalMm(widthMm, heightMm) {
  return Math.hypot(widthMm, heightMm);
}
