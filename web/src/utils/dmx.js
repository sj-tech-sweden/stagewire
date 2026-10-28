// DMX address maths for the fixture patch. A fixture uses `footprint` channels from its
// address on; a universe has 512 channels, numbered 1 to 512.

export const DMX_CHANNELS = 512;

export function footprintOf(fixture) {
  return Math.max(1, Number(fixture?.footprint) || 1);
}

// Channel -> the fixture that uses it, for one universe. `excludeId` leaves out the fixture
// being edited, so its own address is not reported as taken.
export function occupiedChannels(fixtures, universe, excludeId = null) {
  const taken = new Map();
  for (const f of fixtures || []) {
    if (f.id === excludeId || f.universe !== universe || !f.dmx_address) continue;
    const last = Math.min(DMX_CHANNELS, f.dmx_address + footprintOf(f) - 1);
    for (let c = f.dmx_address; c <= last; c += 1) {
      if (!taken.has(c)) taken.set(c, f);
    }
  }
  return taken;
}

// The lowest start address where `footprint` free channels run in a row, or null if none.
export function firstFreeAddress(fixtures, universe, footprint, excludeId = null) {
  const taken = occupiedChannels(fixtures, universe, excludeId);
  const width = Math.min(Math.max(1, Number(footprint) || 1), DMX_CHANNELS);
  for (let start = 1; start <= DMX_CHANNELS - width + 1; start += 1) {
    let free = true;
    for (let c = start; c < start + width; c += 1) {
      if (taken.has(c)) {
        free = false;
        break;
      }
    }
    if (free) return start;
  }
  return null;
}

// The fixtures a run of `footprint` channels from `start` would share channels with, and
// whether the run goes past channel 512. Used to warn before a fixture is saved.
export function clashesFor(fixtures, universe, start, footprint, excludeId = null) {
  if (!start) return { clashes: [], overflow: false };
  const width = Math.max(1, Number(footprint) || 1);
  const last = start + width - 1;
  const clashes = [];
  for (const f of fixtures || []) {
    if (f.id === excludeId || f.universe !== universe || !f.dmx_address) continue;
    const fLast = f.dmx_address + footprintOf(f) - 1;
    if (start <= fLast && f.dmx_address <= last) clashes.push(f);
  }
  return { clashes, overflow: last > DMX_CHANNELS };
}
