// Projector throw distance against a screen, in metres. Throw ratio is distance divided
// by image width. Images are 16:9, and the largest 16:9 image that fits the screen sets
// the width.
export const IMAGE_ASPECT = 16 / 9;
const FIXED_LENS_TOLERANCE = 0.05;

// Distances (m) at which the projector can fill the screen, from its throw ratio range.
export function fillDistanceRangeM({ throwMin, throwMax, screenWidthCm, screenHeightCm }) {
  if (!throwMin || !screenWidthCm) return null;
  const limitCm = screenHeightCm ? Math.min(screenWidthCm, screenHeightCm * IMAGE_ASPECT) : screenWidthCm;
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
