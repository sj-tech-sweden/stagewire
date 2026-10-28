<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('channels.backToJobs')"
        class="q-mr-sm"
        @click="goBackToJob"
      />
      <div class="text-h6">
        {{ t('devices.title') }}
      </div>
    </div>

    <q-card
      flat
      bordered
      class="q-mb-md"
    >
      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">
          {{ t('devices.add') }}
        </div>
        <div class="row q-gutter-sm items-end">
          <q-input
            v-model="newName"
            :label="t('devices.name')"
            dense
            class="col"
            @keyup.enter="createDevice"
          />
          <q-select
            v-model="newType"
            :options="deviceTypeOptions"
            :label="t('devices.type')"
            emit-value
            map-options
            dense
            class="col"
          />
          <q-btn
            color="primary"
            :label="t('devices.createDevice')"
            :disable="!newName.trim()"
            :loading="creating"
            @click="createDevice"
          />
        </div>
        <div class="text-caption q-mt-sm">
          {{ t('devices.ports') }}
        </div>
        <div
          v-for="(port, idx) in newPorts"
          :key="idx"
          class="row q-gutter-xs items-end q-mt-xs"
        >
          <q-select
            v-model="port.direction"
            :options="directionOptions"
            emit-value
            map-options
            dense
            :label="t('devices.direction')"
            class="col-3"
          />
          <q-select
            v-model="port.connector"
            :options="connectorOptions"
            :label="t('channels.patchPoint.connector')"
            dense
            clearable
            class="col"
          />
          <q-input
            v-model.number="port.count"
            type="number"
            :label="t('devices.count')"
            dense
            class="col-3"
          />
          <q-btn
            flat
            dense
            round
            icon="delete"
            color="negative"
            @click="newPorts.splice(idx, 1)"
          />
        </div>
        <q-btn
          dense
          flat
          icon="add"
          class="q-mt-xs"
          :label="t('devices.addPort')"
          @click="newPorts.push({ direction: 'in', connector: '', count: 1 })"
        />
      </q-card-section>
    </q-card>

    <div
      v-if="loading"
      class="q-my-md"
    >
      <q-spinner color="primary" />
    </div>
    <div
      v-else-if="!devicesStore.devices.length"
      class="text-grey-7 q-pa-md text-center"
    >
      {{ t('devices.noDevices') }}
    </div>

    <q-card
      v-for="device in devicesStore.devices"
      :key="device.id"
      flat
      bordered
      class="q-mb-md"
    >
      <q-card-section>
        <div class="row items-center">
          <div class="col">
            <div class="text-subtitle1">
              {{ device.name || '—' }}
            </div>
            <q-badge
              color="primary"
              class="q-mt-xs"
            >
              {{ t(`devices.types.${device.device_type}`) }}
            </q-badge>
          </div>
          <q-btn
            flat
            dense
            round
            icon="delete"
            color="negative"
            class="q-ml-sm"
            @click="confirmDelete(device)"
          />
          <q-btn
            flat
            dense
            round
            icon="edit"
            class="q-ml-sm"
            :aria-label="t('app.actions.edit')"
            @click="openEdit(device)"
          />
        </div>
        <div class="row q-gutter-md q-mt-sm text-caption text-grey-7">
          <div>
            {{ t('devices.patchPoints') }}: <b>{{ device.patch_point_count }}</b>
          </div>
          <div>
            {{ t('devices.linkedElements') }}: <b>{{ linkedElementCount(device.id) }}</b>
          </div>
        </div>
        <div
          v-if="(device.ports || []).length"
          class="q-mt-sm"
        >
          <div
            v-for="(port, idx) in device.ports"
            :key="idx"
            class="row items-center q-gutter-sm q-mt-xs"
          >
            <div
              class="text-caption"
              style="min-width: 96px"
            >
              {{ port.direction === 'out' ? t('devices.directionOut') : t('devices.directionIn') }}
              · {{ port.connector || '—' }}
            </div>
            <q-linear-progress
              :value="portUsage(device, port) / (port.count || 1)"
              :color="port.direction === 'out' ? 'secondary' : 'primary'"
              class="col"
              style="height: 10px"
            />
            <div class="text-caption">
              {{ portUsage(device, port) }}/{{ port.count }}
            </div>
            <q-badge
              v-if="portUsage(device, port) >= (port.count || 0)"
              color="negative"
            >
              {{ t('devices.full') }}
            </q-badge>
          </div>
        </div>
        <div class="row q-gutter-sm q-mt-sm items-end">
          <q-select
            v-model="assignPick[device.id]"
            :options="unassignedOptions"
            :label="t('devices.assignPoint')"
            emit-value
            map-options
            dense
            clearable
            class="col"
            @update:model-value="(val) => assignPoint(device, val)"
          />
        </div>

        <q-list
          v-if="pointsForDevice(device.id).length"
          dense
          separator
          class="q-mt-sm"
        >
          <q-item
            v-for="p in pointsForDevice(device.id)"
            :key="p.id"
          >
            <q-item-section>
              <span>
                Ch {{ p.channel_number }} · {{ p.listName }}
                <span class="text-grey-7"> ({{ p.listName }})</span>
              </span>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
    </q-card>

    <q-dialog v-model="deleteDialog">
      <q-card>
        <q-card-section>
          {{ t('devices.deleteConfirm') }}
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
          />
          <q-btn
            flat
            color="negative"
            :label="t('app.actions.delete')"
            @click="doDelete"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 320px; max-width: 520px">
        <q-card-section class="text-h6">
          {{ t('devices.editDevice') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model="editForm.name"
            :label="t('devices.name')"
            dense
          />
          <q-select
            v-model="editForm.device_type"
            :options="deviceTypeOptions"
            :label="t('devices.type')"
            emit-value
            map-options
            dense
          />
          <div
            v-if="ioDeviceTypes.includes(editForm.device_type)"
            class="q-gutter-sm"
          >
            <div class="text-caption">
              {{ t('devices.ioHint') }}
            </div>
            <div
              v-if="(editTarget?.stockwire_connectors || []).length"
              class="text-caption"
            >
              {{ t('devices.stockwireConnectors', { list: editTarget.stockwire_connectors.join(', ') }) }}
            </div>
            <div class="row q-gutter-sm">
              <q-input
                v-model.number="editForm.input_override"
                type="number"
                min="0"
                clearable
                dense
                class="col"
                :label="t('devices.inputs')"
                :hint="ioSourceHint(editTarget, 'input')"
              />
              <q-input
                v-model.number="editForm.output_override"
                type="number"
                min="0"
                clearable
                dense
                class="col"
                :label="t('devices.outputs')"
                :hint="ioSourceHint(editTarget, 'output')"
              />
            </div>
          </div>
          <div
            v-if="['camera', 'lens'].includes(editForm.device_type)"
            class="q-gutter-sm"
          >
            <div class="text-caption">
              {{ t('devices.cameraHint') }}
            </div>
            <div
              v-if="editTarget?.stockwire_product_id"
              class="text-caption"
            >
              {{ t('devices.cameraStockwireHint') }}
            </div>
            <template v-if="editForm.device_type === 'camera'">
              <q-select
                v-model="sensorPreset"
                :options="sensorPresetOptions"
                :label="t('devices.sensorPreset')"
                emit-value
                map-options
                clearable
                dense
                @update:model-value="applySensorPreset"
              />
              <div class="row q-gutter-sm">
                <q-input
                  v-model="sensorAspect"
                  :label="t('devices.sensorAspect')"
                  :hint="t('devices.sensorAspectHint')"
                  dense
                  class="col"
                />
                <q-input
                  v-model="sensorDiagonal"
                  :label="t('devices.sensorDiagonal')"
                  :hint="t('devices.sensorDiagonalHint')"
                  dense
                  class="col"
                />
                <q-select
                  :model-value="sensorDiagonalUnit"
                  :options="sensorUnitOptions"
                  emit-value
                  map-options
                  dense
                  class="col-3"
                  @update:model-value="convertSensorDiagonal"
                />
              </div>
              <div class="row items-center q-gutter-sm">
                <div class="col text-caption">
                  {{ sensorCalcText }}
                </div>
                <q-btn
                  v-if="calculatedSensorWidth"
                  flat
                  dense
                  color="primary"
                  :label="t('devices.useCalculatedWidth')"
                  @click="useCalculatedSensorWidth"
                />
              </div>
            </template>
            <q-input
              v-if="editForm.device_type === 'camera'"
              v-model.number="editForm.sensor_width_mm"
              type="number"
              min="0"
              step="0.1"
              clearable
              dense
              :label="t('devices.sensorWidth')"
            />
            <div class="row q-gutter-sm">
              <q-input
                v-model.number="editForm.focal_min_mm"
                type="number"
                min="0"
                step="0.1"
                clearable
                dense
                class="col"
                :label="t('devices.focalMin')"
              />
              <q-input
                v-model.number="editForm.focal_max_mm"
                type="number"
                min="0"
                step="0.1"
                clearable
                dense
                class="col"
                :label="t('devices.focalMax')"
              />
            </div>
            <q-input
              v-if="editForm.device_type === 'camera'"
              v-model.number="editForm.max_distance_m"
              type="number"
              min="0"
              step="0.5"
              clearable
              dense
              :label="t('devices.maxDistance')"
              :hint="t('devices.maxDistanceHint')"
            />
          </div>
          <div class="text-caption q-mt-sm">
            {{ t('devices.ports') }}
          </div>
          <div
            v-for="(port, idx) in editForm.ports"
            :key="idx"
            class="row q-gutter-xs items-end q-mt-xs"
          >
            <q-select
              v-model="port.direction"
              :options="directionOptions"
              emit-value
              map-options
              dense
              :label="t('devices.direction')"
              class="col-3"
            />
            <q-select
              v-model="port.connector"
              :options="connectorOptions"
              :label="t('channels.patchPoint.connector')"
              dense
              clearable
              class="col"
            />
            <q-input
              v-model.number="port.count"
              type="number"
              :label="t('devices.count')"
              dense
              class="col-3"
            />
            <q-btn
              flat
              dense
              round
              icon="delete"
              color="negative"
              @click="editForm.ports.splice(idx, 1)"
            />
          </div>
          <q-btn
            dense
            flat
            icon="add"
            class="q-mt-xs"
            :label="t('devices.addPort')"
            @click="editForm.ports.push({ direction: 'in', connector: '', count: 1 })"
          />
          <q-input
            v-model="editForm.notes"
            :label="t('channels.fieldNotes')"
            dense
            type="textarea"
            class="q-mt-sm"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
          />
          <q-btn
            flat
            color="primary"
            :label="t('app.actions.save')"
            @click="saveEdit"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { api } from '@/boot/api';
import { useDevicesStore } from '@/stores/devices';
import { CONNECTOR_OPTIONS } from '@/constants/connectors';
import {
  SENSOR_PRESETS,
  diagonalToMm,
  findPreset,
  mmToDiagonal,
  parseAspect,
  parseLength,
  sensorDiagonalMm,
  sensorWidthFromDiagonal,
} from '@/utils/sensor';

const connectorOptions = CONNECTOR_OPTIONS;

const { t } = useI18n({ useScope: 'global' });
const route = useRoute();
const router = useRouter();

function goBackToJob() {
  router.push({
    path: `/jobs/${jobId}`,
    query: route.query.from === 'video' ? { view: 'video' } : {},
  });
}
const jobId = route.params.jobId;
const devicesStore = useDevicesStore();

const DEVICE_TYPES = [
  'digital_stagebox',
  'analog_stagebox',
  'mixer',
  'split',
  'network',
  'direct',
  'switcher',
  'router',
  'multiviewer',
  'camera',
  'lens',
  'ptz_camera',
  'computer',
  'patchbay',
  'converter',
  'encoder',
  'recorder',
  'screen',
  'projector',
  'other',
];
const ioDeviceTypes = ['mixer', 'switcher', 'router', 'multiviewer'];
function ioSourceHint(device, side) {
  const source = side === 'input' ? device?.input_source : device?.output_source;
  const count = side === 'input' ? device?.input_default : device?.output_default;
  const stockwire = side === 'input' ? device?.stockwire_inputs : device?.stockwire_outputs;
  if (source === 'override') return t('devices.ioOverridden');
  if (source === 'stockwire') return t('devices.ioStockwire', { n: stockwire });
  if (source === 'patch') return t('devices.ioDefault', { n: count ?? 0 });
  return t('devices.ioUnset');
}
const deviceTypeOptions = DEVICE_TYPES.map((v) => ({
  value: v,
  label: t(`devices.types.${v}`),
}));

const newName = ref('');
const newType = ref('digital_stagebox');
const newPorts = ref([]);
const creating = ref(false);
const loading = ref(false);
const deleteDialog = ref(false);
const pendingDelete = ref(null);
const editDialog = ref(false);
const editTarget = ref(null);
const editForm = reactive({
  name: '',
  device_type: 'other',
  ports: [],
  notes: '',
  input_override: null,
  output_override: null,
  sensor_width_mm: null,
  focal_min_mm: null,
  focal_max_mm: null,
  max_distance_m: null,
});
const directionOptions = [
  { value: 'in', label: t('devices.directionIn') },
  { value: 'out', label: t('devices.directionOut') },
];
const assignPick = reactive({});
const lists = ref([]);
const plotElements = ref([]);

const allPoints = computed(() => {
  const pts = [];
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        pts.push({
          id: p.id,
          point_type: p.point_type,
          channel_id: ch.id,
          channel_number: ch.channel_number,
          listName: list.name,
          device_id: p.device_id || null,
          connector: p.connector || '',
          position: p.position,
        });
      }
    }
  }
  return pts;
});
const unassignedOptions = computed(() =>
  allPoints.value
    .filter((p) => !p.device_id)
    .map((p) => ({
      value: p.id,
      label: `Ch ${p.channel_number} · ${p.listName}`,
    })),
);

