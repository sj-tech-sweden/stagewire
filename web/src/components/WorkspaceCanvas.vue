<template>
  <div
    ref="host"
    class="canvas-host"
    :class="{ 'hand-cursor': panning }"
    :data-zoom="zoom"
    :data-pan="`${Math.round(pan.x)},${Math.round(pan.y)}`"
    data-testid="workspace-canvas"
  >
    <v-stage
      ref="stageRef"
      :config="{ width: size.width, height: size.height, x: pan.x, y: pan.y, draggable: panning }"
      @click="onStageClick"
      @tap="onStageClick"
      @dragend="onStagePanEnd"
      @mousemove="onMove"
      @touchmove="onMove"
      @mouseup="endLink"
      @touchend="endLink"
    >
      <v-layer>
        <v-rect :config="{ x: 0, y: 0, width: size.width, height: size.height, fill: bg, listening: false }" />
        <template v-if="frame">
          <v-rect :config="venueConfig" />
          <v-rect :config="stageConfig" />
          <v-image
            v-if="coverageImage"
            :config="coverageConfig"
          />
          <v-line
            v-for="shape in shapeLines"
            :key="shape.id"
            :config="shape.config"
          />
          <v-line
            v-if="audienceLine"
            :config="audienceLine"
          />
          <v-line
            v-for="way in wayLines"
            :key="way.id"
            :config="way.config"
          />
          <v-line
            v-for="cable in cableLines"
            :key="cable.id"
            :config="cable.config"
          />
          <v-line
            v-if="draftLine"
            :config="draftLine"
          />
          <v-line
            v-if="audienceDraftLine"
            :config="audienceDraftLine"
          />
          <v-group
            v-for="outlet in outletMarks"
            :key="outlet.id"
            :config="{ id: `outlet:${outlet.id}`, x: outlet.x, y: outlet.y, draggable: !connectMode && !panning }"
            @dragend="(e) => onOutletDrop(outlet, e)"
            @click="emit('select-outlet', outlet.id)"
            @tap="emit('select-outlet', outlet.id)"
          >
            <v-circle :config="{ radius: connectMode ? 11 : 7, fill: '#FFEB3B', stroke: '#F9A825', strokeWidth: 2 }" />
            <v-text :config="{ text: outlet.label, fontSize: 10, x: 14, y: -5, fill: '#ddd', listening: false }" />
          </v-group>
        </template>
        <v-line
          v-for="line in lines"
          :key="line.id"
          :config="{ points: line.points, stroke: line.color, strokeWidth: 2, opacity: 0.8 }"
        />
        <v-line
          v-if="link.from"
          :config="{
            points: link.points,
            stroke: '#FFFFFF',
            strokeWidth: 2,
            dash: [6, 4],
            listening: false,
          }"
        />
        <v-group
          v-for="device in devices"
          :key="device.id"
          :config="{
            id: device.id,
            x: (device.canvas_x_cm + origin.x) * zoom,
            y: (device.canvas_y_cm + origin.y) * zoom,
            rotation: device.canvas_rotation || 0,
            draggable: !connectMode && !panning,
          }"
          @click="emit('select', device.id)"
          @tap="emit('select', device.id)"
          @dragend="(e) => onDrop(device, e)"
          @mousedown="startLink(device)"
          @touchstart="startLink(device)"
        >
          <v-rect
            :config="{
              width: box(device).w,
              height: box(device).h,
              cornerRadius: 4,
              dash: isPlotElement(device) ? [6, 3] : undefined,
              fill: fillFor(device),
              stroke: device.id === selectedId ? '#FFFFFF' : strokeFor(device),
              strokeWidth: device.id === selectedId ? 3 : 1,
            }"
          />
          <v-text
            :config="{
              x: 4,
              y: 3,
              width: Math.max(8, box(device).w - 8),
              height: Math.max(8, box(device).h - 6),
              text: box(device).w >= 40 ? device.name : '',
              fontSize: Math.min(12, Math.max(8, Math.round(box(device).h * 0.4))),
              fill: '#FFFFFF',
              ellipsis: true,
              wrap: 'none',
            }"
          />
        </v-group>
      </v-layer>
    </v-stage>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useQuasar } from 'quasar';
