<template>
  <div>
    <div class="row q-gutter-xs q-mb-xs items-center wrap">
      <q-btn
        dense
        no-caps
        :color="drawingFootprint ? 'primary' : 'grey-7'"
        :flat="!drawingFootprint"
        icon="draw"
        :label="t('venues.geometry.drawFootprint')"
        @click="toggleDraw('footprint')"
      />
      <q-btn
        dense
        no-caps
        :color="drawingStage ? 'primary' : 'grey-7'"
        :flat="!drawingStage"
        icon="draw"
        :label="t('venues.geometry.drawStage')"
        @click="toggleDraw('stage')"
      />
      <q-btn
        dense
        no-caps
        flat
        color="grey-7"
        icon="delete_sweep"
        :label="t('venues.geometry.clear')"
        :disable="!hasFootprintPolygon && !hasStagePolygon"
        @click="clearAll"
      />
    </div>

    <div
      ref="host"
      class="canvas-host"
      :class="{ 'hand-cursor': drawingFootprint || drawingStage }"
    >
      <v-stage
        ref="stageRef"
        :config="{ width: canvasW, height: canvasH, x: 0, y: 0 }"
        @click="onStageClick"
        @tap="onStageClick"
      >
        <v-layer>
          <!-- Faint bounding box that the whole drawing sits inside. -->
          <v-rect :config="boundsConfig" />

          <!-- Footprint: rectangle (presets) or drawn polygon (custom_polygon). -->
          <template v-if="footprintShape === 'custom_polygon'">
            <v-line :config="footprintLineConfig" />
            <v-circle
              v-for="(p, i) in footprintPolygon"
              :key="`f${i}`"
              :config="vertexConfig(p)"
              @dragend="(e) => onVertexDragEnd(e, i, 'footprint')"
              @dblclick="() => onVertexDblClick(i, 'footprint')"
              @dbltap="() => onVertexDblClick(i, 'footprint')"
            />
          </template>
          <template v-else>
            <v-rect :config="footprintRectConfig" />
            <v-circle
              :config="venueResizeHandle"
              @dragend="onVenueResize"
            />
          </template>

          <!-- Stage group (translated to its position inside the venue). -->
          <v-group :config="{ x: stageX * zoom, y: stageY * zoom }">
            <template v-if="stageShape === 'custom_polygon'">
              <v-line :config="stageLineConfig" />
              <v-circle
                v-for="(p, i) in stagePolygon"
                :key="`s${i}`"
                :config="vertexConfig(p)"
                @dragend="(e) => onVertexDragEnd(e, i, 'stage')"
                @dblclick="() => onVertexDblClick(i, 'stage')"
                @dbltap="() => onVertexDblClick(i, 'stage')"
              />
            </template>
            <template v-else>
              <v-rect
                :config="stageRectConfig"
                @dragend="onStageDragEnd"
              />
              <v-circle
                :config="stageResizeHandle"
                @dragend="onStageResize"
              />
            </template>
          </v-group>
        </v-layer>
      </v-stage>
    </div>

    <div class="text-caption text-grey-6 q-mt-xs">
      {{ drawingFootprint || drawingStage ? t('venues.geometry.drawHint') : t('venues.geometry.hint') }}
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { fitZoom, polygonBounds } from '@/utils/plotFrame';

const props = defineProps({
  venueWidth: { type: Number, default: 0 },
  venueHeight: { type: Number, default: 0 },
  stageX: { type: Number, default: 0 },
  stageY: { type: Number, default: 0 },
  stageW: { type: Number, default: 0 },
  stageH: { type: Number, default: 0 },
  footprintShape: { type: String, default: 'rectangular' },
  footprintPolygon: { type: Array, default: () => [] },
  stageShape: { type: String, default: 'proscenium' },
  stagePolygon: { type: Array, default: () => [] },
});
const emit = defineEmits(['change']);

const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();

const host = ref(null);
const stageRef = ref(null);
const hostWidth = ref(640);
const drawingFootprint = ref(false);
const drawingStage = ref(false);

let observer = null;
onMounted(() => {
  const fit = () => {
    hostWidth.value = Math.max(280, host.value?.clientWidth || 640);
  };
  fit();
  observer = new ResizeObserver(fit);
  observer.observe(host.value);
});
onBeforeUnmount(() => observer?.disconnect());

// The drawing surface: the footprint bounding box, grown to enclose the stage.
const frame = computed(() => {
  const fp =
    props.footprintShape === 'custom_polygon' && props.footprintPolygon.length >= 3
      ? polygonBounds(props.footprintPolygon)
      : { w: props.venueWidth, h: props.venueHeight };
  const sp =
    props.stageShape === 'custom_polygon' && props.stagePolygon.length >= 3
      ? polygonBounds(props.stagePolygon)
      : { w: props.stageW, h: props.stageH };
  return {
    width: Math.max(fp.w, props.stageX + sp.w, 100),
    height: Math.max(fp.h, props.stageY + sp.h, 100),
  };
});
// Fit the frame into the host, but never zoom past 1.5x or below readability.
const zoom = computed(() => Math.min(1.5, fitZoom(frame.value, hostWidth.value, 380, 12)));
const canvasW = computed(() => Math.round(frame.value.width * zoom.value));
const canvasH = computed(() => Math.round(frame.value.height * zoom.value));

const COL = {
  venueFill: $q.dark.isActive ? '#0b1013' : '#ECEFF1',
  venueStroke: '#455a64',
  stageFill: $q.dark.isActive ? '#0f161a' : '#FAFAFA',
  stageStroke: '#37474f',
};

