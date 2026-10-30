import { test, expect } from '@playwright/test';
import { DEFAULT_STAGE, fitZoom, frameFromJob, stageCentre, stagePosition } from '../../src/utils/plotFrame';

test('the frame comes from the job and falls back to a default stage without a venue', () => {
  const frame = frameFromJob({ stage_width_cm: 800, stage_height_cm: 500, stage_x_cm: 200, stage_y_cm: 100 });
  expect(frame).toMatchObject({ stageW: 800, stageH: 500, hasVenue: false, width: 1000, height: 600 });
  expect(frameFromJob(null)).toMatchObject({ stageW: DEFAULT_STAGE.w, stageH: DEFAULT_STAGE.h, audience: [] });
});

test('with a venue the frame is the venue and the audience polygon is passed on', () => {
  const frame = frameFromJob({
    venue_width_cm: 3000,
    venue_height_cm: 2000,
    stage_width_cm: 800,
    audience_polygon: [[0, 0], [10, 0], [10, 10]],
  });
  expect(frame).toMatchObject({ hasVenue: true, width: 3000, height: 2000 });
  expect(frame.audience).toHaveLength(3);
});

test('fit picks the zoom that shows the whole frame and stays within the limits', () => {
  const frame = frameFromJob({ venue_width_cm: 3000, venue_height_cm: 2000 });
  expect(fitZoom(frame, 1016, 1016)).toBeCloseTo(0.333, 2);
  expect(fitZoom(frameFromJob({ venue_width_cm: 10, venue_height_cm: 10 }), 1000, 1000)).toBe(2);
  expect(fitZoom(frameFromJob({ venue_width_cm: 1e7, venue_height_cm: 1e7 }), 1000, 1000)).toBe(0.05);
});

test('a screen position becomes a stage-relative one and gear is placed in the middle of the stage', () => {
  const frame = frameFromJob({ stage_x_cm: 200, stage_y_cm: 100, stage_width_cm: 800, stage_height_cm: 400 });
  expect(stagePosition(500, 300, 0.5, frame)).toEqual({ x: 800, y: 500 });
  expect(stageCentre(frame, 100)).toEqual({ x: 350, y: 150 });
});
