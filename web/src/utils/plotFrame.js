// The frame around the workspace canvas: the venue, the stage inside it, the audience area and
// the venue's power outlets. It is the same frame the stage plot page draws, taken from the job
// (stage_*_cm, venue_*_cm, audience_polygon) so both views agree on scale and origin.
//
// Coordinates, as on the stage plot page:
//  - the venue's top-left corner is the origin (0, 0);
//  - the stage sits at (stage_x_cm, stage_y_cm) inside the venue;
//  - everything placed on the plot (elements, gear, outlets) is stored relative to the stage,
//    so its position on screen is (stageX + x, stageY + y);
//  - the audience polygon is stored in venue coordinates (no stage offset).

export const DEFAULT_STAGE = { w: 1000, h: 600 };

// A venue carries the same geometry fields as a job's snapshot, so its base-rig editor can reuse
// the exact same canvas frame a job would get once the venue is assigned.
export function frameFromVenue(venue) {
  const stageW = venue?.stage_width_cm > 0 ? venue.stage_width_cm : DEFAULT_STAGE.w;
  const stageH = venue?.stage_height_cm > 0 ? venue.stage_height_cm : DEFAULT_STAGE.h;
  const stageX = venue?.stage_x_cm || 0;
  const stageY = venue?.stage_y_cm || 0;
  const venueW = venue?.venue_width_cm || 0;
  const venueH = venue?.venue_height_cm || 0;
  const hasVenue = venueW > 0 && venueH > 0;
  return {
    stageX,
    stageY,
    stageW,
    stageH,
    venueW,
    venueH,
    hasVenue,
    width: hasVenue ? venueW : stageX + stageW,
    height: hasVenue ? venueH : stageY + stageH,
    audience: venue?.audience_polygon || [],
  };
}

export function frameFromJob(job) {
  const stageW = job?.stage_width_cm > 0 ? job.stage_width_cm : DEFAULT_STAGE.w;
  const stageH = job?.stage_height_cm > 0 ? job.stage_height_cm : DEFAULT_STAGE.h;
  const stageX = job?.stage_x_cm || 0;
  const stageY = job?.stage_y_cm || 0;
  const venueW = job?.venue_width_cm || 0;
  const venueH = job?.venue_height_cm || 0;
  const hasVenue = venueW > 0 && venueH > 0;
  return {
    stageX,
    stageY,
    stageW,
    stageH,
    venueW,
    venueH,
    hasVenue,
    // The area the canvas has to show: the venue if there is one, otherwise the stage.
    width: hasVenue ? venueW : stageX + stageW,
    height: hasVenue ? venueH : stageY + stageH,
    audience: job?.audience_polygon || [],
  };
}

// Zoom (pixels per cm) that makes the whole frame fit a host of the given size, with a margin.
export function fitZoom(frame, hostWidth, hostHeight, margin = 16) {
  const w = Math.max(1, frame.width);
  const h = Math.max(1, frame.height);
  const zoom = Math.min((hostWidth - margin) / w, (hostHeight - margin) / h);
  return Math.min(2, Math.max(0.05, Math.round(zoom * 1000) / 1000));
}

// Zoom that makes the frame as wide as the host. A tall venue then scrolls vertically instead of
// shrinking the gear until it cannot be read.
export const fitWidthZoom = (frame, hostWidth, margin = 16) =>
  Math.min(2, Math.max(0.05, Math.round(((hostWidth - margin) / Math.max(1, frame.width)) * 1000) / 1000));

// Where a screen position (relative to the canvas) lands in stage-relative cm, snapped to a grid.
export function stagePosition(px, py, zoom, frame, pan = { x: 0, y: 0 }, grid = 10) {
  const snap = (v) => Math.round(v / grid) * grid;
  return { x: snap((px - pan.x) / zoom - frame.stageX), y: snap((py - pan.y) / zoom - frame.stageY) };
}

// The spot in the middle of the stage where gear is placed when it is added to the plot.
export const stageCentre = (frame, boxCm = 96) => ({
  x: Math.round(frame.stageW / 2 - boxCm / 2),
  y: Math.round(frame.stageH / 2 - boxCm / 2),
});

// The coverage endpoint answers with a grid of '1'/'0' cells; this paints it as a translucent
// canvas that is then stretched over the whole venue (green = covered, red = not covered).
export function buildCoverageCanvas(data) {
  const canvas = document.createElement('canvas');
  canvas.width = data.cols;
  canvas.height = data.rows;
  const ctx = canvas.getContext('2d');
  const pixels = ctx.createImageData(data.cols, data.rows);
  data.grid.forEach((line, r) => {
    for (let c = 0; c < data.cols; c += 1) {
      const covered = line[c] === '1';
      const i = (r * data.cols + c) * 4;
      pixels.data[i] = covered ? 53 : 229;
      pixels.data[i + 1] = covered ? 168 : 57;
      pixels.data[i + 2] = covered ? 83 : 53;
      pixels.data[i + 3] = covered ? 90 : 70;
    }
  });
  ctx.putImageData(pixels, 0, 0);
  return canvas;
}
