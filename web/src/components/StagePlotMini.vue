<template>
  <v-stage :config="stageConfig">
    <v-layer>
      <v-rect :config="bgConfig" />
      <v-group
        v-for="el in elements"
        :key="el.id"
        :config="groupConfig(el)"
      >
        <v-rect :config="rectConfig(el)" />
        <v-text :config="textConfig(el)" />
      </v-group>
    </v-layer>
  </v-stage>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  elements: { type: Array, default: () => [] },
  stageWidth: { type: Number, default: 1200 },
  stageHeight: { type: Number, default: 700 },
  highlightIds: { type: Array, default: () => [] },
  maxWidth: { type: Number, default: 360 },
});

const PALETTE = {
  performer: '#35A853',
  instrument: '#26A69A',
  microphone: '#AB47BC',
  speaker: '#FF7043',
  monitor: '#26C6DA',
  di: '#5C6BC0',
  multicore: '#8D6E63',
  dais: '#78909C',
  custom: '#90A4AE',
};

const scale = computed(() =>
  Math.min(1, props.maxWidth / (props.stageWidth || 1200)),
);
const scaledW = computed(() => (props.stageWidth || 1200) * scale.value);
const scaledH = computed(() => (props.stageHeight || 700) * scale.value);

const stageConfig = computed(() => ({
  width: scaledW.value,
  height: scaledH.value,
}));
const bgConfig = computed(() => ({
  x: 0,
  y: 0,
  width: scaledW.value,
  height: scaledH.value,
  fill: '#0f161a',
  stroke: '#37474f',
  strokeWidth: 1,
  listening: false,
}));

function isHi(el) {
  return props.highlightIds.includes(el.id);
}
function colorFor(type) {
  return PALETTE[type] || PALETTE.custom;
}
function groupConfig(el) {
  return {
    x: el.position_x * scale.value,
    y: el.position_y * scale.value,
    listening: false,
  };
}
function rectConfig(el) {
  const hi = isHi(el);
  return {
    width: (el.width_cm || 60) * scale.value,
    height: (el.height_cm || 60) * scale.value,
    fill: colorFor(el.element_type),
    cornerRadius: 2,
    opacity: hi ? 1 : 0.4,
    stroke: hi ? '#35A853' : 'transparent',
    strokeWidth: hi ? 3 : 0,
    shadowColor: hi ? '#35A853' : 'transparent',
    shadowBlur: hi ? 8 : 0,
  };
}
function textConfig(el) {
  return {
    text: el.label || '',
    x: 0,
    y: 0,
    width: (el.width_cm || 60) * scale.value,
    height: (el.height_cm || 60) * scale.value,
    align: 'center',
    verticalAlign: 'middle',
    fontSize: Math.max(7, 9 * scale.value),
    fill: '#ffffff',
    listening: false,
  };
}
</script>
