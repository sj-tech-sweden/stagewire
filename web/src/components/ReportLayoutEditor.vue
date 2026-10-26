<template>
  <div
    ref="page"
    class="report-layout-page"
    :style="{ aspectRatio: pageAspectRatio }"
    @pointermove="moveObject"
    @pointerup="endPointer"
    @pointercancel="endPointer"
  >
    <div
      v-for="item in visibleObjects"
      :key="item.id"
      class="report-layout-object"
      :class="{ 'report-layout-object--selected': item.id === selectedId }"
      :style="objectStyle(item)"
      @pointerdown.stop="selectObject(item)"
    >
      <div
        class="report-layout-object__handle"
        :aria-label="dragLabel"
        @pointerdown.stop.prevent="startMove($event, item)"
      >
        <q-icon name="drag_indicator" />
        <span>{{ objectLabel(item) }}</span>
      </div>
      <div
        v-if="item.html.includes('{{stage_plot}}') && stageWidth > 0 && stageHeight > 0"
        class="report-layout-object__content report-layout-object__stage-plot"
      >
        <svg
          :viewBox="`0 0 1000 ${plotHeight * stagePlotScale}`"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          :aria-label="stagePlotLabel"
        >
          <rect
            x="0"
            y="0"
            :width="plotWidth * stagePlotScale"
            :height="plotHeight * stagePlotScale"
            fill="#f5faf5"
            stroke="#455a64"
            vector-effect="non-scaling-stroke"
          />
          <rect
            :x="plotOffsetX * stagePlotScale"
            :y="plotOffsetY * stagePlotScale"
            :width="stageWidth * stagePlotScale"
            :height="stageHeight * stagePlotScale"
            fill="#e8f2e8"
            stroke="#3f873f"
            stroke-width="2"
            vector-effect="non-scaling-stroke"
          />
          <text
            :x="(plotOffsetX + 4) * stagePlotScale"
            :y="(plotOffsetY + 16) * stagePlotScale"
            font-size="14"
            fill="#17652b"
          >
            {{ t('reports.stageAreaLabel', { width: stageWidth, height: stageHeight }) }}
          </text>
          <template v-if="stagePlotOptions.show_cableways">
            <polyline
              v-for="way in cablePlan.cableways || []"
              :key="`way-${way.id}`"
              :points="plotPolyline(way.points)"
              fill="none"
              stroke="#546e7a"
              stroke-dasharray="4 4"
              vector-effect="non-scaling-stroke"
            />
          </template>
          <template v-if="stagePlotOptions.show_cables">
            <polyline
              v-for="cable in stagePlotCables"
              :key="`cable-${cable.id}`"
              :points="plotPolyline(cable.points)"
              fill="none"
              stroke="#83939a"
              vector-effect="non-scaling-stroke"
            />
          </template>
          <template
            v-for="element in stagePlotElements"
            :key="`coverage-${element.id}`"
          >
            <path
              v-if="stagePlotOptions.show_coverage && coveragePath(element)"
              :d="coveragePath(element)"
              fill="rgba(255, 183, 77, 0.18)"
              stroke="rgba(216, 137, 32, 0.75)"
              vector-effect="non-scaling-stroke"
            />
          </template>
          <g
            v-for="element in stagePlotElements"
            :key="element.id"
            :transform="`rotate(${element.rotation || 0} ${(plotOffsetX + element.position_x + element.width_cm / 2) * stagePlotScale} ${(plotOffsetY + element.position_y + element.height_cm / 2) * stagePlotScale})`"
          >
            <rect
              :x="(plotOffsetX + element.position_x) * stagePlotScale"
              :y="(plotOffsetY + element.position_y) * stagePlotScale"
              :width="element.width_cm * stagePlotScale"
              :height="element.height_cm * stagePlotScale"
              :fill="['mixer', 'stagebox', 'split'].includes(element.element_type) ? '#e6ddf1' : '#dce9ef'"
              stroke="#1f4b66"
              vector-effect="non-scaling-stroke"
            />
            <text
              :x="(plotOffsetX + element.position_x + element.width_cm / 2) * stagePlotScale"
              :y="(plotOffsetY + element.position_y + element.height_cm / 2) * stagePlotScale"
              text-anchor="middle"
              dominant-baseline="middle"
              font-size="14"
            >
              {{ element.label || element.element_type }}
            </text>
          </g>
        </svg>
      </div>
      <SanitizedHtml
        v-else
        class="report-layout-object__content"
        :html="previewHtml(item.html)"
      />
      <button
        class="report-layout-object__resize"
        type="button"
        :aria-label="resizeLabel"
        @pointerdown.stop.prevent="startResize($event, item)"
      />
    </div>
    <div
      v-if="!visibleObjects.length"
      class="report-layout-empty"
    >
      {{ emptyLabel }}
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
  pageIndex: { type: Number, default: 0 },
  pageAspectRatio: { type: String, default: '174 / 261' },
  fields: { type: Array, default: () => [] },
  tables: { type: Array, default: () => [] },
  previewJob: { type: Object, default: null },
  stagePlotElements: { type: Array, default: () => [] },
  stagePlotCables: { type: Array, default: () => [] },
  stageWidth: { type: Number, default: 0 },
  stageHeight: { type: Number, default: 0 },
  venueWidth: { type: Number, default: 0 },
  venueHeight: { type: Number, default: 0 },
  stageX: { type: Number, default: 0 },
  stageY: { type: Number, default: 0 },
  stagePlotOptions: { type: Object, default: () => ({}) },
  cablePlan: { type: Object, default: () => ({}) },
  stagePlotLabel: { type: String, required: true },
  dragLabel: { type: String, required: true },
  resizeLabel: { type: String, required: true },
  emptyLabel: { type: String, required: true },
  objectLabel: { type: Function, required: true },
})
const emit = defineEmits(['update:modelValue', 'update:selectedId'])
const page = ref(null)
const pointerState = ref(null)
const useVenue = computed(
  () =>
    props.stagePlotOptions.view === 'venue' &&
    props.venueWidth > 0 &&
    props.venueHeight > 0,
)
const plotWidth = computed(() => (useVenue.value ? props.venueWidth : props.stageWidth))
const plotHeight = computed(() => (useVenue.value ? props.venueHeight : props.stageHeight))
const plotOffsetX = computed(() => (useVenue.value ? props.stageX : 0))
const plotOffsetY = computed(() => (useVenue.value ? props.stageY : 0))
const stagePlotScale = computed(() => 1000 / Math.max(plotWidth.value, 1))
const visibleObjects = computed(() =>
  props.modelValue.filter((item) => Number(item.page || 0) === props.pageIndex),
)

