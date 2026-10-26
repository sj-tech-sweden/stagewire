<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('video.back')"
        class="q-mr-sm"
        @click="router.push(`/jobs/${jobId}`)"
      />
      <div class="col">
        <div class="text-h6">
          {{ t('video.title') }}
        </div>
        <div class="text-caption text-grey-7">
          {{ t('video.hint') }}
        </div>
      </div>
    </div>

    <q-card
      flat
      bordered
      class="q-mb-md"
    >
      <q-card-section class="row items-end q-gutter-sm">
        <q-input
          v-model="newListName"
          :label="t('video.newListName')"
          dense
          class="col"
          @keyup.enter="addList"
        />
        <q-btn
          color="primary"
          icon="add"
          :label="t('video.addList')"
          :disable="!newListName.trim()"
          @click="addList"
        />
      </q-card-section>
    </q-card>

    <div
      v-if="!store.lists.length && !store.loading"
      class="text-grey-7"
    >
      {{ t('video.empty') }}
    </div>

    <q-card
      v-for="list in store.lists"
      :key="list.id"
      flat
      bordered
      class="q-mb-md"
    >
      <q-card-section class="row items-center q-gutter-sm">
        <q-input
          :model-value="list.name"
          dense
          borderless
          class="text-h6 col"
          :aria-label="t('video.listName')"
          @change="(v) => renameList(list, v)"
        />
        <q-btn
          outline
          no-caps
          color="primary"
          icon="add"
          :label="t('video.addInput')"
          @click="addInput(list)"
        />
        <q-btn
          flat
          round
          icon="delete"
          color="negative"
          :aria-label="t('video.deleteList')"
          @click="removeList(list)"
        />
      </q-card-section>

      <q-markup-table
        v-if="(list.inputs || []).length"
        flat
        dense
        separator="cell"
      >
        <thead>
          <tr>
            <th
              class="text-left"
              style="width: 64px"
            >
              {{ t('video.colNumber') }}
            </th>
            <th class="text-left">
              {{ t('video.colSource') }}
            </th>
            <th
              class="text-left"
              style="width: 150px"
            >
              {{ t('video.colType') }}
            </th>
            <th
              class="text-left"
              style="width: 130px"
            >
              {{ t('video.colConnector') }}
            </th>
            <th
              class="text-left"
              style="width: 220px"
            >
              {{ t('video.colDevice') }}
            </th>
            <th class="text-left">
              {{ t('video.colChain') }}
            </th>
            <th style="width: 48px" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="input in list.inputs"
            :key="input.id"
          >
            <td>{{ input.input_number }}</td>
            <td>
              <q-input
                :model-value="input.source_label"
                dense
                borderless
                :placeholder="t('video.sourcePlaceholder')"
                @change="(v) => saveInput(input, { source_label: v })"
              />
            </td>
            <td>
              <q-select
                :model-value="input.source_type"
                :options="typeOptions"
                dense
                borderless
                emit-value
                map-options
                @update:model-value="(v) => saveInput(input, { source_type: v })"
              />
            </td>
            <td>
              <q-select
                :model-value="input.connector"
                :options="connectorOptions"
                dense
                borderless
                emit-value
                map-options
                @update:model-value="(v) => saveInput(input, { connector: v })"
              />
            </td>
            <td>
              <q-select
                :model-value="firstDeviceId(input)"
                :options="deviceOptions"
                dense
                borderless
                emit-value
                map-options
                clearable
                :placeholder="t('video.pickDevice')"
                @update:model-value="(v) => setFirstDevice(input, v)"
              />
              <div
                v-if="deviceConnectors(input).length"
                class="text-caption text-grey-7"
              >
                {{ deviceConnectors(input).join(' · ') }}
              </div>
            </td>
            <td>
              <div class="row items-center q-gutter-xs">
                <q-chip
                  v-for="point in chainPoints(input)"
                  :key="point.id"
                  dense
                  removable
                  color="grey-9"
                  text-color="white"
                  :label="deviceName(point.device_id)"
                  @remove="removePoint(input, point)"
                />
                <q-btn
                  v-if="firstDeviceId(input)"
                  flat
                  dense
                  icon="add"
                  :label="t('video.addStage')"
                  @click="openChain(input)"
                />
              </div>
            </td>
            <td>
              <q-btn
                flat
                dense
                round
                icon="delete"
                color="negative"
                :aria-label="t('video.deleteInput')"
                @click="removeInput(input)"
              />
            </td>
          </tr>
        </tbody>
      </q-markup-table>
      <q-card-section
        v-else
        class="text-grey-7"
      >
        {{ t('video.noInputs') }}
      </q-card-section>
    </q-card>

    <q-dialog v-model="chainDialog">
      <q-card style="min-width: 360px">
        <q-card-section class="text-h6">
          {{ t('video.addStage') }}
        </q-card-section>
        <q-card-section>
          <q-select
            v-model="chainDevice"
            :options="deviceOptions"
            :label="t('video.pickDevice')"
            emit-value
            map-options
            dense
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
          />
          <q-btn
            color="primary"
            :label="t('app.actions.add')"
            :disable="!chainDevice"
            @click="addChainPoint"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { useQuasar } from 'quasar';
