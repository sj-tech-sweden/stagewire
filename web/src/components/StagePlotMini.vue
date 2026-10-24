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
        <v-image
          v-if="imageFor(el)"
          :config="imageConfig(el)"
        />
        <v-text :config="textConfig(el)" />
      </v-group>
    </v-layer>
  </v-stage>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { getApiBaseUrl } from '@/utils/runtime-config';

const props = defineProps({
  elements: { type: Array, default: () => [] },
  stageWidth: { type: Number, default: 1200 },
  stageHeight: { type: Number, default: 700 },
  highlightIds: { type: Array, default: () => [] },
  maxWidth: { type: Number, default: 360 },
});

const imageCache = ref({});

function fullImageUrl(value) {
  if (!value) return value;
  if (/^https?:\/\//i.test(value)) return value;
  return getApiBaseUrl() + value;
}
function imageFor(el) {
  return el.image_url ? imageCache.value[el.id] || null : null;
}
function loadImages(els) {
  for (const el of els || []) {
    if (!el.image_url) continue;
    const src = fullImageUrl(el.image_url);
    const cached = imageCache.value[el.id];
    if (cached && cached.src === src) continue;
    const img = new Image();
    img.onload = () => {
      imageCache.value = { ...imageCache.value, [el.id]: img };
    };
    img.src = src;
  }
}
watch(
  () => (props.elements || []).map((e) => `${e.id}:${e.image_url}`).join('|'),
  () => loadImages(props.elements || []),
  { immediate: true },
);
function imageConfig(el) {
  const s = scale.value;
  return {
    image: imageFor(el),
    x: 0,
    y: 0,
    width: (el.width_cm || 60) * s,
    height: (el.height_cm || 60) * s,
    listening: false,
  };
}

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
  const hasImage = !!imageFor(el);
  return {
    width: (el.width_cm || 60) * scale.value,
    height: (el.height_cm || 60) * scale.value,
    fill: hasImage && !hi ? 'transparent' : colorFor(el.element_type),
    cornerRadius: 2,
    opacity: hi ? 1 : hasImage ? 1 : 0.4,
    stroke: hi ? '#35A853' : 'transparent',
    strokeWidth: hi ? 3 : 0,
    shadowColor: hi ? '#35A853' : 'transparent',
    shadowBlur: hi ? 8 : 0,
  };
}
function textConfig(el) {
  const s = scale.value;
  const text = el.label || '';
  if (imageFor(el) && text) {
    const labelFont = Math.max(7, 9 * s);
    return {
      text,
      x: 0,
      y: (el.height_cm || 60) * s + 1,
      width: (el.width_cm || 60) * s,
      align: 'center',
      fontSize: labelFont,
      fill: '#e0e0e0',
      listening: false,
    };
  }
  return {
    text,
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