function plotPolyline(points = []) {
  return points
    .map(([x, y]) => `${(plotOffsetX.value + x) * stagePlotScale.value},${(plotOffsetY.value + y) * stagePlotScale.value}`)
    .join(' ')
}

function coveragePath(element) {
  const types = ['speaker', 'speaker_main', 'speaker_sub', 'speaker_delay']
  const angle = Number(element.coverage_angle_h) || 0
  const distance = Number(element.coverage_distance_m) || 0
  if (!types.includes(element.element_type) || angle <= 0 || distance <= 0) return ''
  const scale = stagePlotScale.value
  const cx = (plotOffsetX.value + element.position_x + element.width_cm / 2) * scale
  const cy = (plotOffsetY.value + element.position_y + element.height_cm / 2) * scale
  const rotation = Number(element.rotation) || 0
  const start = (rotation - 90 - Math.min(angle, 360) / 2) * Math.PI / 180
  const steps = Math.max(8, Math.min(48, Math.ceil(angle / 6)))
  const radius = distance * 100 * scale
  const arc = Array.from({ length: steps + 1 }, (_, index) => {
    const theta = start + ((Math.min(angle, 360) * Math.PI / 180) * index) / steps
    return `${cx + Math.cos(theta) * radius} ${cy + Math.sin(theta) * radius}`
  })
  return `M ${cx} ${cy} L ${arc.join(' L ')} Z`
}

const allowedTags = new Set([
  'P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'STRONG', 'B', 'EM', 'I', 'U', 'S',
  'BR', 'UL', 'OL', 'LI', 'BLOCKQUOTE', 'TABLE', 'THEAD', 'TBODY', 'TR',
  'TH', 'TD', 'SPAN',
])
const blockedTags = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'IMG', 'SVG'])

function toSafeNodes(node, key = 'root') {
  return Array.from(node.childNodes).flatMap((child, index) => {
    if (child.nodeType === Node.TEXT_NODE) return [child.textContent || '']
    if (child.nodeType !== Node.ELEMENT_NODE || blockedTags.has(child.tagName)) return []
    const children = toSafeNodes(child, `${key}-${index}`)
    if (!allowedTags.has(child.tagName)) return children
    const attributes = {}
    if (child.tagName === 'TD' || child.tagName === 'TH') {
      for (const name of ['colspan', 'rowspan']) {
        if (child.hasAttribute(name)) attributes[name] = child.getAttribute(name)
      }
    }
    return [h(child.tagName.toLowerCase(), { key: `${key}-${index}`, ...attributes }, children)]
  })
}

const SanitizedHtml = defineComponent({
  props: {
    html: { type: String, default: '' },
  },
  setup(props) {
    return () => {
      const doc = new DOMParser().parseFromString(props.html, 'text/html')
      return h('div', toSafeNodes(doc.body))
    }
  },
})

