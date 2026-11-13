<template>
  <div data-testid="strip-picker">
    <!-- Host row: a collapsed chip summary instead of a giant dropdown. -->
    <div class="row items-center q-gutter-xs">
      <span class="text-caption text-grey-6">{{ label }}</span>
      <q-chip
        v-for="item in summary.shown"
        :key="item.id"
        dense
        square
        removable
        :class="`kind-${item.kind}`"
        data-testid="strip-picker-chip"
        @remove="remove(item.id)"
      >
        {{ item.number }} {{ item.label }}
      </q-chip>
      <q-chip
        v-if="summary.more"
        dense
        square
        clickable
        color="grey-7"
        text-color="white"
        data-testid="strip-picker-more"
        @click="open"
      >
        {{ t("console.pickerMore", { n: summary.more }) }}
      </q-chip>
      <q-btn
        flat
        dense
        no-caps
        icon="playlist_add_check"
        :label="t('console.pickerChoose')"
        data-testid="strip-picker-open"
        @click="open"
      />
    </div>

    <q-dialog
      v-model="opened"
      :maximized="$q.screen.lt.sm"
    >
      <q-card
        style="min-width: 320px; max-width: 720px; width: 100%"
        class="column no-wrap"
        data-testid="strip-picker-dialog"
      >
        <q-card-section class="q-pb-none text-h6">
          {{ title || t("console.pickerTitle") }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model="query"
            dense
            outlined
            clearable
            :label="t('common.search')"
            data-testid="strip-picker-search"
          >
            <template #prepend>
              <q-icon name="search" />
            </template>
          </q-input>
          <div
            v-if="kindList.length > 1"
            class="row q-gutter-xs"
          >
            <q-chip
              v-for="k in kindList"
              :key="k"
              dense
              clickable
              :outline="!kindsOn.includes(k)"
              color="primary"
              text-color="white"
              :icon="stripKindIcon(k)"
              :data-testid="`strip-picker-kind-${k}`"
              @click="toggleKind(k)"
            >
              {{ t(`console.stripKind.${k}`) }}
            </q-chip>
          </div>
          <q-select
            v-if="groups.length"
            v-model="group"
            :options="groups"
            dense
            outlined
            clearable
            :label="t('console.pickerGroup')"
            data-testid="strip-picker-group"
          />
          <div class="row q-col-gutter-sm items-center">
            <div class="col">
              <q-input
                v-model="rangeText"
                dense
                outlined
                :label="t('console.pickerRange')"
                :hint="t('console.pickerRangeHint')"
                data-testid="strip-picker-range"
                @keyup.enter="applyRange(true)"
              />
            </div>
            <div class="col-auto">
              <q-btn
                dense
                no-caps
                outline
                icon="add"
                :label="t('console.pickerAdd')"
                :disable="!rangeText"
                data-testid="strip-picker-range-apply"
                @click="applyRange(true)"
              />
            </div>
            <div class="col-auto">
              <q-btn
                dense
                no-caps
                flat
                icon="remove"
                :label="t('console.pickerRemove')"
                :disable="!rangeText"
                @click="applyRange(false)"
              />
            </div>
          </div>
          <div class="row q-gutter-xs">
            <q-btn
              dense
              flat
              no-caps
              icon="done_all"
              :label="t('console.pickerAllVisible')"
              data-testid="strip-picker-all"
              @click="sel = selectIds(sel, visibleIds)"
            />
            <q-btn
              dense
              flat
              no-caps
              icon="remove_done"
              :label="t('console.pickerNoneVisible')"
              @click="sel = deselectIds(sel, visibleIds)"
            />
            <q-btn
              dense
              flat
              no-caps
              icon="flip"
              :label="t('console.pickerInvert')"
              @click="sel = invertIds(sel, visibleIds)"
            />
            <q-btn
              dense
              flat
              no-caps
              color="negative"
              icon="clear_all"
              :label="t('console.pickerClear')"
              @click="sel = []"
            />
          </div>
        </q-card-section>

        <div class="row items-center q-px-md q-pb-xs">
          <q-btn-toggle
            v-model="view"
            dense
            no-caps
            unelevated
            toggle-color="primary"
            :options="[
              { icon: 'grid_view', value: 'grid', attrs: { 'aria-label': t('console.pickerViewGrid') } },
              { icon: 'view_list', value: 'list', attrs: { 'aria-label': t('console.pickerViewList') } },
            ]"
            data-testid="strip-picker-view"
            @update:model-value="saveView"
          />
          <q-space />
          <q-pagination
            v-if="view === 'grid' && gridPages > 1"
            v-model="gridPage"
            :max="gridPages"
            :max-pages="5"
            boundary-numbers
            direction-links
            dense
            data-testid="strip-picker-pager"
          />
        </div>

        <!-- Grid: many compact tiles at once (number big, label small), paged so 200+ stay cheap. -->
        <div
          v-if="view === 'grid'"
          class="strip-grid col"
          role="group"
          :aria-label="title || t('console.pickerTitle')"
          data-testid="strip-picker-grid"
        >
          <button
            v-for="item in gridItems"
            :key="item.id"
            type="button"
            role="checkbox"
            :aria-checked="selected.has(item.id) ? 'true' : 'false'"
            :class="['strip-tile', `kind-${item.kind}`, { on: selected.has(item.id) }]"
            :title="`${item.number} ${item.label}`.trim()"
            data-testid="strip-picker-tile"
            @click="(ev) => click(item, ev)"
            @keydown.space.prevent="(ev) => click(item, ev)"
          >
            <q-icon
              v-if="item.kind !== 'input'"
              :name="stripKindIcon(item.kind)"
              size="12px"
              class="tile-kind"
            />
            <span class="tile-number">{{ item.number }}</span>
            <span class="tile-label">{{ item.label || "\u00a0" }}</span>
            <q-icon
              v-if="selected.has(item.id)"
              name="check_circle"
              size="14px"
              class="tile-check"
            />
          </button>
          <div
            v-if="!visible.length"
            class="text-grey-6 q-pa-md"
          >
            {{ t("console.pickerNone") }}
          </div>
        </div>

        <!-- Virtual list: only the visible rows are rendered, so 200 strips cost the same as 20. -->
        <q-virtual-scroll
          v-else
          :items="visible"
          :virtual-scroll-item-size="40"
          class="col"
          style="max-height: 40vh; min-height: 160px"
          separator
          data-testid="strip-picker-list"
        >
          <template #default="{ item }">
            <q-item
              :key="item.id"
              dense
              clickable
              data-testid="strip-picker-row"
              @click="(ev) => click(item, ev)"
            >
              <q-item-section side>
                <q-checkbox
                  :model-value="selected.has(item.id)"
                  dense
                  tabindex="-1"
                  @click.stop.prevent="(ev) => click(item, ev)"
                />
              </q-item-section>
              <q-item-section avatar>
                <q-icon
                  :name="stripKindIcon(item.kind)"
                  size="18px"
                />
              </q-item-section>
              <q-item-section>
                <q-item-label>
                  <b>{{ item.number }}</b> {{ item.label }}<span v-if="item.stereo"> · ST</span>
                </q-item-label>
                <q-item-label
                  v-if="item.caption"
                  caption
                >
                  {{ item.caption }}
                </q-item-label>
              </q-item-section>
            </q-item>
          </template>
          <template #after>
            <div
              v-if="!visible.length"
              class="text-grey-6 q-pa-md"
            >
              {{ t("console.pickerNone") }}
            </div>
          </template>
        </q-virtual-scroll>

        <q-card-actions align="between">
          <span
            class="text-caption"
            data-testid="strip-picker-count"
          >{{ t("console.pickerSelected", { n: sel.length, total: items.length }) }}</span>
          <div>
            <q-btn
              v-close-popup
              flat
              no-caps
              :label="t('common.cancel')"
            />
            <q-btn
              color="primary"
              no-caps
              :label="t('console.pickerDone')"
              data-testid="strip-picker-done"
              @click="done"
            />
          </div>
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
// A picker for many strips at once (DCA members, FX sends, the channels of an auto patch). The host
// shows a few chips and "+N more"; the dialog has search, kind and instrument-group filters, a
// number-range box ("1-16, 20, 24-32"), select all / none / invert on the visible rows, shift-click
// ranges and a virtual list, so it stays usable at 100+ strips and on a phone. The selection is a
// local draft until Done.
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import {
  deselectIds,
  filterStripItems,
  idsInRanges,
  invertIds,
  pageOf,
  rangeBetween,
  selectIds,
  stripKindIcon,
  summariseSelection,
} from "@/utils/workspace";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // [{id, kind: input|fx|mix|fxsend|dca, label, number, stereo?, group?, caption?}]
  items: { type: Array, default: () => [] },
  label: { type: String, default: "" },
  title: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);
