<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('channels.backToJobs')"
        class="q-mr-sm"
        @click="router.push(`/jobs/${jobId}`)"
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
        <div class="row q-gutter-sm items-end q-mt-sm">
          <q-input
            v-model.number="newInputs"
            type="number"
            :label="t('devices.inputs')"
            dense
            class="col"
          />
          <q-input
            v-model.number="newOutputs"
            type="number"
            :label="t('devices.outputs')"
            dense
            class="col"
          />
          <q-input
            v-model="newInConnector"
            :label="t('devices.inputConnector')"
            dense
            class="col"
          />
          <q-input
            v-model="newOutConnector"
            :label="t('devices.outputConnector')"
            dense
            class="col"
          />
        </div>
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
          v-if="device.input_count || device.output_count"
          class="q-mt-sm"
        >
          <div
            v-if="device.input_count"
            class="row items-center q-gutter-sm"
          >
            <div
              class="text-caption text-grey-7"
              style="min-width: 64px"
            >
              {{ t('devices.inputs') }}
            </div>
            <q-linear-progress
              :value="usageIn(device) / device.input_count"
              color="primary"
              class="col"
              style="height: 10px"
            />
            <div class="text-caption">
              {{ usageIn(device) }}/{{ device.input_count }}
            </div>
            <q-badge
              v-if="usageIn(device) >= device.input_count"
              color="negative"
            >
              {{ t('devices.full') }}
            </q-badge>
          </div>
          <div
            v-if="device.output_count"
            class="row items-center q-gutter-sm q-mt-xs"
          >
            <div
              class="text-caption text-grey-7"
              style="min-width: 64px"
            >
              {{ t('devices.outputs') }}
            </div>
            <q-linear-progress
              :value="usageOut(device) / device.output_count"
              color="secondary"
              class="col"
              style="height: 10px"
            />
            <div class="text-caption">
              {{ usageOut(device) }}/{{ device.output_count }}
            </div>
            <q-badge
              v-if="usageOut(device) >= device.output_count"
              color="negative"
            >
              {{ t('devices.full') }}
            </q-badge>
          </div>
          <div class="text-caption text-grey-7 q-mt-xs">
            {{ device.input_connector || '—' }} → {{ device.output_connector || '—' }}
          </div>
        </div>
        <div class="row q-gutter-sm q-mt-sm items-end">
          <q-btn
            dense
            outline
            color="primary"
            :label="t('devices.autoAssign')"
            :loading="autoAssigning === device.id"
            @click="autoAssign(device)"
          >
            <q-tooltip>{{ t('devices.autoAssignHint') }}</q-tooltip>
          </q-btn>
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
                Ch {{ p.channel_number }} · {{ p.name || t('devices.none') }}
                <span class="text-grey-7"> ({{ p.listName }})</span>
              </span>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                dense
                icon="link_off"
                color="negative"
                @click="unassignPoint(p)"
              />
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
          <div class="row q-gutter-sm items-end">
            <q-input
              v-model.number="editForm.input_count"
              type="number"
              :label="t('devices.inputs')"
              dense
              class="col"
            />
            <q-input
              v-model.number="editForm.output_count"
              type="number"
              :label="t('devices.outputs')"
              dense
              class="col"
            />
          </div>
          <div class="row q-gutter-sm items-end">
            <q-input
              v-model="editForm.input_connector"
              :label="t('devices.inputConnector')"
              dense
              class="col"
            />
            <q-input
              v-model="editForm.output_connector"
              :label="t('devices.outputConnector')"
              dense
              class="col"
            />
          </div>
          <q-input
            v-model="editForm.notes"
            :label="t('channels.fieldNotes')"
            dense
            type="textarea"
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

const { t } = useI18n({ useScope: 'global' });
const route = useRoute();
const router = useRouter();
const jobId = route.params.jobId;
const devicesStore = useDevicesStore();

const DEVICE_TYPES = [
  'digital_stagebox',
  'analog_stagebox',
  'mixer',
  'split',
  'network',
  'direct',
  'other',
];
const deviceTypeOptions = DEVICE_TYPES.map((v) => ({
  value: v,
  label: t(`devices.types.${v}`),
}));

const newName = ref('');
const newType = ref('digital_stagebox');
const newInputs = ref(0);
const newOutputs = ref(0);
const newInConnector = ref('');
const newOutConnector = ref('');
const creating = ref(false);
const loading = ref(false);
const autoAssigning = ref(null);
const deleteDialog = ref(false);
const pendingDelete = ref(null);
const editDialog = ref(false);
const editTarget = ref(null);
const editForm = reactive({
  name: '',
  device_type: 'other',
  input_count: 0,
  output_count: 0,
  input_connector: '',
  output_connector: '',
  notes: '',
});
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
          name: p.name || '',
          point_type: p.point_type,
          channel_id: ch.channel_id,
          channel_number: ch.channel_number,
          listName: list.name,
          device_id: p.device_id || null,
          direction: p.direction || null,
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
      label: `Ch ${p.channel_number} · ${p.name || t('devices.none')} (${p.listName})`,
    })),
);

function pointsForDevice(deviceId) {
  return allPoints.value.filter((p) => p.device_id === deviceId);
}
function linkedElementCount(deviceId) {
  return plotElements.value.filter((el) => el.linked_device_id === deviceId).length;
}
function usageIn(device) {
  return pointsForDevice(device.id).filter((p) => p.direction === 'in').length;
}
function usageOut(device) {
  return pointsForDevice(device.id).filter((p) => p.direction === 'out').length;
}
function openEdit(device) {
  editTarget.value = device;
  editForm.name = device.name || '';
  editForm.device_type = device.device_type || 'other';
  editForm.input_count = device.input_count || 0;
  editForm.output_count = device.output_count || 0;
  editForm.input_connector = device.input_connector || '';
  editForm.output_connector = device.output_connector || '';
  editForm.notes = device.notes || '';
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
      input_count: Number(newInputs.value) || 0,
      output_count: Number(newOutputs.value) || 0,
      input_connector: newInConnector.value,
      output_connector: newOutConnector.value,
    });
    newName.value = '';
    newInputs.value = 0;
    newOutputs.value = 0;
    newInConnector.value = '';
    newOutConnector.value = '';
    await refresh();
  } finally {
    creating.value = false;
  }
}

async function autoAssign(device) {
  autoAssigning.value = device.id;
  try {
    const target = (device.name || '').toLowerCase();
    const matches = allPoints.value.filter(
      (p) => (p.name || '').toLowerCase() === target && p.device_id !== device.id,
    );
    for (const p of matches) {
      await devicesStore.assignPatchPoint(jobId, p, device.id);
    }
    await refresh();
  } finally {
    autoAssigning.value = null;
  }
}

async function assignPoint(device, pointId) {
  if (!pointId) return;
  const p = allPoints.value.find((x) => x.id === pointId);
  if (p) await devicesStore.assignPatchPoint(jobId, p, device.id);
  assignPick[device.id] = null;
  await refresh();
}

async function unassignPoint(p) {
  await devicesStore.assignPatchPoint(jobId, p, null);
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

onMounted(refresh);
</script>