function pointsForDevice(deviceId) {
  return allPoints.value.filter((p) => p.device_id === deviceId);
}
function linkedElementCount(deviceId) {
  return plotElements.value.filter((el) => el.linked_device_id === deviceId).length;
}

// Derive each patch point's in/out direction from its position in the channel's
// signal chain: the device's connector closest to the source is an input, the
// one closest to the destination is an output.
function deviceUsedMap(deviceId) {
  const used = {};
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      const cps = (ch.patch_points || []).slice().sort((a, b) => a.position - b.position);
      if (!cps.length) continue;
      const startPos = cps[0].position;
      const endPos = cps[cps.length - 1].position;
      const devPoints = cps.filter((p) => (p.device_id || null) === deviceId);
      if (!devPoints.length) continue;
      const devMin = devPoints[0].position;
      const devMax = devPoints[devPoints.length - 1].position;
      const isInputSide = devMin === startPos;
      const isOutputSide = devMax === endPos;
      for (const p of devPoints) {
        let dir;
        if (isInputSide && !isOutputSide) dir = 'in';
        else if (isOutputSide && !isInputSide) dir = 'out';
        else if (p.position === devMin) dir = 'in';
        else if (p.position === devMax) dir = 'out';
        else dir = 'in';
        const conn = (p.connector || '').toLowerCase();
        const key = `${dir}|${conn}`;
        used[key] = (used[key] || 0) + 1;
      }
    }
  }
  return used;
}
const usedByDevice = computed(() => {
  const result = {};
  for (const device of devicesStore.devices) {
    result[device.id] = deviceUsedMap(device.id);
  }
  return result;
});
function portUsage(device, port) {
  const used = usedByDevice.value[device.id] || {};
  const key = `${port.direction}|${(port.connector || '').toLowerCase()}`;
  return used[key] || 0;
}
const sensorPreset = ref(null);
const sensorAspect = ref('');
const sensorDiagonal = ref('');
const sensorDiagonalUnit = ref('mm');
const sensorPresetOptions = SENSOR_PRESETS.map((p) => ({ value: p.id, label: `${p.label} · ${p.width} × ${p.height} mm` }));
const sensorUnitOptions = [
  { value: 'mm', label: 'mm' },
  { value: 'in', label: 'in' },
];
const calculatedSensorWidth = computed(() => {
  const diagonal = parseLength(sensorDiagonal.value);
  const aspect = parseAspect(sensorAspect.value);
  if (!diagonal || !aspect) return null;
  return sensorWidthFromDiagonal(diagonalToMm(diagonal, sensorDiagonalUnit.value), aspect);
});
const sensorCalcText = computed(() =>
  calculatedSensorWidth.value
    ? t('devices.sensorCalculated', { mm: calculatedSensorWidth.value.toFixed(2) })
    : t('devices.sensorCalcHint'),
);
function formatDiagonal(mm, unit) {
  const digits = unit === 'in' ? 10000 : 100;
  return String(Math.round(mmToDiagonal(mm, unit) * digits) / digits);
}
function applySensorPreset(id) {
  const preset = findPreset(id);
  if (!preset) return;
  editForm.sensor_width_mm = preset.width;
  sensorAspect.value = preset.aspect;
  sensorDiagonal.value = formatDiagonal(sensorDiagonalMm(preset.width, preset.height), sensorDiagonalUnit.value);
}
function convertSensorDiagonal(unit) {
  const diagonal = parseLength(sensorDiagonal.value);
  if (diagonal) {
    sensorDiagonal.value = formatDiagonal(diagonalToMm(diagonal, sensorDiagonalUnit.value), unit);
  }
  sensorDiagonalUnit.value = unit;
}
function useCalculatedSensorWidth() {
  if (calculatedSensorWidth.value) {
    editForm.sensor_width_mm = Math.round(calculatedSensorWidth.value * 100) / 100;
  }
}
function openEdit(device) {
  sensorPreset.value = null;
  sensorAspect.value = '';
  sensorDiagonal.value = '';
  sensorDiagonalUnit.value = 'mm';
  editTarget.value = device;
  editForm.name = device.name || '';
  editForm.device_type = device.device_type || 'other';
  editForm.ports = (device.ports || []).map((p) => ({
    direction: p.direction || 'in',
    connector: p.connector || '',
    count: p.count || 0,
  }));
  editForm.notes = device.notes || '';
  editForm.input_override = device.input_override ?? null;
  editForm.output_override = device.output_override ?? null;
  editForm.sensor_width_mm = device.sensor_width_mm ?? null;
  editForm.focal_min_mm = device.focal_min_mm ?? null;
  editForm.focal_max_mm = device.focal_max_mm ?? null;
  editForm.max_distance_m = device.max_distance_m ?? null;
  editDialog.value = true;
}
async function saveEdit() {
  if (!editTarget.value) return;
  await devicesStore.updateDevice(jobId, editTarget.value.id, { ...editForm });
  editDialog.value = false;
  editTarget.value = null;
  await refresh();
}

