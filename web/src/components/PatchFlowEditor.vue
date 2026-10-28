<template>
  <div>
    <q-card-section class="q-gutter-sm">
      <div class="text-caption text-grey-7">
        {{ t('video.patchFlowHint') }}
      </div>
      <div
        v-for="(step, i) in steps"
        :key="step.key"
        class="row items-center q-gutter-xs no-wrap"
      >
        <div class="text-caption text-grey-7 q-pr-xs">
          {{ i + 1 }}
        </div>
        <q-select
          v-model="step.kind"
          :options="kindOptions"
          :label="t('video.stepKind')"
          emit-value
          map-options
          dense
          style="min-width: 150px"
          @update:model-value="() => (step.device_id = null)"
        />
        <q-select
          v-model="step.device_id"
          :options="deviceOptionsFor(step)"
          :label="t('video.stepDevice')"
          emit-value
          map-options
          dense
          use-input
          hide-selected
          fill-input
          input-debounce="0"
          class="col"
          @new-value="(val, done) => askNewDevice(step, val, done)"
        />
        <q-select
          v-if="i > 0"
          v-model="step.source_port"
          :options="sourcePortOptions(i)"
          :label="t('video.sourcePort')"
          emit-value
          map-options
          use-input
          new-value-mode="add-unique"
          dense
          clearable
          style="min-width: 110px; max-width: 140px"
        />
        <q-select
          v-model="step.input_port"
          :options="inputPortOptions(step)"
          :label="t('video.inputPort')"
          emit-value
          map-options
          use-input
          new-value-mode="add-unique"
          dense
          clearable
          style="min-width: 110px; max-width: 140px"
        />
        <q-select
          v-model="step.connector"
          :options="connectorOptions"
          :label="t('video.colConnector')"
          emit-value
          map-options
          dense
          style="min-width: 110px"
        />
        <q-input
          v-model="step.patch_label"
          :label="t('video.stepLabel')"
          dense
          style="min-width: 110px; max-width: 140px"
        />
        <q-btn
          flat
          dense
          round
          icon="arrow_upward"
          :disable="i === 0"
          :aria-label="t('video.moveUp')"
          @click="move(i, -1)"
        />
        <q-btn
          flat
          dense
          round
          icon="arrow_downward"
          :disable="i === steps.length - 1"
          :aria-label="t('video.moveDown')"
          @click="move(i, 1)"
        />
        <q-btn
          flat
          dense
          round
          icon="delete"
          color="negative"
          :aria-label="t('video.removeStep')"
          @click="removeStep(i)"
        />
      </div>
      <div
        v-if="!steps.length"
        class="text-grey-7"
      >
        {{ t('video.noSteps') }}
      </div>
      <q-btn
        outline
        no-caps
        color="primary"
        icon="add"
        :label="t('video.addStep')"
        @click="addStep"
      />
    </q-card-section>
    <q-dialog v-model="createDialog">
      <q-card style="min-width: 320px">
        <q-card-section class="text-h6">
          {{ t('video.newDevice') }}
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="createName"
            :label="t('devices.name')"
            dense
            autofocus
          />
          <div class="text-caption text-grey-7 q-mt-xs">
            {{ t('devices.type') }}: {{ t(`devices.types.${createKind}`) }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
          />
          <q-btn
            color="primary"
            :label="t('devices.createDevice')"
            :disable="!createName.trim()"
            @click="confirmNewDevice"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useDevicesStore } from '@/stores/devices';
import { VIDEO_DEVICE_KINDS } from '@/constants/videoDevices';

const props = defineProps({
  jobId: { type: String, required: true },
  points: { type: Array, default: () => [] },
  excludeDeviceTypes: { type: Array, default: () => [] },
});

const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const devicesStore = useDevicesStore();

let keySeq = 0;
const steps = ref([]);

