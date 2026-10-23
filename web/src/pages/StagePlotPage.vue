<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('stagePlot.back')"
        class="q-mr-sm"
        @click="router.push(`/jobs/${jobId}`)"
      />
      <div class="col">
        <div class="text-h6">
          {{ t('stagePlot.title') }}
        </div>
        <div
          v-if="job"
          class="text-subtitle2 text-grey-7"
        >
          <span v-if="job.title">{{ job.title }}</span>
          <span v-if="job.venue_name"> · {{ job.venue_name }}</span>
        </div>
      </div>
    </div>

    <q-banner
      v-if="highlightIds.length"
      class="bg-accent text-white q-mb-md rounded-borders"
      dense
    >
      <template #avatar>
        <q-icon name="visibility" />
      </template>
      {{ t('stagePlot.highlightActive', { name: highlightLabel }) }}
      <template #action>
        <q-btn
          flat
          color="white"
          :label="t('stagePlot.highlightClear')"
          @click="clearHighlight"
        />
      </template>
    </q-banner>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-3">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('stagePlot.stageSetup') }}
            </div>
            <div
              v-if="job && job.venue_name"
              class="text-caption text-grey-7 q-mb-xs"
            >
              {{ job.venue_name }}
            </div>
            <div class="row q-gutter-sm">
              <q-input
                v-model.number="stageW"
                type="number"
                :label="t('stagePlot.stageWidth')"
                dense
                class="col"
                @change="saveStage"
              />
              <q-input
                v-model.number="stageH"
                type="number"
                :label="t('stagePlot.stageHeight')"
                dense
                class="col"
                @change="saveStage"
              />
            </div>
            <div class="text-caption text-grey-7 q-mt-xs">
              {{ t('stagePlot.stageUnitsHint') }}
            </div>
          </q-card-section>
        </q-card>

        <q-card
          flat
          bordered
          class="q-mt-md"
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
            <q-select
              v-model="draft.linked_channel_id"
              :label="t('stagePlot.linkChannel')"
              :options="channelOptions"
              emit-value
              map-options
              clearable
              dense
              class="q-mt-sm"
              @update:model-value="commitLink"
            />
            <q-select
              v-model="draft.linked_device_id"
              :label="t('stagePlot.linkDevice')"
              :options="deviceOptions"
              emit-value
              map-options
              clearable
              dense
              class="q-mt-sm"
              @update:model-value="commitDevice"
            />
            <div class="row q-gutter-sm q-mt-sm">
              <q-input
                v-model.number="draft.width_cm"
                type="number"
                :label="t('stagePlot.widthCm')"
                dense
                class="col"
                @update:model-value="commitSize"
              />
              <q-input
                v-model.number="draft.height_cm"
                type="number"
                :label="t('stagePlot.heightCm')"
                dense
                class="col"
                @update:model-value="commitSize"
              />
            </div>
            <q-input
              v-model="draft.image_url"
              :label="t('stagePlot.imageUrl')"
              dense
              class="q-mt-sm"
              @change="commitImage"
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
                <v-line
                  v-for="w in cablePlan.cableways"
                  :key="'w' + w.id"
                  :config="cableWayConfig(w)"
                />
                <v-line
                  v-for="row in visibleCableRows"
                  :key="'c' + row.key"
                  :config="cableConfig(row)"
                />
                <v-line
                  v-if="drawingWay && drawPoints.length"
                  :config="drawConfig"
                />
                <v-circle
                  v-for="(wp, i) in rerouteWaypoints"
                  :key="'wp' + i"
                  :config="waypointConfig(wp)"
                />
                <v-group
                  v-for="el in store.elements"
                  :key="el.id"
                  :config="groupConfig(el)"
                >
                  <v-rect :config="rectConfig(el)" />
                  <v-image
                    v-if="imageFor(el)"
                    :config="imageConfig(el)"
                  />
                  <v-text :config="textConfig(el)" />
                  <v-text
                    v-if="linkedSummary(el)"
                    :config="linkedTextConfig(el)"
                  />
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
      <div class="col-12">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="row items-center q-gutter-sm">
              <div class="text-subtitle1 col">
                {{ t('cables.title') }}
              </div>
              <q-toggle
                v-model="cablesVisible"
                :label="t('cables.show')"
              />
              <q-btn
                flat
                dense
                icon="alt_route"
                :label="t('cables.drawWay')"
                :disable="drawingWay || !!rerouteKey"
                @click="startDrawWay"
              />
              <q-btn
                flat
                dense
                icon="download"
                :label="t('cables.exportCsv')"
                :disable="!cableRows.length"
                @click="exportCables"
              />
            </div>
            <div
              v-if="drawingWay"
              class="row items-center q-gutter-sm q-mt-sm"
            >
              <div class="text-caption">
                {{ t('cables.drawHint') }}
              </div>
              <q-btn
                dense
                color="primary"
                :label="t('cables.finishWay')"
                :disable="drawPoints.length < 2"
                @click="finishDrawWay"
              />
              <q-btn
                dense
                flat
                :label="t('app.actions.cancel')"
                @click="cancelDrawWay"
              />
            </div>
            <div
              v-if="rerouteRow"
              class="row items-center q-gutter-sm q-mt-sm"
            >
              <div class="text-caption">
                {{ t('cables.rerouteHint', { name: 'C' + rerouteRow.index }) }}
              </div>
              <q-btn
                dense
                flat
                :label="t('cables.undoWaypoint')"
                :disable="!rerouteWaypoints.length"
                @click="undoWaypoint"
              />
              <q-btn
                dense
                flat
                :label="t('cables.resetRoute')"
                @click="resetRoute(rerouteRow)"
              />
              <q-btn
                dense
                color="primary"
                :label="t('cables.doneReroute')"
                @click="rerouteKey = null"
              />
            </div>

            <div class="row q-col-gutter-md q-mt-xs">
              <q-input
                :model-value="cablePlan.settings.slack_pct"
                type="number"
                dense
                outlined
                :label="t('cables.slackPct')"
                class="col-12 col-sm-3"
                @update:model-value="(v) => saveCableSettings({ slack_pct: Number(v) || 0 })"
              />
              <q-input
                :model-value="cablePlan.settings.slack_m"
                type="number"
                dense
                outlined
                :label="t('cables.slackM')"
                class="col-12 col-sm-3"
                @update:model-value="(v) => saveCableSettings({ slack_m: Number(v) || 0 })"
              />
              <q-input
                :model-value="standardLengthsText"
                dense
                outlined
                :label="t('cables.standardLengths')"
                class="col-12 col-sm-6"
                @update:model-value="saveStandardLengths"
              />
            </div>

            <div
              v-if="cableOrder.length"
              class="q-mt-md"
            >
              <div class="text-subtitle2 q-mb-xs">
                {{ t('cables.order') }}
              </div>
              <q-chip
                v-for="o in cableOrder"
                :key="String(o.length)"
                dense
                color="primary"
                text-color="white"
              >
                {{ o.count }} × {{ o.length === 'over' ? t('cables.overMax') : `${o.length} m` }}
              </q-chip>
            </div>

            <q-list
              separator
              class="q-mt-md"
            >
              <q-item
                v-for="row in cableRows"
                :key="row.key"
                :active="selectedCableKey === row.key || rerouteKey === row.key"
                clickable
                @click="selectedCableKey = row.key"
              >
                <q-item-section>
                  <q-item-label>
                    C{{ row.index }} · {{ row.fromName }} → {{ row.toName }}
                  </q-item-label>
                  <q-item-label caption>
                    {{ row.label }} · {{ row.connector || '—' }} ·
                    {{ row.placed ? t(`cables.route.${row.mode}`) : t('cables.notPlaced') }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-item-label v-if="row.placed">
                    {{ row.pathM }} m
                  </q-item-label>
                  <q-item-label
                    v-if="row.placed"
                    caption
                  >
                    {{ t('cables.cut') }}:
                    {{ row.assignedM === null ? t('cables.overMax') : `${row.assignedM} m` }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <div class="row no-wrap">
                    <q-btn
                      flat
                      dense
                      round
                      :icon="row.hidden ? 'visibility_off' : 'visibility'"
                      :aria-label="t('cables.show')"
                      @click.stop="toggleCableHidden(row)"
                    />
                    <q-btn
                      flat
                      dense
                      round
                      icon="edit_route"
                      :aria-label="t('cables.reroute')"
                      :disable="!row.placed || !!drawingWay"
                      @click.stop="startReroute(row)"
                    />
                    <q-btn
                      v-if="row.requestedMode === 'manual'"
                      flat
                      dense
                      round
                      icon="undo"
                      :aria-label="t('cables.resetRoute')"
                      @click.stop="resetRoute(row)"
                    />
                  </div>
                </q-item-section>
              </q-item>
            </q-list>
            <div
              v-if="!cableRows.length"
              class="text-grey-7 q-mt-sm"
            >
              {{ t('cables.none') }}
            </div>

            <div
              v-if="cablePlan.cableways.length"
              class="q-mt-md"
            >
              <div class="text-subtitle2 q-mb-xs">
                {{ t('cables.waysTitle') }}
              </div>
              <div
                v-for="(w, i) in cablePlan.cableways"
                :key="w.id"
                class="row items-center q-gutter-sm"
              >
                <div class="col">
                  {{ t('cables.wayLabel', { n: i + 1 }) }}
                  <span class="text-grey-7">({{ w.points.length }} {{ t('cables.points') }})</span>
                </div>
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('cables.deleteWay')"
                  @click="removeCableway(w.id)"
                />
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { api } from '@/boot/api';
import { useStagePlotStore } from '@/stores/stageplot';
import { useDevicesStore } from '@/stores/devices';
import {
  buildCableRows,
  cablesToCsv,
  DEFAULT_CABLE_SETTINGS,
  emptyCablePlan,
  lengthOrder,
} from '@/utils/cables';

const { t } = useI18n({ useScope: 'global' });
const route = useRoute();
const router = useRouter();
const jobId = route.params.jobId;
const store = useStagePlotStore();
const devicesStore = useDevicesStore();

const DEFAULT_W = 1200;
const DEFAULT_H = 700;
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

const pointTypeKey = {
  mixer: 'typeMixer',
  analog_stagebox: 'typeAnalog',
  digital_stagebox: 'typeDigital',
  split: 'typeSplit',
  network: 'typeNetwork',
  direct: 'typeDirect',
  speaker: 'typeSpeaker',
  monitor: 'typeMonitor',
  recorder: 'typeRecorder',
  amp: 'typeAmp',
  stage: 'typeStage',
  other: 'typeOther',
};
function patchPointTypeLabel(pt) {
  return t(`channels.patchPoint.${pointTypeKey[pt] || 'typeDirect'}`);
}

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
const draft = ref({
  label: '',
  rotation: 0,
  position_x: 0,
  position_y: 0,
  linked_channel_id: null,
  linked_device_id: null,
  width_cm: 60,
  height_cm: 60,
  image_url: '',
});

const stageW = ref(DEFAULT_W);
const stageH = ref(DEFAULT_H);
const job = ref(null);
const channelLists = ref([]);
const imageCache = ref({});

const pxPerCm = computed(() => scale.value);
const selected = computed(
  () => store.elements.find((e) => e.id === selectedId.value) || null,
);
const channelOptions = computed(() => {
  const opts = [];
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      const bits = [`Ch ${ch.channel_number}: ${ch.source_label || ''}`.trim()];
      if (ch.input_type) bits.push(ch.input_type);
      opts.push({ value: ch.id, label: bits.join(' · ') });
    }
  }
  return opts;
});
const pointChannelMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) m[p.id] = ch.id;
    }
  }
  return m;
});
const pointNameMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        m[p.id] = deviceNameMap.value[p.device_id] || patchPointTypeLabel(p.point_type);
      }
    }
  }
  return m;
});
const deviceOptions = computed(() =>
  devicesStore.devices.map((d) => ({ value: d.id, label: d.name || '—' })),
);
const deviceNameMap = computed(() => {
  const m = {};
  for (const d of devicesStore.devices) m[d.id] = d.name || '—';
  return m;
});
const deviceChannelMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        if (p.device_id) {
          (m[p.device_id] = m[p.device_id] || new Set()).add(ch.channel_id);
        }
      }
    }
  }
  return m;
});
const devicePatchPointMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        if (p.device_id) {
          (m[p.device_id] = m[p.device_id] || new Set()).add(p.id);
        }
      }
    }
  }
  return m;
});

