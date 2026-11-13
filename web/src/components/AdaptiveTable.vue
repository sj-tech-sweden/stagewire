<template>
  <!-- Phones (and anything not wide enough for a real table) keep the plain q-table: the column
       chooser, resizing and the floating header are desktop / tablet features. -->
  <q-table
    v-if="!desktop"
    v-bind="$attrs"
    :columns="plainColumns"
  >
    <template
      v-for="name in forwardedSlots"
      #[name]="slotProps"
    >
      <slot
        :name="name"
        v-bind="slotProps || {}"
      />
    </template>
  </q-table>
  <div
    v-else
    ref="rootEl"
    class="adaptive-table"
  >
    <!-- Which columns show, and how wide they are, is the user's choice (kept per browser, user and
         table); by default the widths are computed so text columns fit and compact ones stay compact. -->
    <div
      v-if="chooser"
      class="row items-center justify-end q-mb-xs"
    >
      <slot name="toolbar" />
      <q-btn
        flat
        dense
        no-caps
        icon="view_column"
        :label="t('workspace.columns')"
        :data-testid="`${prefix}-columns`"
      >
        <q-menu>
          <q-list
            dense
            style="min-width: 220px"
          >
            <q-item-label
              header
              class="text-caption"
            >
              {{ t("workspace.columnsHint") }}
            </q-item-label>
            <q-item
              v-for="c in described"
              :key="c.name"
              tag="label"
              :disable="c.required"
            >
              <q-item-section side>
                <q-checkbox
                  :model-value="isVisible(c)"
                  :disable="c.required"
                  dense
                  :data-testid="`${prefix}-col-toggle-${c.name}`"
                  @update:model-value="(v) => toggleColumn(c.name, v)"
                />
              </q-item-section>
              <q-item-section>{{ c.chooserLabel || c.label || t("workspace.columnActions") }}</q-item-section>
            </q-item>
            <q-separator />
            <q-item
              v-close-popup
              clickable
              :data-testid="`${prefix}-columns-reset`"
              @click="resetColumns"
            >
              <q-item-section avatar>
                <q-icon name="restart_alt" />
              </q-item-section>
              <q-item-section>{{ t("workspace.columnsReset") }}</q-item-section>
            </q-item>
          </q-list>
        </q-menu>
      </q-btn>
    </div>
    <div ref="wrapEl">
      <q-table
        v-bind="$attrs"
        :columns="qColumns"
        :table-style="tableStyle"
        class="adaptive-table-q"
      >
        <template #header-cell="hp">
          <q-th
            :props="hp"
            class="adaptive-th"
          >
            <span class="adaptive-th-label">{{ hp.col.label }}</span>
            <span
              v-if="resizable(hp.col.name)"
              class="col-resize-handle"
              role="separator"
              aria-orientation="vertical"
              tabindex="0"
              :aria-label="t('workspace.resizeColumn', { name: hp.col.label })"
              :data-testid="`${prefix}-col-resize-${hp.col.name}`"
              @pointerdown.stop.prevent="(e) => startResize(e, hp.col.name)"
              @click.stop
              @dblclick.stop.prevent="autoWidth(hp.col.name)"
              @keydown="(e) => resizeKey(e, hp.col.name)"
            />
          </q-th>
        </template>
        <template
          v-for="name in forwardedSlots"
          #[name]="slotProps"
        >
          <slot
            :name="name"
            v-bind="slotProps || {}"
          />
        </template>
      </q-table>
    </div>

    <!-- A copy of the header, fixed under the app header while the table's own header has scrolled
         out of view. It is teleported to <body> so no overflow / transform of an ancestor clips or
         offsets it, and it is only ever "pointer-active" on the header itself. -->
    <Teleport to="body">
      <div
        v-if="floating.visible"
        class="adaptive-floating"
        :style="floatingStyle"
        :data-testid="`${prefix}-floating-header`"
      >
        <div class="q-table__container q-table--dense q-table--flat">
          <div class="q-table__middle adaptive-floating-middle">
            <table
              class="q-table"
              :style="floatingTableStyle"
            >
              <thead>
                <tr>
                  <th
                    v-for="c in qColumns"
                    :key="c.name"
                    :class="`text-${c.align || 'left'} adaptive-th`"
                    :style="c.headerStyle"
                  >
                    <span class="adaptive-th-label">{{ c.label }}</span>
                    <span
                      v-if="resizable(c.name)"
                      class="col-resize-handle"
                      role="separator"
                      aria-orientation="vertical"
                      tabindex="0"
                      :aria-label="t('workspace.resizeColumn', { name: c.label })"
                      :data-testid="`${prefix}-fcol-resize-${c.name}`"
                      @pointerdown.stop.prevent="(e) => startResize(e, c.name)"
                      @dblclick.stop.prevent="autoWidth(c.name)"
                      @keydown="(e) => resizeKey(e, c.name)"
                    />
                  </th>
                </tr>
              </thead>
            </table>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, useSlots, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { useAuthStore } from "@/stores/auth";