const { t } = useI18n();
const $q = useQuasar();

// Grid (default) or list, remembered per browser; storage may be blocked, so every access is guarded.
const VIEW_KEY = "stagewire.stripPickerView";
function loadView() {
  try {
    return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid";
  } catch {
    return "grid";
  }
}
function saveView(v) {
  try {
    localStorage.setItem(VIEW_KEY, v);
  } catch {
    /* private mode / blocked storage: the choice just is not remembered */
  }
}
const view = ref(loadView());
const GRID_PAGE = 120;
const gridPage = ref(1);

const opened = ref(false);
const sel = ref([]);
const query = ref("");
const kindsOn = ref([]);
const group = ref(null);
const rangeText = ref("");
let lastClicked = null;

const selected = computed(() => new Set(sel.value));
const summary = computed(() => summariseSelection(props.items, props.modelValue));
const kindList = computed(() => [...new Set(props.items.map((i) => i.kind))]);
const groups = computed(() => [...new Set(props.items.map((i) => i.group).filter((g) => g && g !== "other"))]);
const visible = computed(() => filterStripItems(props.items, { query: query.value || "", kinds: kindsOn.value, group: group.value || "" }));
const visibleIds = computed(() => visible.value.map((i) => i.id));
const gridPages = computed(() => Math.max(1, Math.ceil(visible.value.length / GRID_PAGE)));
const gridItems = computed(() => pageOf(visible.value, gridPage.value, GRID_PAGE));
// a filter that shrinks the list must not leave the grid on a page that no longer exists
watch(gridPages, (n) => {
  if (gridPage.value > n) gridPage.value = n;
});