function objectStyle(item) {
  return {
    left: `${item.x}%`,
    top: `${item.y}%`,
    width: `${item.width}%`,
    height: `${item.height}%`,
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character])
}

function previewHtml(value) {
  let html = String(value || '')
  html = html.replace(/\{\{job\.([a-zA-Z0-9_.-]+)\}\}/g, (token, key) => {
    const label = props.fields.find((field) => field.key === `job.${key}`)?.label || key
    const value = props.previewJob?.[key]
    return escapeHtml(value || label || token)
  })
  html = html.replace(/\{\{table:([a-zA-Z0-9_.-]+)\}\}/g, (token, key) => {
    const table = props.tables.find((item) => item.key === key)
    if (!table) return escapeHtml(token)
    const headings = table.columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join('')
    const cells = table.columns.map(() => '<td>…</td>').join('')
    return `<table><thead><tr>${headings}</tr></thead><tbody><tr>${cells}</tr></tbody></table>`
  })
  return html.replace(/\{\{stage_plot\}\}/g, escapeHtml(props.stagePlotLabel))
}

function selectObject(item) {
  emit('update:selectedId', item.id)
}

function startMove(event, item) {
  selectObject(item)
  pointerState.value = { itemId: item.id, mode: 'move', startX: event.clientX, startY: event.clientY }
  event.currentTarget.setPointerCapture(event.pointerId)
}

function startResize(event, item) {
  selectObject(item)
  pointerState.value = { itemId: item.id, mode: 'resize', startX: event.clientX, startY: event.clientY }
  event.currentTarget.setPointerCapture(event.pointerId)
}

function moveObject(event) {
  if (!pointerState.value || !page.value) return
  const target = visibleObjects.value.find((item) => item.id === pointerState.value.itemId)
  if (!target) return
  const bounds = page.value.getBoundingClientRect()
  const dx = ((event.clientX - pointerState.value.startX) / bounds.width) * 100
  const dy = ((event.clientY - pointerState.value.startY) / bounds.height) * 100
  const next = props.modelValue.map((item) => {
    if (item.id !== target.id) return item
    if (pointerState.value.mode === 'resize') {
      return {
        ...item,
        width: Math.min(100 - item.x, Math.max(8, item.width + dx)),
        height: Math.min(100 - item.y, Math.max(6, item.height + dy)),
      }
    }
    const x = Math.min(100 - item.width, Math.max(0, item.x + dx))
    const y = Math.min(100 - item.height, Math.max(0, item.y + dy))
    return { ...item, x, y }
  })
  pointerState.value.startX = event.clientX
  pointerState.value.startY = event.clientY
  emit('update:modelValue', next)
}

function endPointer() {
  pointerState.value = null
}
</script>

<style scoped>
.report-layout-page {
  position: relative;
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
  overflow: hidden;
  background: #fff;
  border: 1px solid #aab4b8;
  box-shadow: 0 2px 12px rgb(0 0 0 / 18%);
  touch-action: none;
}

.report-layout-object {
  position: absolute;
  overflow: hidden;
  border: 1px solid transparent;
  color: #172126;
  font-size: clamp(7px, 1.7vw, 12px);
}

.report-layout-object--selected {
  border: 1px solid #3f873f;
  outline: 1px solid rgb(63 135 63 / 25%);
}

.report-layout-object__handle {
  display: flex;
  min-height: 18px;
  align-items: center;
  gap: 3px;
  padding: 0 3px;
  overflow: hidden;
  background: rgb(63 135 63 / 14%);
  color: #245b2a;
  cursor: move;
  touch-action: none;
  user-select: none;
  white-space: nowrap;
}

.report-layout-object__content {
  padding: 2px 4px;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.report-layout-object__content :deep(h1) {
  margin: 0;
  font-size: 1.5em;
  line-height: 1.2;
}

.report-layout-object__content :deep(p) {
  margin: 0 0 0.25em;
}

.report-layout-object__content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85em;
}

.report-layout-object__content :deep(td),
.report-layout-object__content :deep(th) {
  border: 1px solid #aab4b8;
  padding: 1px 3px;
}

.report-layout-object__stage-plot {
  display: grid;
  height: calc(100% - 18px);
  place-items: center;
}

.report-layout-object__stage-plot svg {
  display: block;
  width: 100%;
  height: 100%;
}

.report-layout-object__resize {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 18px;
  height: 18px;
  border: 0;
  background: #3f873f;
  cursor: nwse-resize;
  touch-action: none;
}

.report-layout-object__resize::after {
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 7px;
  height: 7px;
  border-right: 2px solid white;
  border-bottom: 2px solid white;
  content: '';
}

.report-layout-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #637177;
}
</style>