import {
  clampWidth,
  computeWidths,
  loadLayout,
  minWidthOf,
  resetLayout,
  saveLayout,
  withAllDefaults,
} from "@/utils/columnLayout";
import { floatingHeaderState, floatingOffset } from "@/utils/floatingHeader";

// A q-table with a layout of its own: widths computed so the header and the cells agree
// (`table-layout: fixed`), a Columns chooser, drag / keyboard resizing, per browser + user + table
// persistence, and a floating copy of the header while the table is scrolled past. Everything else
// (rows, row-key, virtual scroll, classes, data-testids, listeners) is passed straight to the q-table,
// and every q-table slot is forwarded.
defineOptions({ inheritAttrs: false });

const props = defineProps({
  // storage key part and default test-id prefix: `sw_table_<tableId>_v1_<userId>`
  tableId: { type: String, required: true },
  // q-table columns plus layout meta: {min, width, grow (0 = compact), required, defaultVisible, resizable}
  columns: { type: Array, required: true },
  // test-id prefix of the chooser / handles (`<prefix>-columns`, `<prefix>-col-resize-<name>`)
  testPrefix: { type: String, default: "" },
  chooser: { type: Boolean, default: true },
  floatingHeader: { type: Boolean, default: true },
});

const { t } = useI18n();
const $q = useQuasar();
const slots = useSlots();
const auth = useAuthStore();
const prefix = computed(() => props.testPrefix || props.tableId);
const desktop = computed(() => !$q.screen.lt.sm);

// header-cell is ours (it carries the resize handle); everything else the parent gave is forwarded
const forwardedSlots = computed(() => Object.keys(slots).filter((n) => n !== "header-cell" && n !== "toolbar"));

const described = computed(() => withAllDefaults(props.columns));
const plainColumns = computed(() => props.columns.map((c) => ({ ...c })));

// --- the user's layout ------------------------------------------------------------------------------
const layout = ref(loadLayout(auth.user?.id, props.columns, null, props.tableId));
// columns that existed when the layout was loaded: a column that appears later (a table whose set of
// columns depends on a setting) takes its default visibility until the user decides
const known = ref(new Set(props.columns.map((c) => c.name)));
const isVisible = (c) => c.required || (known.value.has(c.name) ? layout.value.visible.includes(c.name) : c.defaultVisible);
const visibleNames = computed(() => described.value.filter(isVisible).map((c) => c.name));
function persist() {
  const names = props.columns.map((c) => c.name);
  known.value = new Set(names);
  saveLayout(auth.user?.id, { ...layout.value, visible: visibleNames.value }, props.columns, null, props.tableId);
}
function toggleColumn(name, on) {
  const column = described.value.find((c) => c.name === name);
  if (!column || column.required) return;
  const visible = new Set(visibleNames.value);
  if (on) visible.add(name);
  else visible.delete(name);
  layout.value = { ...layout.value, visible: described.value.filter((c) => c.required || visible.has(c.name)).map((c) => c.name) };
  persist();
}
function resetColumns() {
  layout.value = resetLayout(auth.user?.id, props.columns, null, props.tableId);
  known.value = new Set(props.columns.map((c) => c.name));
}