const kindOptions = VIDEO_DEVICE_KINDS.filter((v) => !props.excludeDeviceTypes.includes(v)).map((v) => ({
  value: v,
  label: t(`devices.types.${v}`),
}));
const connectorOptions = [
  { value: 'sdi', label: 'SDI' },
  { value: 'hdmi', label: 'HDMI' },
  { value: 'ndi', label: 'NDI' },
  { value: 'fiber', label: 'Fiber' },
  { value: 'other', label: t('video.types.other') },
];

function stepFromPoint(point) {
  const device = devicesStore.byId(point.device_id);
  keySeq += 1;
  return {
    key: `s${keySeq}`,
    kind: device?.device_type || 'other',
    device_id: point.device_id,
    connector: point.connector || '',
    patch_label: point.patch_label || '',
    notes: point.notes || '',
    source_port: point.source_port || '',
    input_port: point.input_port || '',
  };
}

function reset() {
  steps.value = (props.points || []).map(stepFromPoint);
}

watch(() => props.points, reset, { immediate: true });

function addStep() {
  keySeq += 1;
  steps.value = [
    ...steps.value,
    {
      key: `s${keySeq}`,
      kind: 'patchbay',
      device_id: null,
      connector: '',
      patch_label: '',
      notes: '',
      source_port: '',
      input_port: '',
    },
  ];
}
function removeStep(index) {
  steps.value = steps.value.filter((_, i) => i !== index);
}
function move(index, delta) {
  const next = steps.value.slice();
  const target = index + delta;
  [next[index], next[target]] = [next[target], next[index]];
  steps.value = next;
}

// Ports are the device's numbered outputs (the one the signal leaves from) and inputs
// (the one it arrives at). The first step takes from the stage source, not a device.
function portOptions(count, prefix) {
  return Array.from({ length: count || 0 }, (_, n) => ({
    value: `${prefix} ${n + 1}`,
    label: `${prefix} ${n + 1}`,
  }));
}
function sourcePortOptions(index) {
  const previous = steps.value[index - 1];
  const device = previous?.device_id ? devicesStore.byId(previous.device_id) : null;
  return portOptions(device?.output_count, 'OUT');
}
function inputPortOptions(step) {
  const device = step.device_id ? devicesStore.byId(step.device_id) : null;
  return portOptions(device?.input_count, 'IN');
}

function deviceOptionsFor(step) {
  const all = devicesStore.devices
    .filter((d) => !props.excludeDeviceTypes.includes(d.device_type))
    .map((d) => ({
      value: d.id,
      label: `${d.name || '—'} · ${t(`devices.types.${d.device_type}`)}`,
      kind: d.device_type,
    }));
  const sameKind = all.filter((o) => o.kind === step.kind);
  return (sameKind.length ? sameKind : all).map(({ value, label }) => ({ value, label }));
}

const createDialog = ref(false);
const createName = ref('');
const createKind = ref('other');
const createStep = ref(null);
function askNewDevice(step, val, done) {
  done();
  const name = String(val || '').trim();
  if (!name) return;
  createStep.value = step;
  createName.value = name;
  createKind.value = step.kind;
  createDialog.value = true;
}
async function confirmNewDevice() {
  try {
    const device = await devicesStore.createDevice(props.jobId, {
      name: createName.value.trim(),
      device_type: createKind.value,
    });
    if (createStep.value) createStep.value.device_id = device.id;
    createDialog.value = false;
  } catch (err) {
    $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('common.errorOccurred') });
  }
}

function collect() {
  if (steps.value.some((s) => !s.device_id)) {
    $q.notify({ type: 'warning', message: t('video.stepsNeedDevice') });
    return null;
  }
  return steps.value.map((s) => ({
    device_id: s.device_id,
    connector: s.connector || '',
    patch_label: s.patch_label || '',
    notes: s.notes || '',
    source_port: s.source_port || '',
    input_port: s.input_port || '',
  }));
}

defineExpose({ collect });
</script>