const highlightParam = computed(() => route.query.highlight || '');
const highlightIds = computed(() => {
  const raw = highlightParam.value;
  if (!raw) return [];
  const idx = String(raw).indexOf(':');
  const mode = idx >= 0 ? String(raw).slice(0, idx) : String(raw);
  const value = idx >= 0 ? String(raw).slice(idx + 1) : '';
  const deviceSet = new Set();
  const channelSet = new Set();
  const pointSet = new Set();
  if (mode === 'device' && value) {
    deviceSet.add(value);
  } else if (mode === 'channel' && value) {
    channelSet.add(value);
    for (const [devId, chans] of Object.entries(deviceChannelMap.value)) {
      if (chans.has(value)) deviceSet.add(devId);
    }
  } else if (mode === 'patchpoint' && value) {
    pointSet.add(value);
    if (pointChannelMap.value[value]) channelSet.add(pointChannelMap.value[value]);
    for (const [devId, pts] of Object.entries(devicePatchPointMap.value)) {
      if (pts.has(value)) deviceSet.add(devId);
    }
  } else if (mode === 'sheet' && value) {
    const name = decodeURIComponent(value);
    const dev = devicesStore.devices.find(
      (d) => (d.name || '').toLowerCase() === name.toLowerCase(),
    );
    if (dev) deviceSet.add(dev.id);
    for (const list of channelLists.value) {
      for (const ch of list.channels || []) {
        for (const p of ch.patch_points || []) {
          if (p.device_id && p.device_id === dev?.id) {
            pointSet.add(p.id);
            channelSet.add(ch.channel_id);
          }
        }
      }
    }
  }
  const ids = [];
  for (const el of store.elements) {
    if (
      (el.linked_device_id && deviceSet.has(el.linked_device_id)) ||
      (el.linked_channel_id && channelSet.has(el.linked_channel_id)) ||
      (el.linked_patch_point_id && pointSet.has(el.linked_patch_point_id))
    ) {
      ids.push(el.id);
    }
  }
  return ids;
});
const highlightLabel = computed(() => {
  const raw = highlightParam.value;
  if (!raw) return '';
  const idx = String(raw).indexOf(':');
  const mode = idx >= 0 ? String(raw).slice(0, idx) : String(raw);
  const value = idx >= 0 ? String(raw).slice(idx + 1) : '';
  if (mode === 'sheet') return decodeURIComponent(value || '');
  if (mode === 'device') return deviceNameMap.value[value] || '';
  if (mode === 'channel') {
    const ch = findChannel(value);
    return ch ? `Ch ${ch.channel_number}` : '';
  }
  if (mode === 'patchpoint') return pointNameMap.value[value] || '';
  return '';
});
function clearHighlight() {
  router.replace({ name: route.name, params: route.params });
}
const xLabel = computed(() => `X (${unit.value})`);
const yLabel = computed(() => `Y (${unit.value})`);
const stageConfig = computed(() => ({
  width: stageW.value * pxPerCm.value,
  height: stageH.value * pxPerCm.value,
}));
const stageBg = computed(() => ({
  x: 0,
  y: 0,
  width: stageW.value * pxPerCm.value,
  height: stageH.value * pxPerCm.value,
  fill: '#0f161a',
  stroke: '#37474f',
  strokeWidth: 2,
  listening: false,
}));
const gridLines = computed(() => {
  const lines = [];
  const w = stageW.value * pxPerCm.value;
  const h = stageH.value * pxPerCm.value;
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
    onclick: () => select(el.id),
    ontap: () => select(el.id),
    ondragend: (e) => onDragEnd(el, e),
    ontransformend: (e) => onTransformEnd(el, e),
  };
}
function rectConfig(el) {
  const def = defFor(el.element_type);
  const hi = highlightIds.value.includes(el.id);
  return {
    width: el.width_cm * pxPerCm.value,
    height: el.height_cm * pxPerCm.value,
    fill: def.color,
    cornerRadius: 4,
    opacity: hi ? 1 : selectedId.value === el.id ? 1 : 0.85,
    stroke: hi ? '#35A853' : 'transparent',
    strokeWidth: hi ? 4 : 0,
    shadowColor: hi ? '#35A853' : 'transparent',
    shadowBlur: hi ? 14 : 0,
  };
}
function textConfig(el) {
  const s = pxPerCm.value;
  return {
    text: el.label || defFor(el.element_type).label,
    x: 0,
    y: 0,
    width: el.width_cm * s,
    height: el.height_cm * s,
    align: 'center',
    verticalAlign: 'middle',
    fontSize: Math.max(10, 12 * s),
    fill: '#ffffff',
    listening: false,
  };
}
function imageFor(el) {
  return el.image_url ? imageCache.value[el.id] || null : null;
}
function findChannel(channelId) {
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      if (ch.id === channelId) return ch;
    }
  }
  return null;
}
function linkedSummary(el) {
  const parts = [];
  if (el.linked_device_id) {
    const name = deviceNameMap.value[el.linked_device_id];
    if (name) parts.push(name);
  }
  if (el.linked_channel_id) {
    const ch = findChannel(el.linked_channel_id);
    if (ch) parts.push(`Ch ${ch.channel_number}`);
  }
  return parts.join(' · ');
}
function linkedTextConfig(el) {
  const s = pxPerCm.value;
  return {
    text: linkedSummary(el),
    x: 0,
    y: el.height_cm * s + 2,
    width: el.width_cm * s,
    align: 'center',
    fontSize: Math.max(9, 10 * s),
    fill: '#9ccc9c',
    listening: false,
  };
}
function imageConfig(el) {
  return {
    image: imageFor(el),
    x: 0,
    y: 0,
    width: el.width_cm * pxPerCm.value,
    height: el.height_cm * pxPerCm.value,
    listening: false,
  };
}
function loadImages(els) {
  for (const el of els) {
    if (!el.image_url) continue;
    const cached = imageCache.value[el.id];
    if (cached && cached.src === el.image_url) continue;
    const img = new Image();
    img.onload = () => {
      imageCache.value = { ...imageCache.value, [el.id]: img };
    };
    img.src = el.image_url;
  }
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
      linked_channel_id: el.linked_channel_id || null,
      linked_device_id: el.linked_device_id || null,
      width_cm: el.width_cm,
      height_cm: el.height_cm,
      image_url: el.image_url || '',
    };
  }
  updateTransformer();
}

