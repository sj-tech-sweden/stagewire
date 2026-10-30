<template>
  <div
    ref="host"
    class="canvas-host"
    :data-zoom="zoom"
    data-testid="workspace-canvas"
  >
    <v-stage
      ref="stageRef"
      :config="{ width: size.width, height: size.height }"
      @mousemove="onMove"
      @touchmove="onMove"
      @mouseup="endLink"
      @touchend="endLink"
    >
      <v-layer>
        <v-rect :config="{ x: 0, y: 0, width: size.width, height: size.height, fill: bg }" />
        <template v-if="frame">
          <v-rect :config="venueConfig" />
          <v-rect :config="stageConfig" />
          <v-image
            v-if="coverageImage"
            :config="coverageConfig"
          />
          <v-line
            v-if="audienceLine"
            :config="audienceLine"
          />
          <v-group
            v-for="outlet in outletMarks"
            :key="outlet.id"
            :config="{ x: outlet.x, y: outlet.y, listening: false }"
          >
            <v-circle :config="{ radius: 7, fill: '#FFEB3B', stroke: '#F9A825', strokeWidth: 2 }" />
            <v-text :config="{ text: outlet.label, fontSize: 10, x: 10, y: -5, fill: '#ddd' }" />
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
            draggable: !connectMode,
          }"
          @click="emit('select', device.id)"
          @tap="emit('select', device.id)"
          @dragend="(e) => onDrop(device, e)"
          @mousedown="startLink(device)"
          @touchstart="startLink(device)"
        >
          <v-rect
            :config="{
              width: boxFor(device, zoom).w,
              height: boxFor(device, zoom).h,
              cornerRadius: 4,
              dash: isPlotElement(device) ? [6, 3] : undefined,
              fill: fillFor(device),
              stroke: device.id === selectedId ? '#FFFFFF' : strokeFor(device),
              strokeWidth: device.id === selectedId ? 3 : 1,
            }"
          />
          <v-text
            :config="{
              x: 6,
              y: 6,
              width: Math.max(8, boxFor(device, zoom).w - 12),
              height: Math.max(8, boxFor(device, zoom).h - 12),
              text: device.name,
              fontSize: 12,
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
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
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
  devices: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
  zoom: { type: Number, default: 0.8 },
  connectMode: { type: Boolean, default: false },
});
const emit = defineEmits(['select', 'move', 'connect']);

const $q = useQuasar();
const host = ref(null);
const stageRef = ref(null);
const link = reactive({ from: null, points: [0, 0, 0, 0] });
const hostWidth = ref(800);
const size = computed(() => {
  const minHeight = $q.screen.lt.sm ? 380 : 520;
  if (!props.frame) return { width: hostWidth.value, height: minHeight };
  return {
    width: Math.max(hostWidth.value, props.frame.width * props.zoom),
    height: Math.max(minHeight, props.frame.height * props.zoom),
  };
});
let observer = null;

const bg = computed(() => ($q.dark.isActive ? '#0C1114' : '#F5F5F5'));
const DOMAIN_FILL = { audio: '#2E7D32', lighting: '#8D6E00', video: '#00697F', power: '#8E0012', other: '#455A64' };
const fillFor = (device) => DOMAIN_FILL[device.domain] || DOMAIN_FILL.other;
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

const center = (device) => {
  const [x, y] = centerOf(device, props.zoom);
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
  overflow: auto;
  border-radius: 4px;
  touch-action: none;
}
</style>
