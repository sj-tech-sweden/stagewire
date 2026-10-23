<template>
  <q-page padding>
    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-3">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('stagePlot.palette') }}
            </div>
            <q-list
              dense
              separator
            >
              <q-item
                v-for="(def, type) in palette"
                :key="type"
                v-ripple
                clickable
                @click="addElement(type)"
              >
                <q-item-section avatar>
                  <q-icon
                    :name="def.icon"
                    :style="{ color: def.color }"
                  />
                </q-item-section>
                <q-item-section>{{ def.label }}</q-item-section>
              </q-item>
              <q-item
                v-ripple
                clickable
                @click="addCustom"
              >
                <q-item-section avatar>
                  <q-icon name="add" />
                </q-item-section>
                <q-item-section>{{ t('stagePlot.custom') }}</q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>

        <q-card
          v-if="selected"
          flat
          bordered
          class="q-mt-md"
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('stagePlot.element') }}
            </div>
            <q-input
              v-model="draft.label"
              :label="t('stagePlot.label')"
              dense
              @change="commitDraft"
            />
            <q-input
              v-model.number="draft.rotation"
              type="number"
              :label="t('stagePlot.rotation')"
              dense
              class="q-mt-sm"
              @update:model-value="commitRotation"
            />
            <div class="row q-gutter-sm q-mt-sm">
              <q-input
                v-model.number="draft.position_x"
                type="number"
                :label="xLabel"
                dense
                class="col"
                @update:model-value="commitPosition"
              />
              <q-input
                v-model.number="draft.position_y"
                type="number"
                :label="yLabel"
                dense
                class="col"
                @update:model-value="commitPosition"
              />
            </div>
            <q-btn
              color="negative"
              class="full-width q-mt-md"
              :label="t('stagePlot.delete')"
              @click="removeSelected"
            />
          </q-card-section>
        </q-card>

        <q-card
          flat
          bordered
          class="q-mt-md"
        >
          <q-card-section>
            <div class="text-subtitle2 q-mb-xs">
              {{ t('stagePlot.units') }}
            </div>
            <q-btn-toggle
              v-model="unit"
              spread
              no-caps
              :options="unitOptions"
            />
            <div class="text-subtitle2 q-mt-sm q-mb-xs">
              {{ t('stagePlot.zoom') }}
            </div>
            <q-slider
              v-model="scale"
              :min="0.3"
              :max="1.5"
              :step="0.1"
              label
            />
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-9">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-h6">
              {{ t('stagePlot.title') }}
            </div>
            <div class="text-caption text-grey-7">
              {{ t('stagePlot.addHint') }}
            </div>
            <div
              v-if="store.loading"
              class="q-my-md"
            >
              <q-spinner color="primary" />
            </div>
            <div
              v-else-if="!store.elements.length"
              class="text-grey-7 q-my-md"
            >
              {{ t('stagePlot.empty') }}
            </div>
            <v-stage
              v-else
              ref="stageRef"
              :config="stageConfig"
              @click="onStageClick"
              @tap="onStageClick"
            >
              <v-layer>
                <v-rect :config="stageBg" />
                <v-line
                  v-for="(g, i) in gridLines"
                  :key="'g' + i"
                  :config="g"
                />
                <v-group
                  v-for="el in store.elements"
                  :key="el.id"
                  :config="groupConfig(el)"
                  @dragend="onDragEnd(el, $event)"
                  @transformend="onTransformEnd(el, $event)"
                  @click="select(el.id)"
                  @tap="select(el.id)"
                >
                  <v-rect :config="rectConfig(el)" />
                  <v-text :config="textConfig(el)" />
                </v-group>
                <v-transformer
                  ref="trRef"
                  :config="transformerConfig"
                />
              </v-layer>
            </v-stage>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useStagePlotStore } from '@/stores/stageplot';

const { t } = useI18n({ useScope: 'global' });
const route = useRoute();
const jobId = route.params.jobId;
const store = useStagePlotStore();

const STAGE_W_CM = 1200;
const STAGE_H_CM = 700;
const GRID_CM = 50;

const palette = {
  performer: { label: 'Performer', icon: 'person', color: '#35A853', w: 60, h: 60 },
  instrument: { label: 'Instrument', icon: 'music_note', color: '#26A69A', w: 90, h: 60 },
  microphone: { label: 'Microphone', icon: 'mic', color: '#AB47BC', w: 26, h: 26 },
  speaker: { label: 'Speaker', icon: 'volume_up', color: '#FF7043', w: 42, h: 72 },
  monitor: { label: 'Monitor', icon: 'headphones', color: '#26C6DA', w: 46, h: 36 },
  di: { label: 'DI', icon: 'crop_square', color: '#5C6BC0', w: 24, h: 18 },
  multicore: { label: 'Multicore', icon: 'cable', color: '#8D6E63', w: 32, h: 120 },
  dais: { label: 'Dais', icon: 'crop_16_9', color: '#78909C', w: 220, h: 120 },
};
const CUSTOM_DEF = { label: 'Custom', icon: 'add', color: '#90A4AE', w: 60, h: 60 };

function defFor(type) {
  return palette[type] || CUSTOM_DEF;
}

const scale = ref(0.7);
const unit = ref('cm');
const unitOptions = [
  { label: 'cm', value: 'cm' },
  { label: 'mm', value: 'mm' },
];
const selectedId = ref(null);
const stageRef = ref(null);
const trRef = ref(null);
const draft = ref({ label: '', rotation: 0, position_x: 0, position_y: 0 });