function onStageClick(e) {
  if (drawingWay.value) {
    addDrawPoint(e);
    return;
  }
  if (rerouteKey.value) {
    addWaypoint(e);
    return;
  }
  if (e.target === e.target.getStage()) {
    selectedId.value = null;
    selectedCableKey.value = null;
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
    position_x: stageW.value / 2 - def.w / 2,
    position_y: stageH.value / 2 - def.h / 2,
    rotation: 0,
    label: def.label,
    width_cm: def.w,
    height_cm: def.h,
  };
  store.createElement(jobId, payload).then((created) => select(created.id));
}

function addCustom() {
  const payload = {
    element_type: 'custom',
    position_x: stageW.value / 2 - CUSTOM_DEF.w / 2,
    position_y: stageH.value / 2 - CUSTOM_DEF.h / 2,
    rotation: 0,
    label: t('stagePlot.custom'),
    width_cm: CUSTOM_DEF.w,
    height_cm: CUSTOM_DEF.h,
  };
  store.createElement(jobId, payload).then((created) => select(created.id));
}

function commitDraft() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { label: draft.value.label });
}
function commitLink(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { linked_channel_id: val || null });
}
function commitDevice(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { linked_device_id: val || null });
}
function commitSize() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    width_cm: Number(draft.value.width_cm) || 0,
    height_cm: Number(draft.value.height_cm) || 0,
  });
}
function commitImage() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { image_url: draft.value.image_url || '' });
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

