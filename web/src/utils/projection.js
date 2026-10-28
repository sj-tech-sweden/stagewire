// Projector throw distance against a screen, in metres. Throw ratio is distance divided
// by image width. Images are 16:9, and the largest 16:9 image that fits the screen sets
// the width.
export const IMAGE_ASPECT = 16 / 9;
const FIXED_LENS_TOLERANCE = 0.05;

// Distances (m) at which the projector can fill the screen, from its throw ratio range.
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

// Plan-view shape of a projector throwing onto a screen. The image sits on the screen's
// face that points at the projector. The cone runs from the projector to the image, and
// the coverage zone is the image width on that face, centred on it. Screen rotation follows
// the speaker convention: 0 faces up, width along x, depth along y.
export function projectionGeometry({ apex, screen, aspect = IMAGE_ASPECT }) {
  const t = (screen.rotationDeg * Math.PI) / 180;
  const u = { x: Math.cos(t), y: Math.sin(t) };
  const n = { x: Math.sin(t), y: -Math.cos(t) };
  const towards = n.x * (apex.x - screen.x) + n.y * (apex.y - screen.y);
  const side = towards < 0 ? -1 : 1;
  const depth = (screen.heightCm || 0) / 2;
  const face = { x: screen.x + side * n.x * depth, y: screen.y + side * n.y * depth };
  const limitCm = screen.heightCm ? Math.min(screen.widthCm, screen.heightCm * aspect) : screen.widthCm;
  const half = limitCm / 2;
  const left = { x: face.x - u.x * half, y: face.y - u.y * half };
  const right = { x: face.x + u.x * half, y: face.y + u.y * half };
  return {
    imageWidthCm: limitCm,
    distanceCm: Math.hypot(face.x - apex.x, face.y - apex.y),
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
