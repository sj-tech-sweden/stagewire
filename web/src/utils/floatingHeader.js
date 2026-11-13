// When does a table's header float, and where? Pure so it can be unit-tested without a browser.
//
// A table that is scrolled with the page loses its header off the top of the viewport. While the
// real header is hidden above the app header (`offsetTop`, the bottom edge of the layout header) and
// part of the table is still in view, a copy is shown fixed at that offset. When the table's bottom
// edge reaches the floating header it slides up with the table and is gone once the table has left.
//
// Rects are `{top, bottom, left, right, width, height}` in viewport pixels (getBoundingClientRect).

const EMPTY = Object.freeze({ visible: false, top: 0 });

export function floatingHeaderState({ table, header, offsetTop = 0, floatHeight = 0 }) {
  if (!table || !header) return EMPTY;
  // a table hidden by a tab, a collapsed section or v-show has no size
  if (!(table.width > 0) || !(table.height > 0)) return EMPTY;
  const headerAbove = header.bottom <= offsetTop + 1; // real header no longer visible
  const tableStillThere = table.bottom > offsetTop;
  if (!headerAbove || !tableStillThere) return EMPTY;
  // slides up with the table's bottom edge instead of covering rows below the table
  const top = Math.min(offsetTop, table.bottom - floatHeight);
  return { visible: true, top: Math.round(top) };
}

/** Bottom edge of the app's fixed header (or of a scrolling container), the line the header floats under. */
export function floatingOffset({ layoutHeaderBottom = 0, scrollParentTop = 0 }) {
  return Math.max(0, layoutHeaderBottom || 0, scrollParentTop || 0);
}
