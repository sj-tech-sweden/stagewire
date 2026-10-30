<template>
  <div
    ref="host"
    class="canvas-host"
    data-testid="workspace-canvas"
  >
    <v-stage :config="{ width: size.width, height: size.height }">
      <v-layer>
        <v-rect :config="{ x: 0, y: 0, width: size.width, height: size.height, fill: bg }" />
        <v-line
          v-for="line in lines"
          :key="line.id"
          :config="{ points: line.points, stroke: line.color, strokeWidth: 2, opacity: 0.8 }"
        />
        <v-group
          v-for="device in devices"
          :key="device.id"
          :config="{
            x: device.canvas_x_cm * zoom,
            y: device.canvas_y_cm * zoom,
            draggable: true,
          }"
          @click="emit('select', device.id)"
          @tap="emit('select', device.id)"
          @dragend="(e) => onDrop(device, e)"
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
});
const emit = defineEmits(['select', 'move']);

const $q = useQuasar();
const host = ref(null);
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