import { objectColor } from '@/utils/plotObjects';
import { SIGNAL_COLOR, boxFor, centerOf, isPlotElement, needsBookingRequest } from '@/utils/workspace';

// ``frame`` (see utils/plotFrame.js) is the venue/stage the gear sits in. Without it the canvas is
// a plain board. Gear coordinates are stage-relative, so everything is drawn at (origin + x) and
// the drop handler subtracts the origin again.
const props = defineProps({
  frame: { type: Object, default: null },
  outlets: { type: Array, default: () => [] },
  showOutlets: { type: Boolean, default: true },
  showAudience: { type: Boolean, default: true },
  coverageImage: { type: Object, default: null },
  shapes: { type: Array, default: () => [] },
  // routed cables ({ key, points, mode }), cableways ({ id, points }) and the cableway being drawn
  cables: { type: Array, default: () => [] },
  cableways: { type: Array, default: () => [] },
  drawPoints: { type: Array, default: () => [] },
  drawing: { type: Boolean, default: false },
  // the audience area being outlined (venue cm) and whether a click adds a corner of it
  audienceDraft: { type: Array, default: () => [] },
  audienceDrawing: { type: Boolean, default: false },
  devices: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
  zoom: { type: Number, default: 0.8 },
  deviceScale: { type: Number, default: 1 },
  // the hand tool (or Space) pans a map that is zoomed in beyond the standard fit
  hand: { type: Boolean, default: false },
  connectMode: { type: Boolean, default: false },
});
const emit = defineEmits(['select', 'move', 'connect', 'pan', 'move-outlet', 'select-outlet', 'draw-point', 'audience-point']);

const $q = useQuasar();
const host = ref(null);
const stageRef = ref(null);
const link = reactive({ from: null, points: [0, 0, 0, 0] });
const hostWidth = ref(800);
// The map is drawn at full size and the page scrolls, so there are no scrollbars on the map. Only
// when it is zoomed in beyond the standard fit (the venue as wide as the page) does the map get a
// viewport of its own and move by panning with the hand tool.
const mapSize = computed(() => ({
  width: props.frame ? props.frame.width * props.zoom : hostWidth.value,
  height: props.frame ? props.frame.height * props.zoom : 0,
}));
const zoomedIn = computed(() => Boolean(props.frame) && mapSize.value.width > hostWidth.value + 1);
const panning = computed(() => props.hand && zoomedIn.value);
const viewportHeight = computed(() => Math.max(300, Math.round(window.innerHeight * 0.7)));
const size = computed(() => {
  const minHeight = $q.screen.lt.sm ? 380 : 520;
  if (!props.frame) return { width: hostWidth.value, height: minHeight };
  if (zoomedIn.value) {
    return { width: hostWidth.value, height: Math.min(mapSize.value.height, viewportHeight.value) };
  }
  return { width: hostWidth.value, height: Math.max(minHeight, mapSize.value.height) };
});

// Pan offset of the map inside its viewport, kept so the map always covers the viewport.
const pan = reactive({ x: 0, y: 0 });
function clampPan() {
  if (!zoomedIn.value) {
    pan.x = 0;
    pan.y = 0;
  } else {
    pan.x = Math.min(0, Math.max(hostWidth.value - mapSize.value.width, pan.x));
    pan.y = Math.min(0, Math.max(size.value.height - mapSize.value.height, pan.y));
  }
  emit('pan', { x: pan.x, y: pan.y });
}
function onStagePanEnd(event) {
  if (event.target !== stageRef.value?.getStage()) return;
  pan.x = event.target.x();
  pan.y = event.target.y();
  clampPan();
  event.target.position({ x: pan.x, y: pan.y });
}
watch([() => props.zoom, hostWidth, () => props.frame?.width, () => props.frame?.height], clampPan);