async function loadLists() {
  const { data } = await api.get(`/jobs/${jobId}/channel-lists`);
  lists.value = data || [];
}
async function loadPlot() {
  const { data } = await api.get(`/jobs/${jobId}/plot-elements`);
  plotElements.value = data || [];
}
async function refresh() {
  loading.value = true;
  try {
    await Promise.all([
      devicesStore.fetchDevices(jobId),
      loadLists(),
      loadPlot(),
    ]);
  } finally {
    loading.value = false;
  }
}

async function createDevice() {
  if (!newName.value.trim()) return;
  creating.value = true;
  try {
    await devicesStore.createDevice(jobId, {
      name: newName.value.trim(),
      device_type: newType.value,
      ports: newPorts.value.map((p) => ({
        direction: p.direction || 'in',
        connector: p.connector || '',
        count: Number(p.count) || 0,
      })),
    });
    newName.value = '';
    newPorts.value = [];
    await refresh();
  } finally {
    creating.value = false;
  }
}

async function assignPoint(device, pointId) {
  if (!pointId) return;
  const p = allPoints.value.find((x) => x.id === pointId);
  if (p) await devicesStore.assignPatchPoint(jobId, p, device.id);
  assignPick[device.id] = null;
  await refresh();
}

function confirmDelete(device) {
  pendingDelete.value = device;
  deleteDialog.value = true;
}
async function doDelete() {
  if (pendingDelete.value) {
    await devicesStore.deleteDevice(jobId, pendingDelete.value.id);
    await refresh();
  }
  deleteDialog.value = false;
  pendingDelete.value = null;
}

onMounted(async () => {
  await refresh();
  const deviceId = route.query.device;
  const device = deviceId && devicesStore.devices.find((d) => d.id === deviceId);
  if (device) openEdit(device);
});
</script>