import { useVideoStore } from '@/stores/video';
import { useDevicesStore } from '@/stores/devices';

const { t } = useI18n({ useScope: 'global' });
const route = useRoute();
const router = useRouter();
const $q = useQuasar();
const store = useVideoStore();
const devicesStore = useDevicesStore();
const jobId = route.params.jobId;

const newListName = ref('');
const chainDialog = ref(false);
const chainInput = ref(null);
const chainDevice = ref(null);

const typeOptions = [
  { value: 'camera', label: t('video.types.camera') },
  { value: 'ptz', label: t('video.types.ptz') },
  { value: 'graphics', label: t('video.types.graphics') },
  { value: 'playback', label: t('video.types.playback') },
  { value: 'other', label: t('video.types.other') },
];
const connectorOptions = [
  { value: 'sdi', label: 'SDI' },
  { value: 'hdmi', label: 'HDMI' },
  { value: 'ndi', label: 'NDI' },
  { value: 'fiber', label: 'Fiber' },
  { value: 'other', label: t('video.types.other') },
];

const deviceOptions = computed(() =>
  devicesStore.devices.map((d) => ({ value: d.id, label: d.name || '—' })),
);

function deviceName(id) {
  return devicesStore.byId(id)?.name || '—';
}
function firstDeviceId(input) {
  return (input.patch_points || [])[0]?.device_id || null;
}
function deviceConnectors(input) {
  return devicesStore.byId(firstDeviceId(input))?.stockwire_connectors || [];
}
function chainPoints(input) {
  return (input.patch_points || []).slice(1);
}

async function run(fn) {
  try {
    await fn();
  } catch (err) {
    $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('common.errorOccurred') });
  }
}

function addList() {
  const name = newListName.value.trim();
  if (!name) return;
  run(async () => {
    await store.createList(jobId, name);
    newListName.value = '';
  });
}
function renameList(list, value) {
  const name = String(value || '').trim();
  if (!name || name === list.name) return;
  run(() => store.updateList(jobId, list.id, { name }));
}
function removeList(list) {
  $q.dialog({
    title: t('video.deleteList'),
    message: t('video.deleteListConfirm', { name: list.name }),
    cancel: true,
    persistent: true,
  }).onOk(() => run(() => store.deleteList(jobId, list.id)));
}
function addInput(list) {
  run(() => store.createInput(jobId, list.id, { source_type: 'camera', connector: 'sdi' }));
}
function saveInput(input, payload) {
  run(() => store.updateInput(jobId, input.id, payload));
}
function removeInput(input) {
  run(() => store.deleteInput(jobId, input.id));
}
function setFirstDevice(input, deviceId) {
  run(async () => {
    const first = (input.patch_points || [])[0];
    if (!deviceId) {
      if (first) await store.deletePatchPoint(jobId, input.id, first.id);
      return;
    }
    if (first) {
      await store.updatePatchPoint(jobId, input.id, first.id, { device_id: deviceId });
    } else {
      await store.createPatchPoint(jobId, input.id, { position: 0, device_id: deviceId });
    }
  });
}
function openChain(input) {
  chainInput.value = input;
  chainDevice.value = null;
  chainDialog.value = true;
}
function addChainPoint() {
  const input = chainInput.value;
  if (!input || !chainDevice.value) return;
  run(async () => {
    await store.createPatchPoint(jobId, input.id, {
      position: (input.patch_points || []).length,
      device_id: chainDevice.value,
    });
    chainDialog.value = false;
  });
}
function removePoint(input, point) {
  run(() => store.deletePatchPoint(jobId, input.id, point.id));
}

onMounted(() => {
  devicesStore.fetchDevices(jobId);
  store.fetchLists(jobId);
});
</script>