let observer = null;

const bg = computed(() => ($q.dark.isActive ? '#0C1114' : '#F5F5F5'));
const DOMAIN_FILL = { audio: '#2E7D32', lighting: '#8D6E00', video: '#00697F', power: '#8E0012', other: '#455A64' };
const fillFor = (device) => objectColor(device) || DOMAIN_FILL[device.domain] || DOMAIN_FILL.other;
const strokeFor = (device) => (needsBookingRequest(device) ? '#FFC107' : 'rgba(255,255,255,0.25)');

const origin = computed(() => ({ x: props.frame?.stageX || 0, y: props.frame?.stageY || 0 }));
const venueConfig = computed(() => ({
  x: 0,
  y: 0,
  width: props.frame.width * props.zoom,
  height: props.frame.height * props.zoom,
  fill: $q.dark.isActive ? '#0b1013' : '#ECEFF1',
  stroke: '#455a64',
  strokeWidth: 2,
  listening: false,
}));
const stageConfig = computed(() => ({
  x: props.frame.stageX * props.zoom,
  y: props.frame.stageY * props.zoom,
  width: props.frame.stageW * props.zoom,
  height: props.frame.stageH * props.zoom,
  fill: $q.dark.isActive ? '#0f161a' : '#FAFAFA',
  stroke: '#37474f',
  strokeWidth: 2,
  listening: false,
}));
const coverageConfig = computed(() => ({
  image: props.coverageImage,
  x: 0,
  y: 0,
  width: props.frame.width * props.zoom,
  height: props.frame.height * props.zoom,
  listening: false,
}));
// Camera and projector views arrive in stage-relative cm; they are drawn at the stage offset.
const shapeLines = computed(() =>
  props.shapes.map((shape) => ({
    id: shape.id,
    config: {
      points: shape.points.flatMap(([x, y]) => [(x + origin.value.x) * props.zoom, (y + origin.value.y) * props.zoom]),
      closed: shape.closed,
      fill: shape.fill,
      stroke: shape.stroke,
      strokeWidth: shape.strokeWidth,
      dash: shape.dash,
      listening: false,
    },
  })),
);
const toPx = (points) =>
  points.flatMap(([x, y]) => [(x + origin.value.x) * props.zoom, (y + origin.value.y) * props.zoom]);
const wayLines = computed(() =>
  props.cableways.map((way) => ({
    id: way.id,
    config: { points: toPx(way.points), stroke: '#ffb300', strokeWidth: 6, opacity: 0.35, lineCap: 'round', lineJoin: 'round', listening: false },
  })),
);
const cableLines = computed(() =>
  props.cables
    .filter((c) => c.placed && !c.hidden)
    .map((c) => ({
      id: c.key,
      config: {
        points: toPx(c.points),
        stroke: '#b0bec5',
        strokeWidth: 2,
        dash: c.mode === 'direct' ? [8, 6] : undefined,
        lineCap: 'round',
        lineJoin: 'round',
        listening: false,
      },
    })),
);
const draftLine = computed(() =>
  props.drawing && props.drawPoints.length
    ? { points: toPx(props.drawPoints), stroke: '#ffb300', strokeWidth: 3, dash: [6, 4], listening: false }
    : null,
);

// While a cableway is being drawn a click on the map adds a point (stage-relative cm).
function onStageClick(event) {
  const drawingAny = props.drawing || props.audienceDrawing;
  if (!drawingAny || event.target !== stageRef.value?.getStage()) return;
  const pos = stageRef.value.getStage().getRelativePointerPosition();
  if (props.audienceDrawing) {
    // the audience area is in venue coordinates: no stage offset
    emit('audience-point', [Math.round(pos.x / props.zoom), Math.round(pos.y / props.zoom)]);
    return;
  }
  emit('draw-point', [Math.round(pos.x / props.zoom - origin.value.x), Math.round(pos.y / props.zoom - origin.value.y)]);
}