function open() {
  sel.value = [...props.modelValue];
  query.value = "";
  kindsOn.value = [];
  group.value = null;
  rangeText.value = "";
  lastClicked = null;
  gridPage.value = 1;
  opened.value = true;
}
function toggleKind(k) {
  kindsOn.value = kindsOn.value.includes(k) ? kindsOn.value.filter((x) => x !== k) : [...kindsOn.value, k];
}
function remove(id) {
  emit("update:modelValue", props.modelValue.filter((x) => x !== id));
}
// Click toggles one row; shift-click applies the clicked row's new state to everything between it
// and the previous click (in the visible order).
function click(item, ev) {
  const on = !selected.value.has(item.id);
  const ids = ev?.shiftKey && lastClicked ? rangeBetween(visibleIds.value, lastClicked, item.id) : [item.id];
  sel.value = on ? selectIds(sel.value, ids) : deselectIds(sel.value, ids);
  lastClicked = item.id;
}
function applyRange(on) {
  const ids = idsInRanges(props.items, rangeText.value);
  sel.value = on ? selectIds(sel.value, ids) : deselectIds(sel.value, ids);
}
function done() {
  // keep the items' own order (channel order) rather than click order
  const order = new Map(props.items.map((i, n) => [i.id, n]));
  emit("update:modelValue", [...sel.value].sort((a, b) => (order.get(a) ?? 1e9) - (order.get(b) ?? 1e9)));
  opened.value = false;
}
</script>

<style scoped>
.strip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(68px, 1fr));
  gap: 6px;
  padding: 4px 16px 8px;
  overflow-y: auto;
  max-height: 40vh;
  min-height: 160px;
  align-content: start;
}
.strip-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 52px;
  padding: 4px 2px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
  font: inherit;
  line-height: 1.1;
}
.strip-tile:focus-visible { outline: 2px solid var(--q-primary); outline-offset: 1px; }
.strip-tile.on { border-color: var(--q-primary); box-shadow: inset 0 0 0 2px var(--q-primary); }
.tile-number { font-size: 1.05rem; font-weight: 700; }
.tile-label { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.68rem; opacity: 0.8; }
.tile-kind { position: absolute; top: 2px; left: 3px; opacity: 0.7; }
.tile-check { position: absolute; top: 2px; right: 3px; color: var(--q-primary); }
.kind-input { background: rgba(63, 135, 63, 0.25); }
.kind-mix { background: rgba(38, 166, 154, 0.25); }
.kind-dca { background: rgba(255, 193, 7, 0.22); }
.kind-fx { background: rgba(156, 39, 176, 0.28); }
.kind-fxsend { background: rgba(233, 30, 99, 0.25); }
</style>
