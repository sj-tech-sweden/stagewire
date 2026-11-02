import { coverageFocals, horizontalFovDeg, viewPolygon } from './camera';
import { elementCentre } from './cables';
import {
  fillDistanceRangeM,
  fitStatus,
  projectionGeometry,
  projectorEnds,
  targetScreen,
  throwAngleDeg,
  IMAGE_ASPECT,
} from './projection';

// Camera and projector view shapes for the workspace canvas, the same ones the stage plot page
// draws. Every shape is a polygon or a line in stage-relative cm ({ id, points: [[x, y], ...],
// closed, fill, stroke, strokeWidth, dash }); the canvas adds the stage offset and the zoom.
// `box` is the area views may reach (the venue, in stage-relative cm), so a cone is clipped at
// the walls.

const CAMERA = 'rgba(66, 165, 245, 0.6)';
const PROJECTOR = 'rgba(171, 71, 188, 0.6)';

// One cone per camera for the widest (filled) and, with a zoom lens, the longest focal length,
// plus a dotted cone limited to the lens's recommended distance when it has one. `specs` is the
// /camera-specs answer, keyed by element id.
export function cameraShapes({ elements, specs, mode = 'range', box }) {
  const shapes = [];
  for (const el of elements) {
    const spec = specs[el.id];
    if (!spec || !spec.sensor_width_mm || !spec.focal_min_mm) continue;
    const [cx, cy] = elementCentre(el);
    const ends = coverageFocals(spec.focal_min_mm, spec.focal_max_mm, { mode, chosenMm: spec.focal_mm });
    for (const end of ends) {
      shapes.push({
        id: `${el.id}-${end.filled ? 'wide' : 'tele'}`,
        points: viewPolygon({
          apex: { x: cx, y: cy },
          rotationDeg: el.rotation || 0,
          fovDeg: horizontalFovDeg(spec.sensor_width_mm, end.focalMm),
          maxDistanceCm: null,
          box,
        }),
        closed: true,
        fill: end.filled ? 'rgba(66, 165, 245, 0.16)' : 'transparent',
        stroke: CAMERA,
        strokeWidth: 1,
        dash: end.filled ? [] : [6, 4],
      });
    }
    if (spec.max_distance_m && ends.length) {
      shapes.push({
        id: `${el.id}-recommended`,
        points: viewPolygon({
          apex: { x: cx, y: cy },
          rotationDeg: el.rotation || 0,
          fovDeg: horizontalFovDeg(spec.sensor_width_mm, ends[0].focalMm),
          maxDistanceCm: spec.max_distance_m * 100,
          box,
        }),
        closed: true,
        fill: 'transparent',
        stroke: 'rgba(66, 165, 245, 0.8)',
        strokeWidth: 1,
        dash: [2, 3],
      });
    }
  }
  return shapes;
}

// A projector aimed at a screen draws the cone to the screen and the image zone on it (green
// when it fits, orange when too close or far); one facing the wall draws its throw angle.
// `deviceOf(element)` gives the linked device's throw ratios and image aspect.
export function projectorShapes({ elements, deviceOf, box }) {
  const shapes = [];
  for (const el of elements) {
    if (el.element_type !== 'projector') continue;
    const device = deviceOf(el);
    if (!device || !device.throw_ratio_min) continue;
    const [px, py] = elementCentre(el);
    const ends = projectorEnds(device.throw_ratio_min, device.throw_ratio_max);
    const screenEl = targetScreen(el, elements, device.throw_ratio_min);
    let status = null;
    let screen = null;
    if (screenEl) {
      const [sx, sy] = elementCentre(screenEl);
      screen = { x: sx, y: sy, rotationDeg: screenEl.rotation || 0 };
      const range = fillDistanceRangeM({
        throwMin: device.throw_ratio_min,
        throwMax: device.throw_ratio_max,
        screenWidthCm: screenEl.width_cm,
        screenHeightCm: screenEl.height_cm,
        aspect: device.image_aspect_ratio || IMAGE_ASPECT,
      });
      status = fitStatus(Math.hypot(sx - px, sy - py) / 100, range);
    }
    const zone = !screen ? PROJECTOR : status === 'fits' ? '#66BB6A' : status ? '#FFA726' : '#90A4AE';
    for (const end of ends) {
      const key = end.filled ? 'min' : 'max';
      const dash = end.filled ? [] : [6, 4];
      const fill = end.filled ? 'rgba(171, 71, 188, 0.14)' : 'transparent';
      if (screen) {
        const g = projectionGeometry({ apex: { x: px, y: py }, screen, throwRatio: end.throwRatio });
        shapes.push({ id: `${el.id}-cone-${key}`, points: g.cone, closed: true, fill, stroke: PROJECTOR, strokeWidth: 1, dash });
        shapes.push({ id: `${el.id}-zone-${key}`, points: g.zone, closed: false, fill: 'transparent', stroke: zone, strokeWidth: end.filled ? 3 : 2, dash });
      } else {
        shapes.push({
          id: `${el.id}-wall-${key}`,
          points: viewPolygon({
            apex: { x: px, y: py },
            rotationDeg: el.rotation || 0,
            fovDeg: throwAngleDeg(end.throwRatio),
            maxDistanceCm: null,
            box,
          }),
          closed: true,
          fill,
          stroke: PROJECTOR,
          strokeWidth: 1,
          dash,
        });
      }
    }
  }
  return shapes;
}