const pxPerCm = computed(() => scale.value);
const selected = computed(
  () => store.elements.find((e) => e.id === selectedId.value) || null,
);
const xLabel = computed(() => `X (${unit.value})`);
const yLabel = computed(() => `Y (${unit.value})`);
const stageConfig = computed(() => ({
  width: STAGE_W_CM * pxPerCm.value,
  height: STAGE_H_CM * pxPerCm.value,
}));
const stageBg = computed(() => ({
  x: 0,
  y: 0,
  width: STAGE_W_CM * pxPerCm.value,
  height: STAGE_H_CM * pxPerCm.value,
  fill: '#0f161a',
  stroke: '#37474f',
  strokeWidth: 2,
  listening: false,
}));
const gridLines = computed(() => {
  const lines = [];
  const w = STAGE_W_CM * pxPerCm.value;
  const h = STAGE_H_CM * pxPerCm.value;
  const step = GRID_CM * pxPerCm.value;
  for (let x = step; x < w; x += step) {
    lines.push({ points: [x, 0, x, h], stroke: '#1c272d', strokeWidth: 1, listening: false });
  }
  for (let y = step; y < h; y += step) {
    lines.push({ points: [0, y, w, y], stroke: '#1c272d', strokeWidth: 1, listening: false });
  }
  return lines;
});
const transformerConfig = {
  rotateEnabled: true,
  enabledAnchors: [],
  rotationSnaps: [0, 45, 90, 135, 180, 225, 270, 315],
  borderEnabled: false,
};

function round1(n) {
  return Math.round(n * 10) / 10;
}
function groupConfig(el) {
  return {
    id: el.id,
    x: el.position_x * pxPerCm.value,
    y: el.position_y * pxPerCm.value,
    rotation: el.rotation,
    draggable: true,
  };
}
function rectConfig(el) {
  const def = defFor(el.element_type);
  return {
    width: def.w * pxPerCm.value,
    height: def.h * pxPerCm.value,
    fill: def.color,
    cornerRadius: 4,
    opacity: selectedId.value === el.id ? 1 : 0.85,
  };
}
function textConfig(el) {
  const def = defFor(el.element_type);
  const s = pxPerCm.value;
  return {
    text: el.label || def.label,
    x: 0,
    y: 0,
    width: def.w * s,
    height: def.h * s,
    align: 'center',
    verticalAlign: 'middle',
    fontSize: Math.max(10, 12 * s),
    fill: '#ffffff',
    listening: false,
  };
}

function updateTransformer() {
  const tr = trRef.value && trRef.value.getNode ? trRef.value.getNode() : null;
  if (!tr) return;
  if (!selectedId.value) {
    tr.nodes([]);
    return;
  }
  const stage = stageRef.value && stageRef.value.getStage ? stageRef.value.getStage() : null;
  const node = stage ? stage.findOne('#' + selectedId.value) : null;
  tr.nodes(node ? [node] : []);
  const layer = tr.getLayer();
  if (layer) layer.batchDraw();
}

function select(id) {
  selectedId.value = id;
  const el = store.elements.find((e) => e.id === id);
  if (el) {
    draft.value = {
      label: el.label,
      rotation: el.rotation,
      position_x: el.position_x,
      position_y: el.position_y,
    };
  }
  updateTransformer();
}

function onStageClick(e) {
  if (e.target === e.target.getStage()) {
    selectedId.value = null;
    updateTransformer();
  }
}

function onDragEnd(el, e) {
  const node = e.target;
  const x = round1(node.x() / pxPerCm.value);
  const y = round1(node.y() / pxPerCm.value);
  store.updateElement(jobId, el.id, { position_x: x, position_y: y });
  if (selectedId.value === el.id) {
    draft.value.position_x = x;
    draft.value.position_y = y;
  }
}

function onTransformEnd(el, e) {
  const rotation = Math.round(e.target.rotation());
  store.updateElement(jobId, el.id, { rotation });
  if (selectedId.value === el.id) draft.value.rotation = rotation;
}

function addElement(type) {
  const def = palette[type];
  const payload = {
    element_type: type,
    position_x: STAGE_W_CM / 2 - def.w / 2,
    position_y: STAGE_H_CM / 2 - def.h / 2,
    rotation: 0,
    label: def.label,
  };
  store.createElement(jobId, payload).then((created) => select(created.id));
}

function addCustom() {
  const payload = {
    element_type: 'custom',
    position_x: STAGE_W_CM / 2 - CUSTOM_DEF.w / 2,
    position_y: STAGE_H_CM / 2 - CUSTOM_DEF.h / 2,
    rotation: 0,
    label: t('stagePlot.custom'),
  };
  store.createElement(jobId, payload).then((created) => select(created.id));
}

function commitDraft() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { label: draft.value.label });
}
function commitRotation() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    rotation: Number(draft.value.rotation) || 0,
  });
}
function commitPosition() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    position_x: Number(draft.value.position_x) || 0,
    position_y: Number(draft.value.position_y) || 0,
  });
}

async function removeSelected() {
  if (!selectedId.value) return;
  const id = selectedId.value;
  selectedId.value = null;
  await store.deleteElement(jobId, id);
}

watch(selectedId, updateTransformer);
watch(scale, updateTransformer);

onMounted(() => {
  store.fetchElements(jobId);
});
</script>