// --- widths -----------------------------------------------------------------------------------------
const rootEl = ref(null);
const wrapEl = ref(null);
const containerWidth = ref(0);
let resizeObserver = null;
let resizeTimer = null;
function measure() {
  if (wrapEl.value) containerWidth.value = Math.floor(wrapEl.value.clientWidth);
}
const sizing = computed(() =>
  computeWidths(props.columns, {
    containerWidth: containerWidth.value,
    visible: visibleNames.value,
    overrides: layout.value.widths,
  }),
);
const tableStyle = computed(() => ({ tableLayout: "fixed", width: `${sizing.value.total}px`, minWidth: "100%" }));
const qColumns = computed(() =>
  sizing.value.names.map((name) => {
    const own = props.columns.find((c) => c.name === name);
    const px = `width:${sizing.value.widths[name]}px;min-width:${sizing.value.widths[name]}px;max-width:${sizing.value.widths[name]}px`;
    return { field: () => "", align: "left", ...own, style: [own.style, px].filter(Boolean).join(";"), headerStyle: px };
  }),
);

// --- resizing ---------------------------------------------------------------------------------------
const resizable = (name) => {
  const c = described.value.find((x) => x.name === name);
  return !!c && c.resizable !== false && name !== "actions";
};
const currentWidth = (name) => sizing.value.widths[name];
function setWidth(name, px, save) {
  const column = described.value.find((c) => c.name === name);
  const clamped = column ? clampWidth(column, px) : null;
  if (clamped == null) return;
  layout.value = { ...layout.value, widths: { ...layout.value.widths, [name]: clamped } };
  if (save) persist();
}
// Pointer events cover mouse, touch and pen; the width follows the pointer live and is stored when it
// is released. Double click goes back to the automatic width, and the arrow keys nudge a focused handle.
function startResize(event, name) {
  const handle = event.currentTarget;
  const startX = event.clientX;
  const startWidth = currentWidth(name);
  handle.setPointerCapture?.(event.pointerId);
  const move = (e) => setWidth(name, startWidth + (e.clientX - startX), false);
  const end = (e) => {
    handle.removeEventListener("pointermove", move);
    handle.removeEventListener("pointerup", end);
    handle.removeEventListener("pointercancel", end);
    try {
      handle.releasePointerCapture?.(e.pointerId);
    } catch {
      /* already released */
    }
    setWidth(name, startWidth + (e.clientX - startX), true);
  };
  handle.addEventListener("pointermove", move);
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
}
function resizeKey(event, name) {
  const step = event.shiftKey ? 40 : 10;
  const delta = event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0;
  if (!delta) return;
  event.preventDefault();
  event.stopPropagation();
  const column = described.value.find((c) => c.name === name);
  setWidth(name, Math.max(currentWidth(name) + delta, minWidthOf(column)), true);
}
function autoWidth(name) {
  const widths = { ...layout.value.widths };
  delete widths[name];
  layout.value = { ...layout.value, widths };
  persist();
}