async function saveStage() {
  try {
    await api.patch(`/jobs/${jobId}`, {
      stage_width_cm: stageW.value,
      stage_height_cm: stageH.value,
    });
  } catch (err) {
    console.error('Failed to save stage size', err);
  }
}

async function loadJob() {
  try {
    const { data } = await api.get(`/jobs/${jobId}`);
    job.value = data;
    if (data.stage_width_cm && data.stage_width_cm > 0) stageW.value = data.stage_width_cm;
    if (data.stage_height_cm && data.stage_height_cm > 0) stageH.value = data.stage_height_cm;
  } catch (err) {
    console.error('Failed to load job', err);
  }
}

async function loadChannels() {
  try {
    const { data } = await api.get(`/jobs/${jobId}/channel-lists`);
    channelLists.value = data || [];
  } catch (err) {
    console.error('Failed to load channel lists', err);
  }
}

const cablesVisible = ref(true);
const selectedCableKey = ref(null);
const rerouteKey = ref(null);
const drawingWay = ref(false);
const drawPoints = ref([]);

const cablePlan = computed(() => emptyCablePlan(job.value?.cable_plan));
const cableRows = computed(() =>
  buildCableRows({
    lists: channelLists.value,
    devices: devicesStore.devices,
    elements: store.elements,
    plan: cablePlan.value,
  }),
);
const visibleCableRows = computed(() =>
  cablesVisible.value ? cableRows.value.filter((r) => r.placed && !r.hidden) : [],
);
const cableOrder = computed(() => lengthOrder(cableRows.value));
const rerouteRow = computed(() => cableRows.value.find((r) => r.key === rerouteKey.value) || null);
const rerouteWaypoints = computed(
  () => cablePlan.value.routes[rerouteKey.value]?.waypoints || [],
);
const standardLengthsText = computed(() =>
  (cablePlan.value.settings.standard_lengths_m || DEFAULT_CABLE_SETTINGS.standard_lengths_m).join(', '),
);

