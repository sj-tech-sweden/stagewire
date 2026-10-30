<template>
  <div
    ref="host"
    class="canvas-host"
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
            x: device.canvas_x_cm * zoom,
            y: device.canvas_y_cm * zoom,
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
              width: BOX_W,
              height: BOX_H,
              cornerRadius: 4,
              fill: fillFor(device),
              stroke: device.id === selectedId ? '#FFFFFF' : strokeFor(device),
              strokeWidth: device.id === selectedId ? 3 : 1,
            }"
          />
          <v-text
            :config="{
              x: 6,
              y: 6,
              width: BOX_W - 12,
              height: BOX_H - 12,
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
import { SIGNAL_COLOR, needsBookingRequest } from '@/utils/workspace';

const BOX_W = 96;
const BOX_H = 40;

const props = defineProps({
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
const size = reactive({ width: 800, height: 520 });
let observer = null;

const bg = computed(() => ($q.dark.isActive ? '#0C1114' : '#F5F5F5'));
const DOMAIN_FILL = { audio: '#2E7D32', lighting: '#8D6E00', video: '#00697F', power: '#8E0012', other: '#455A64' };
const fillFor = (device) => DOMAIN_FILL[device.domain] || DOMAIN_FILL.other;
const strokeFor = (device) => (needsBookingRequest(device) ? '#FFC107' : 'rgba(255,255,255,0.25)');

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
        points: [
          a.canvas_x_cm * props.zoom + BOX_W / 2,
          a.canvas_y_cm * props.zoom + BOX_H / 2,
          b.canvas_x_cm * props.zoom + BOX_W / 2,
          b.canvas_y_cm * props.zoom + BOX_H / 2,
        ],
      };
    }),
);

function center(device) {
  return [device.canvas_x_cm * props.zoom + BOX_W / 2, device.canvas_y_cm * props.zoom + BOX_H / 2];
}

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
    x: Math.round(event.target.x() / props.zoom),
    y: Math.round(event.target.y() / props.zoom),
  });
}

onMounted(() => {
  const fit = () => {
    size.width = Math.max(280, host.value?.clientWidth || 800);
    size.height = $q.screen.lt.sm ? 380 : 520;
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
</style>
