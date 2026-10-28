import { elementCentre } from './cables';

// Projector throw, in cm and m. Throw ratio is distance divided by image width, so the
// image width at a distance is distance / throw ratio, and the horizontal throw angle is
// 2 * atan(1 / (2 * throw ratio)). Images are 16:9 unless an aspect ratio is given.
export const IMAGE_ASPECT = 16 / 9;
const FIXED_LENS_TOLERANCE = 0.05;

// Horizontal angle (degrees) a projector throws across at this throw ratio.
export function throwAngleDeg(throwRatio) {
  if (!throwRatio) return null;
  return (2 * Math.atan(1 / (2 * throwRatio)) * 180) / Math.PI;
}

// The throw ratios to draw: the shortest throw (widest angle, filled) and, for a zoom,
// the longest (outline). A fixed lens has only the one.
export function projectorEnds(throwMin, throwMax) {
  if (!throwMin) return [];
  const ends = [{ throwRatio: throwMin, filled: true }];
  if (throwMax && throwMax > throwMin) ends.push({ throwRatio: throwMax, filled: false });
  return ends;
}

// Distances (m) at which the projector fills a screen of the given size. The image is
// the largest 16:9 (or the given aspect) that fits the screen.
export function fillDistanceRangeM({ throwMin, throwMax, screenWidthCm, screenHeightCm, aspect = IMAGE_ASPECT }) {
  if (!throwMin || !screenWidthCm) return null;
  const limitCm = screenHeightCm ? Math.min(screenWidthCm, screenHeightCm * aspect) : screenWidthCm;
  const widthM = limitCm / 100;
  const high = throwMax || throwMin;
  return { minM: throwMin * widthM, maxM: high * widthM };
}

// 'close' or 'far' when the distance is outside the range, otherwise 'fits'.
// A fixed lens has a single distance, so it counts as fitting within a small tolerance.
export function fitStatus(distanceM, range) {
  if (!range || distanceM == null) return null;
  const fixed = range.maxM - range.minM < 1e-6;
  const low = range.minM * (fixed ? 1 - FIXED_LENS_TOLERANCE : 1);
  const high = range.maxM * (fixed ? 1 + FIXED_LENS_TOLERANCE : 1);
  if (distanceM < low) return 'close';
  if (distanceM > high) return 'far';
  return 'fits';
}

// Plan-view triangle from a projector to a screen face at one throw ratio. The screen is
// a line in plan (its height is vertical), so the face is its centre. The zone is the
// image width at that distance, centred on the face.
export function projectionGeometry({ apex, screen, throwRatio }) {
  const t = (screen.rotationDeg * Math.PI) / 180;
  const u = { x: Math.cos(t), y: Math.sin(t) };
  const distanceCm = Math.hypot(screen.x - apex.x, screen.y - apex.y);
  const imageWidthCm = distanceCm / throwRatio;
  const half = imageWidthCm / 2;
  const left = { x: screen.x - u.x * half, y: screen.y - u.y * half };
  const right = { x: screen.x + u.x * half, y: screen.y + u.y * half };
  return {
    imageWidthCm,
    distanceCm,
    cone: [
      [apex.x, apex.y],
      [left.x, left.y],
      [right.x, right.y],
    ],
    zone: [
      [left.x, left.y],
      [right.x, right.y],
    ],
  };
}

// The screen a projector aims at: the nearest one inside its throw angle (the widest throw,
// from the shortest throw ratio). A screen outside that angle is not its target, and a
// projector facing the wall has none.
export function targetScreen(projector, elements, throwMin) {
  if (!throwMin) return null;
  const [px, py] = elementCentre(projector);
  const theta = ((projector.rotation || 0) * Math.PI) / 180;
  const facing = { x: Math.sin(theta), y: -Math.cos(theta) };
  const cosHalf = Math.cos((throwAngleDeg(throwMin) * Math.PI) / 360);
  let best = null;
  let bestDistance = Infinity;
  for (const el of elements || []) {
    if (el.element_type !== 'screen') continue;
    const [sx, sy] = elementCentre(el);
    const dx = sx - px;
    const dy = sy - py;
    const distance = Math.hypot(dx, dy);
    if (distance === 0 || (dx * facing.x + dy * facing.y) / distance < cosHalf) continue;
    if (distance < bestDistance) {
      best = el;
      bestDistance = distance;
    }
  }
  return best;
}