// --- the floating header ----------------------------------------------------------------------------
const floating = ref({ visible: false, top: 0, left: 0, width: 0, height: 0, scrollLeft: 0 });
let frame = 0;
function scrollParentTop(el) {
  // a scrolling container that is not the window (a q-page inside a scroll area) starts below its own top
  for (let node = el?.parentElement; node && node !== document.body; node = node.parentElement) {
    if (node.classList?.contains("q-table__middle")) continue;
    const overflowY = getComputedStyle(node).overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight + 1) {
      return node.getBoundingClientRect().top;
    }
  }
  return 0;
}
function updateFloating() {
  frame = 0;
  const root = rootEl.value;
  if (!props.floatingHeader || !root) {
    if (floating.value.visible) floating.value = { ...floating.value, visible: false };
    return;
  }
  const thead = root.querySelector("thead");
  const middle = root.querySelector(".q-table__middle");
  const container = root.querySelector(".q-table__container") || middle;
  if (!thead || !container) return;
  const header = thead.getBoundingClientRect();
  const table = container.getBoundingClientRect();
  const appHeader = document.querySelector(".q-header");
  const offsetTop = floatingOffset({
    layoutHeaderBottom: appHeader ? appHeader.getBoundingClientRect().bottom : 0,
    scrollParentTop: scrollParentTop(root),
  });
  const next = floatingHeaderState({ table, header, offsetTop, floatHeight: header.height });
  floating.value = {
    visible: next.visible,
    top: next.top,
    left: table.left,
    width: table.width,
    height: header.height,
    scrollLeft: middle ? middle.scrollLeft : 0,
  };
}
function scheduleFloating() {
  if (frame) return;
  frame = requestAnimationFrame(updateFloating);
}
const floatingStyle = computed(() => ({
  top: `${floating.value.top}px`,
  left: `${floating.value.left}px`,
  width: `${floating.value.width}px`,
  height: `${floating.value.height}px`,
}));
const floatingTableStyle = computed(() => ({
  ...tableStyle.value,
  width: `${sizing.value.total}px`,
  minWidth: "100%",
  marginLeft: `${-floating.value.scrollLeft}px`,
}));

function watchContainer(el) {
  resizeObserver?.disconnect();
  if (!el) return;
  measure();
  if (typeof ResizeObserver === "undefined") return;
  resizeObserver = new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(measure, 60);
    scheduleFloating(); // a tab switch / collapse changes the size: the floating copy follows
  });
  resizeObserver.observe(el);
  if (rootEl.value) resizeObserver.observe(rootEl.value);
}
// the wrapper only exists in the desktop layout (phones get the plain table), so follow the ref
watch(wrapEl, watchContainer, { flush: "post" });
watch([sizing, () => props.columns.length], () => nextTick(scheduleFloating));

onMounted(() => {
  // scroll does not bubble, but it is seen in the capture phase on window: this catches the page,
  // any scrolling container and the table's own scroller (horizontal scroll keeps the copy in step)
  window.addEventListener("scroll", scheduleFloating, { passive: true, capture: true });
  window.addEventListener("resize", scheduleFloating, { passive: true });
  scheduleFloating();
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", scheduleFloating, { capture: true });
  window.removeEventListener("resize", scheduleFloating);
  if (frame) cancelAnimationFrame(frame);
  resizeObserver?.disconnect();
  clearTimeout(resizeTimer);
});
</script>

<style scoped>
/* fixed layout: cells never push their column wider; their inputs fill what they are given */
.adaptive-table-q :deep(td) {
  overflow: hidden;
  text-overflow: ellipsis;
}
.adaptive-th {
  position: relative;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.adaptive-th-label {
  padding-right: 8px;
}
.col-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  touch-action: none;
  user-select: none;
  z-index: 2;
}
.col-resize-handle::after {
  content: "";
  position: absolute;
  top: 25%;
  bottom: 25%;
  right: 4px;
  width: 2px;
  border-radius: 1px;
  background: currentColor;
  opacity: 0.15;
}
.adaptive-th:hover .col-resize-handle::after,
.col-resize-handle:hover::after,
.col-resize-handle:focus-visible::after {
  opacity: 0.7;
}
.col-resize-handle:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: -2px;
}
</style>

<style>
/* The floating copy lives in <body> (teleported), so its styles cannot be scoped. It sits under the
   app header (z 2000) and below dialogs and drawers; only the header cells take the pointer. */
.adaptive-floating {
  position: fixed;
  z-index: 1500;
  overflow: hidden;
  pointer-events: none;
  background: #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.18);
}
.body--dark .adaptive-floating {
  background: #1d1d1d;
}
.adaptive-floating .adaptive-floating-middle {
  overflow: hidden;
}
.adaptive-floating th {
  pointer-events: auto;
  position: relative;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: inherit;
}
.adaptive-floating table {
  table-layout: fixed;
}
</style>
