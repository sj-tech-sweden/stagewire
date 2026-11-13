<template>
  <div data-testid="console-patch-overview">
    <div
      v-if="pages > 1"
      class="row justify-end q-mb-xs"
    >
      <q-pagination
        v-model="page"
        :max="pages"
        :max-pages="5"
        boundary-numbers
        direction-links
        dense
        data-testid="console-patch-grid-pager"
      />
    </div>
    <!-- One tile per channel (or bus): number, name, where it is patched, stereo pairing, split badge.
         Tiles are buttons, so Enter / Space toggle the selection like a click does. -->
    <div
      class="patch-grid"
      role="group"
      :aria-label="ariaLabel"
      data-testid="console-patch-grid"
    >
      <button
        v-for="tile in shown"
        :key="tile.id"
        type="button"
        role="checkbox"
        :aria-checked="selectedSet.has(tile.id) ? 'true' : 'false'"
        :class="[
          'patch-tile',
          tile.patched ? 'is-patched' : 'is-unpatched',
          {
            on: selectedSet.has(tile.id),
            active: tile.id === activeId,
            'bridge-start': tile.bridge === 'start',
            'bridge-end': tile.bridge === 'end',
            orphaned: tile.orphaned,
          },
        ]"
        data-testid="console-patch-card"
        :data-patched="tile.patched ? 'true' : 'false'"
        :data-pair="tile.pair || ''"
        @click="(ev) => emit('tile', tile, ev)"
      >
        <span class="tile-top">
          <span class="tile-num">{{ prefixShort }}{{ tile.number }}</span>
          <span
            v-if="tile.pair"
            class="tile-pair"
            data-testid="console-tile-pair"
          >
            <q-icon
              name="link"
              size="12px"
            />{{ tile.pair }}
          </span>
          <span
            v-if="tile.modeBadge"
            class="tile-mode"
            data-testid="console-tile-mode"
          >{{ tile.modeBadge }}</span>
        </span>
        <span
          class="tile-name"
          data-testid="console-tile-name"
        >{{ tile.name || " " }}</span>
        <span
          class="tile-route"
          data-testid="console-tile-route"
        >{{ tile.routing }}</span>
        <q-icon
          v-if="tile.shortage"
          name="warning"
          color="warning"
          size="14px"
          class="tile-warn"
          data-testid="console-tile-shortage"
        />
        <q-badge
          v-if="tile.shared"
          floating
          color="warning"
          text-color="black"
          data-testid="console-tile-shared"
        >
          ×{{ tile.shared }}
        </q-badge>
        <q-icon
          v-if="selectedSet.has(tile.id)"
          name="check_circle"
          size="14px"
          class="tile-check"
        />
        <q-tooltip
          :delay="400"
          anchor="top middle"
          self="bottom middle"
        >
          {{ titleOf(tile) }}
        </q-tooltip>
      </button>
      <div
        v-if="!tiles.length"
        class="text-grey-6 q-pa-md"
      >
        {{ empty }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { pageOf, softTileTitle } from "@/utils/workspace";

// The soft patch's channel (or bus) overview as a grid of tiles. Presentational: it shows the tile
// models built by `softPatchTiles`, paged so 100+ stay cheap, and reports clicks; the panel owns the
// selection (click toggles, shift-click ranges over the visible tiles).
const props = defineProps({
  tiles: { type: Array, default: () => [] },
  selected: { type: Array, default: () => [] },
  // the tile whose socket the socket grid is showing
  activeId: { type: String, default: null },
  prefix: { type: String, default: "Ch" },
  ariaLabel: { type: String, default: "" },
  empty: { type: String, default: "" },
});
const emit = defineEmits(["tile"]);

const PAGE = 120;
const page = ref(1);
const selectedSet = computed(() => new Set(props.selected));
const pages = computed(() => Math.max(1, Math.ceil(props.tiles.length / PAGE)));
const shown = computed(() => pageOf(props.tiles, page.value, PAGE));
// "Ch" tiles show just the number; other prefixes (mixes) show it ("M3") so buses read differently
const prefixShort = computed(() => (props.prefix === "Ch" ? "" : `${props.prefix} `));
const titleOf = (tile) => softTileTitle(tile, props.prefix);
watch(pages, (n) => {
  if (page.value > n) page.value = n;
});
// the tile that became active (a socket tap, the dropdown) is brought onto the visible page
watch(
  () => props.activeId,
  (id) => {
    const i = props.tiles.findIndex((t) => t.id === id);
    if (i >= 0) page.value = Math.floor(i / PAGE) + 1;
  },
);
</script>

<style scoped>
.patch-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 4px;
  max-height: 38vh;
  overflow-y: auto;
  align-content: start;
}
.patch-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 1px;
  min-height: 62px;
  padding: 4px 6px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  font: inherit;
  line-height: 1.15;
  text-align: left;
  cursor: pointer;
}
.patch-tile:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 1px;
}
/* patched: green tint; unpatched: dashed amber outline so gaps stand out */
.patch-tile.is-patched {
  background: rgba(63, 135, 63, 0.22);
  border-color: rgba(63, 135, 63, 0.7);
}
.patch-tile.is-unpatched {
  border-style: dashed;
  border-color: rgba(255, 193, 7, 0.6);
  background: rgba(255, 193, 7, 0.06);
}
.patch-tile.orphaned {
  border-color: var(--q-negative);
}
/* selected: strong outline; active (its socket is in the grid): left accent bar */
.patch-tile.on {
  border-color: var(--q-primary);
  box-shadow: inset 0 0 0 2px var(--q-primary);
}
.patch-tile.active {
  border-left: 4px solid var(--q-primary);
}
/* the two legs of a stereo pair are drawn as one joined unit */
.patch-tile.bridge-start {
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
  margin-right: -5px;
  z-index: 1;
}
.patch-tile.bridge-end {
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
  border-left-style: solid;
}
.tile-top {
  display: flex;
  align-items: center;
  gap: 4px;
}
.tile-num {
  font-size: 1.05rem;
  font-weight: 700;
}
.tile-pair {
  display: inline-flex;
  align-items: center;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 0 3px;
  border-radius: 3px;
  background: var(--q-primary);
  color: #fff;
}
.tile-mode {
  margin-left: auto;
  font-size: 0.62rem;
  font-weight: 700;
  padding: 0 3px;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.4);
}
.tile-name,
.tile-route {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tile-name {
  font-size: 0.72rem;
}
.tile-route {
  font-size: 0.66rem;
  opacity: 0.8;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.tile-check {
  position: absolute;
  bottom: 2px;
  right: 3px;
  color: var(--q-primary);
}
.tile-warn {
  position: absolute;
  bottom: 2px;
  left: 4px;
}
</style>