const boundsConfig = computed(() => ({
  x: 0,
  y: 0,
  width: canvasW.value,
  height: canvasH.value,
  fill: COL.venueFill,
  stroke: '#90a4ae',
  strokeWidth: 1,
  listening: false,
}));
const footprintRectConfig = computed(() => ({
  x: 0,
  y: 0,
  width: Math.max(0, props.venueWidth) * zoom.value,
  height: Math.max(0, props.venueHeight) * zoom.value,
  fill: COL.venueFill,
  stroke: COL.venueStroke,
  strokeWidth: 2,
  listening: false,
}));
const footprintLineConfig = computed(() => ({
  points: props.footprintPolygon.flatMap(([x, y]) => [x * zoom.value, y * zoom.value]),
  closed: true,
  fill: 'rgba(69, 90, 100, 0.06)',
  stroke: COL.venueStroke,
  strokeWidth: 2,
  dash: [8, 4],
  listening: false,
}));
const stageRectConfig = computed(() => ({
  x: 0,
  y: 0,
  width: Math.max(0, props.stageW) * zoom.value,
  height: Math.max(0, props.stageH) * zoom.value,
  fill: COL.stageFill,
  stroke: COL.stageStroke,
  strokeWidth: 2,
  draggable: true,
  listening: true,
}));
const stageLineConfig = computed(() => ({
  points: props.stagePolygon.flatMap(([x, y]) => [x * zoom.value, y * zoom.value]),
  closed: true,
  fill: $q.dark.isActive ? 'rgba(15, 22, 26, 0.6)' : 'rgba(255, 255, 255, 0.6)',
  stroke: COL.stageStroke,
  strokeWidth: 2,
  listening: false,
}));
const venueResizeHandle = computed(() => ({
  x: Math.max(0, props.venueWidth) * zoom.value,
  y: Math.max(0, props.venueHeight) * zoom.value,
  radius: 8,
  fill: '#35A853',
  stroke: '#1B5E20',
  strokeWidth: 2,
  draggable: true,
  listening: true,
}));
const stageResizeHandle = computed(() => ({
  x: Math.max(0, props.stageW) * zoom.value,
  y: Math.max(0, props.stageH) * zoom.value,
  radius: 8,
  fill: '#35A853',
  stroke: '#1B5E20',
  strokeWidth: 2,
  draggable: true,
  listening: true,
}));

const hasFootprintPolygon = computed(
  () => props.footprintShape === 'custom_polygon' && props.footprintPolygon.length >= 3,
);
const hasStagePolygon = computed(
  () => props.stageShape === 'custom_polygon' && props.stagePolygon.length >= 3,
);

function vertexConfig(p) {
  return {
    x: p[0] * zoom.value,
    y: p[1] * zoom.value,
    radius: 7,
    fill: '#FFEB3B',
    stroke: '#F9A825',
    strokeWidth: 2,
    draggable: true,
    listening: true,
  };
}

function emitChange(partial) {
  emit('change', partial);
}

function toggleDraw(kind) {
  if (kind === 'footprint') {
    drawingFootprint.value = !drawingFootprint.value;
    drawingStage.value = false;
  } else {
    drawingStage.value = !drawingStage.value;
    drawingFootprint.value = false;
  }
}

function clearAll() {
  if (hasFootprintPolygon.value) emitChange({ footprint_polygon: [] });
  if (hasStagePolygon.value) emitChange({ stage_polygon: [] });
}

// Clicking empty canvas while drawing appends a corner (footprint in venue cm,
// stage in stage-relative cm).
function onStageClick(e) {
  if (e.target !== stageRef.value?.getStage()) return;
  if (!drawingFootprint.value && !drawingStage.value) return;
  const pos = stageRef.value.getStage().getRelativePointerPosition();
  const cmX = Math.round(pos.x / zoom.value);
  const cmY = Math.round(pos.y / zoom.value);
  if (drawingFootprint.value) {
    emitChange({ footprint_polygon: [...props.footprintPolygon, [cmX, cmY]] });
  } else if (drawingStage.value) {
    emitChange({ stage_polygon: [...props.stagePolygon, [cmX - props.stageX, cmY - props.stageY]] });
  }
}

function onVertexDragEnd(e, i, kind) {
  const x = Math.round(e.target.x() / zoom.value);
  const y = Math.round(e.target.y() / zoom.value);
  const src = kind === 'footprint' ? props.footprintPolygon : props.stagePolygon;
  const poly = src.map((p, idx) => (idx === i ? [x, y] : p));
  emitChange(kind === 'footprint' ? { footprint_polygon: poly } : { stage_polygon: poly });
}

function onVertexDblClick(i, kind) {
  const src = kind === 'footprint' ? props.footprintPolygon : props.stagePolygon;
  if (src.length <= 3) return;
  const poly = src.filter((_, idx) => idx !== i);
  emitChange(kind === 'footprint' ? { footprint_polygon: poly } : { stage_polygon: poly });
}

function onVenueResize(e) {
  emitChange({
    venue_width_cm: Math.max(1, Math.round(e.target.x() / zoom.value)),
    venue_height_cm: Math.max(1, Math.round(e.target.y() / zoom.value)),
  });
}

function onStageResize(e) {
  emitChange({
    stage_width_cm: Math.max(1, Math.round(e.target.x() / zoom.value)),
    stage_height_cm: Math.max(1, Math.round(e.target.y() / zoom.value)),
  });
}

function onStageDragEnd(e) {
  emitChange({
    stage_x_cm: Math.round(e.target.x() / zoom.value),
    stage_y_cm: Math.round(e.target.y() / zoom.value),
  });
}
</script>

<style scoped>
.canvas-host {
  width: 100%;
  height: 380px;
  overflow: hidden;
  border-radius: 4px;
  touch-action: none;
  border: 1px solid rgba(128, 128, 128, 0.35);
}
.hand-cursor :deep(canvas) {
  cursor: crosshair;
}
</style>
