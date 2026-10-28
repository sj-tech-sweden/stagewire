// Camera field of view and the area it covers, in stage coordinates (cm).
// Front convention matches speakers: rotation 0 faces up (-y).

export function horizontalFovDeg(sensorWidthMm, focalMm) {
  if (!sensorWidthMm || !focalMm) return null;
  return (2 * Math.atan(sensorWidthMm / (2 * focalMm)) * 180) / Math.PI;
}

// The focal length in use: the chosen one if it is inside the lens range, else the
// widest (shortest) focal length.
export function focalInUse(chosenMm, focalMinMm, focalMaxMm) {
  if (!focalMinMm) return null;
  const max = focalMaxMm || focalMinMm;
  if (chosenMm && chosenMm >= focalMinMm && chosenMm <= max) return chosenMm;
  return focalMinMm;
}

// The focal lengths to draw. 'range' gives the widest end of the lens and, for a zoom,
// the narrowest end too (filled is the widest, the other is an outline). 'chosen' gives
// only the focal length in use.
export function coverageFocals(focalMinMm, focalMaxMm, { mode = 'range', chosenMm = null } = {}) {
  if (!focalMinMm) return [];
  if (mode === 'chosen') return [{ focalMm: chosenMm || focalMinMm, filled: true }];
  const zoom = focalMaxMm && focalMaxMm > focalMinMm;
  const ends = [{ focalMm: focalMinMm, filled: true }];
  if (zoom) ends.push({ focalMm: focalMaxMm, filled: false });
  return ends;
}

// Direction the camera faces, as a vector.
export function facing(rotationDeg) {
  const t = (rotationDeg * Math.PI) / 180;
  return { x: Math.sin(t), y: -Math.cos(t) };
}

// Distance along a ray from `origin` in unit direction `dir` to leave the box.
function exitDistance(origin, dir, box) {
  let t = Infinity;
  if (dir.x > 1e-9) t = Math.min(t, (box.maxX - origin.x) / dir.x);
  if (dir.x < -1e-9) t = Math.min(t, (box.minX - origin.x) / dir.x);
  if (dir.y > 1e-9) t = Math.min(t, (box.maxY - origin.y) / dir.y);
  if (dir.y < -1e-9) t = Math.min(t, (box.minY - origin.y) / dir.y);
  return Math.max(0, t);
}

// Polygon of the area a camera sees: a fan of rays across its horizontal field of
// view, each ending at the venue wall or at the maximum distance, whichever is first.
export function viewPolygon({ apex, rotationDeg, fovDeg, maxDistanceCm, box, steps = 48 }) {
  const front = facing(rotationDeg);
  const base = Math.atan2(front.y, front.x);
  const half = ((fovDeg || 0) * Math.PI) / 360;
  const points = [[apex.x, apex.y]];
  for (let i = 0; i <= steps; i++) {
    const angle = base - half + (2 * half * i) / steps;
    const dir = { x: Math.cos(angle), y: Math.sin(angle) };
    let reach = exitDistance(apex, dir, box);
    if (maxDistanceCm) reach = Math.min(reach, maxDistanceCm);
    points.push([apex.x + dir.x * reach, apex.y + dir.y * reach]);
  }
  return points;
}