async function savePlan(next) {
  job.value = { ...job.value, cable_plan: next };
  try {
    const { data } = await api.patch(`/jobs/${jobId}`, { cable_plan: next });
    job.value = { ...job.value, cable_plan: data.cable_plan };
  } catch (err) {
    console.error('Failed to save cables', err);
  }
}
function updateRoute(key, patch) {
  const plan = cablePlan.value;
  const current = plan.routes[key] || { mode: 'auto', waypoints: [], hidden: false };
  savePlan({ ...plan, routes: { ...plan.routes, [key]: { ...current, ...patch } } });
}
function toggleCableHidden(row) {
  updateRoute(row.key, { hidden: !row.hidden });
}
function resetRoute(row) {
  updateRoute(row.key, { mode: 'auto', waypoints: [] });
  if (rerouteKey.value === row.key) rerouteKey.value = null;
}
function startReroute(row) {
  selectedCableKey.value = row.key;
  rerouteKey.value = row.key;
  const keep = row.requestedMode === 'manual' ? row.waypoints : [];
  updateRoute(row.key, { mode: 'manual', waypoints: keep });
}
function stagePoint(e) {
  const p = e.target.getStage().getPointerPosition();
  if (!p) return null;
  return [p.x / pxPerCm.value, p.y / pxPerCm.value];
}
function addWaypoint(e) {
  const cm = stagePoint(e);
  const key = rerouteKey.value;
  if (!cm || !key) return;
  const current = cablePlan.value.routes[key]?.waypoints || [];
  updateRoute(key, { mode: 'manual', waypoints: [...current, cm] });
}
function undoWaypoint() {
  const key = rerouteKey.value;
  if (!key) return;
  const current = cablePlan.value.routes[key]?.waypoints || [];
  updateRoute(key, { mode: 'manual', waypoints: current.slice(0, -1) });
}
function startDrawWay() {
  rerouteKey.value = null;
  drawPoints.value = [];
  drawingWay.value = true;
}
function cancelDrawWay() {
  drawingWay.value = false;
  drawPoints.value = [];
}
function addDrawPoint(e) {
  const cm = stagePoint(e);
  if (cm) drawPoints.value = [...drawPoints.value, cm];
}
function finishDrawWay() {
  if (drawPoints.value.length < 2) return;
  const plan = cablePlan.value;
  savePlan({
    ...plan,
    cableways: [...plan.cableways, { id: crypto.randomUUID(), points: drawPoints.value }],
  });
  cancelDrawWay();
}
function removeCableway(id) {
  const plan = cablePlan.value;
  savePlan({ ...plan, cableways: plan.cableways.filter((w) => w.id !== id) });
}
function saveCableSettings(patch) {
  const plan = cablePlan.value;
  savePlan({ ...plan, settings: { ...plan.settings, ...patch } });
}
function saveStandardLengths(text) {
  const lengths = String(text)
    .split(',')
    .map((v) => Number(v.trim()))
    .filter((v) => v > 0)
    .sort((a, b) => a - b);
  saveCableSettings({ standard_lengths_m: lengths });
}
function exportCables() {
  const blob = new Blob([cablesToCsv(cableRows.value)], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'cables.csv';
  a.click();
  URL.revokeObjectURL(url);
}
function cableLinePoints(points) {
  return points.flatMap(([x, y]) => [x * pxPerCm.value, y * pxPerCm.value]);
}
function cableConfig(row) {
  const active = selectedCableKey.value === row.key || rerouteKey.value === row.key;
  return {
    points: cableLinePoints(row.points),
    stroke: active ? '#ffb300' : '#b0bec5',
    strokeWidth: active ? 3 : 2,
    lineCap: 'round',
    lineJoin: 'round',
    dash: row.mode === 'direct' ? [8, 6] : undefined,
    hitStrokeWidth: 12,
    onclick: () => (selectedCableKey.value = row.key),
  };
}
function cableWayConfig(w) {
  return {
    points: cableLinePoints(w.points),
    stroke: '#546e7a',
    strokeWidth: 2,
    dash: [4, 4],
    listening: false,
  };
}
const drawConfig = computed(() => ({
  points: cableLinePoints(drawPoints.value),
  stroke: '#ffb300',
  strokeWidth: 2,
  dash: [6, 4],
  listening: false,
}));
function waypointConfig(wp) {
  return {
    x: wp[0] * pxPerCm.value,
    y: wp[1] * pxPerCm.value,
    radius: 5,
    fill: '#ffb300',
    listening: false,
  };
}

watch(selectedId, updateTransformer);
watch(scale, updateTransformer);
watch(
  () => store.elements,
  (els) => loadImages(els),
  { deep: false },
);

onMounted(() => {
  loadJob();
  loadChannels();
  devicesStore.fetchDevices(jobId);
  store.fetchElements(jobId);
});
</script>