const audienceDraftLine = computed(() =>
  props.audienceDrawing && props.audienceDraft.length
    ? {
        points: props.audienceDraft.flatMap(([x, y]) => [x * props.zoom, y * props.zoom]),
        stroke: '#e53935',
        strokeWidth: 3,
        dash: [6, 4],
        listening: false,
      }
    : null,
);

const audienceLine = computed(() => {
  const polygon = props.frame?.audience || [];
  if (!props.showAudience || polygon.length < 3) return null;
  return {
    points: polygon.flatMap(([x, y]) => [x * props.zoom, y * props.zoom]),
    closed: true,
    fill: 'rgba(229, 57, 53, 0.12)',
    stroke: '#e53935',
    strokeWidth: 2,
    dash: [10, 6],
    listening: false,
  };
});
const outletMarks = computed(() =>
  props.showOutlets
    ? props.outlets.map((o) => ({
        id: o.id,
        x: (origin.value.x + o.x_cm) * props.zoom,
        y: (origin.value.y + o.y_cm) * props.zoom,
        label: o.name || o.connector || '',
      }))
    : [],
);

const box = (device) => boxFor(device, props.zoom, props.deviceScale);
const center = (device) => {
  const [x, y] = centerOf(device, props.zoom, props.deviceScale);
  return [x + origin.value.x * props.zoom, y + origin.value.y * props.zoom];
};
const placed = computed(() => new Map(props.devices.map((d) => [d.id, d])));
const lines = computed(() =>
  props.edges
    .filter((e) => placed.value.has(e.src_device_id) && placed.value.has(e.dst_device_id))
    .map((e) => {
      const a = placed.value.get(e.src_device_id);
      const b = placed.value.get(e.dst_device_id);
      return {
        id: e.id,
        color: SIGNAL_COLOR[e.signal] || SIGNAL_COLOR.data,
        points: [...center(a), ...center(b)],
      };
    }),
);


function startLink(device) {
  if (!props.connectMode) return;
  link.from = device;
  link.points = [...center(device), ...center(device)];
}

function onMove() {
  if (!link.from) return;
  const pos = stageRef.value?.getStage().getPointerPosition();
  if (pos) link.points = [...center(link.from), pos.x, pos.y];
}

function endLink() {
  if (!link.from) return;
  const stage = stageRef.value.getStage();
  const pos = stage.getPointerPosition() || { x: link.points[2], y: link.points[3] };
  const hit = stage.getIntersection(pos);
  const targetId = hit?.getParent()?.id();
  const fromId = link.from.id;
  link.from = null;
  if (targetId && targetId !== fromId) emit('connect', { srcId: fromId, dstId: targetId });
}

// An outlet dragged to a new spot is saved on the venue (stage-relative cm, like gear).
function onOutletDrop(outlet, event) {
  emit('move-outlet', {
    id: outlet.id,
    x: Math.round(event.target.x() / props.zoom - origin.value.x),
    y: Math.round(event.target.y() / props.zoom - origin.value.y),
  });
}

function onDrop(device, event) {
  emit('move', {
    id: device.id,
    x: Math.round(event.target.x() / props.zoom - origin.value.x),
    y: Math.round(event.target.y() / props.zoom - origin.value.y),
  });
}

onMounted(() => {
  const fit = () => {
    hostWidth.value = Math.max(280, host.value?.clientWidth || 800);
  };
  fit();
  observer = new ResizeObserver(fit);
  observer.observe(host.value);
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<style scoped>
.canvas-host {
  width: 100%;
  overflow: hidden;
  border-radius: 4px;
  touch-action: none;
}
.hand-cursor :deep(canvas) {
  cursor: grab;
}
</style>
