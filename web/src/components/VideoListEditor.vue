<template>
  <div>
    <q-card
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
          @change="(v) => renameList(v)"
        />
        <q-btn
          outline
          no-caps
          color="primary"
          icon="playlist_add"
          :label="t('video.bulkInputs')"
          @click="openBulkInputs"
        />
        <q-btn
          outline
          no-caps
          color="primary"
          icon="playlist_add"
          :label="t('video.bulkOutputs')"
          @click="openBulkOutputs"
        />
        <q-btn
          outline
          no-caps
          color="primary"
          icon="memory"
          :label="list.switcher_product_name || t('video.pickSwitcher')"
          @click="openSwitcher"
        />
        <q-btn
          flat
          round
          icon="delete"
          color="negative"
          :aria-label="t('video.deleteList')"
          @click="removeList"
        />
      </q-card-section>
      <q-card-section
        v-if="list.switcher_product_name"
        class="q-pt-none text-caption text-grey-7"
      >
        {{ t('video.switcherSummary', { name: list.switcher_product_name, inputs: list.switcher_inputs ?? '–', outputs: list.switcher_outputs ?? '–' }) }}
      </q-card-section>
    </q-card>

    <q-card
      flat
      bordered
      class="q-mb-md"
    >
      <q-card-section class="text-subtitle1">
        {{ t('video.inputsTitle') }}
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
                use-input
                hide-selected
                fill-input
                input-debounce="0"
                @new-value="(val, done) => onNewDevice('first', 'input', input, val, done)"
                @update:model-value="(v) => setFirstDevice('input', input, v)"
              />
              <div
                v-if="deviceConnectors(input).length"
                class="text-caption text-grey-7"
              >
                {{ deviceConnectors(input).join(' · ') }}
              </div>
            </td>
            <td>
              <PatchChain
                :points="input.patch_points"
                :can-add="!!firstDeviceId(input)"
                :device-name="deviceName"
                @add="openChain('input', input)"
                @remove="(point) => removePoint('input', input, point)"
              />
            </td>
            <td class="text-no-wrap">
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('channels.signalFlow')"
                @click="openFlow('input', input)"
              />
              <q-btn
                flat
                dense
                round
                icon="edit"
                :aria-label="t('video.editInput')"
                @click="openEdit('input', input)"
              />
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

    <q-card
      flat
      bordered
      class="q-mb-md"
    >
      <q-card-section class="text-subtitle1">
        {{ t('video.outputsTitle') }}
      </q-card-section>
      <q-markup-table
        v-if="(list.outputs || []).length"
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
              {{ t('video.colOutputName') }}
            </th>
            <th class="text-left">
              {{ t('video.colDestination') }}
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
            v-for="output in list.outputs"
            :key="output.id"
          >
            <td>{{ output.output_number }}</td>
            <td>
              <q-input
                :model-value="output.name"
                dense
                borderless
                :placeholder="t('video.outputPlaceholder')"
                @change="(v) => saveOutput(output, { name: v })"
              />
            </td>
            <td>
              <q-input
                :model-value="output.destination_label"
                dense
                borderless
                :placeholder="t('video.destinationPlaceholder')"
                @change="(v) => saveOutput(output, { destination_label: v })"
              />
            </td>
            <td>
              <q-select
                :model-value="output.connector"
                :options="connectorOptions"
                dense
                borderless
                emit-value
                map-options
                @update:model-value="(v) => saveOutput(output, { connector: v })"
              />
            </td>
            <td>
              <q-select
                :model-value="firstDeviceId(output)"
                :options="deviceOptions"
                dense
                borderless
                emit-value
                map-options
                clearable
                :placeholder="t('video.pickDevice')"
                use-input
                hide-selected
                fill-input
                input-debounce="0"
                @new-value="(val, done) => onNewDevice('first', 'output', output, val, done)"
                @update:model-value="(v) => setFirstDevice('output', output, v)"
              />
            </td>
            <td>
              <PatchChain
                :points="output.patch_points"
                :can-add="!!firstDeviceId(output)"
                :device-name="deviceName"
                @add="openChain('output', output)"
                @remove="(point) => removePoint('output', output, point)"
              />
            </td>
            <td class="text-no-wrap">
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('channels.signalFlow')"
                @click="openFlow('output', output)"
              />
              <q-btn
                flat
                dense
                round
                icon="edit"
                :aria-label="t('video.editOutput')"
                @click="openEdit('output', output)"
              />
              <q-btn
                flat
                dense
                round
                icon="delete"
                color="negative"
                :aria-label="t('video.deleteOutput')"
                @click="removeOutput(output)"
              />
            </td>
          </tr>
        </tbody>
      </q-markup-table>
      <q-card-section
        v-else
        class="text-grey-7"
      >
        {{ t('video.noOutputs') }}
      </q-card-section>
    </q-card>

    <q-dialog v-model="bulkInputDialog">
      <q-card style="min-width: 380px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('video.bulkInputs') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="bulkIn.quantity"
              type="number"
              :label="t('video.bulkQuantity')"
              style="width: 110px"
            />
            <q-input
              v-model.number="bulkIn.start_number"
              type="number"
              :label="t('video.bulkStart')"
              style="width: 110px"
            />
            <q-input
              v-model="bulkIn.prefix"
              :label="t('video.bulkPrefix')"
              class="col"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-select
              v-model="bulkIn.source_type"
              :options="typeOptions"
              :label="t('video.bulkType')"
              emit-value
              map-options
              class="col"
            />
            <q-select
              v-model="bulkIn.connector"
              :options="connectorOptions"
              :label="t('video.bulkConnector')"
              emit-value
              map-options
              class="col"
            />
          </div>
          <q-select
            v-model="bulkIn.device_id"
            :options="deviceOptions"
            :label="t('video.bulkDevice')"
            :hint="t('video.bulkDeviceHint')"
            emit-value
            map-options
            clearable
          />
          <div class="text-caption text-grey-7">
            {{ t('video.bulkHint', { count: Math.max(0, Number(bulkIn.quantity) || 0) }) }}
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
            :label="t('app.actions.add')"
            :disable="!(Number(bulkIn.quantity) > 0)"
            :loading="bulkBusy"
            @click="saveBulkInputs"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="bulkOutputDialog">
      <q-card style="min-width: 380px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('video.bulkOutputs') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="bulkOut.quantity"
              type="number"
              :label="t('video.bulkQuantity')"
              style="width: 110px"
            />
            <q-input
              v-model.number="bulkOut.start_number"
              type="number"
              :label="t('video.bulkStart')"
              style="width: 110px"
            />
            <q-input
              v-model="bulkOut.prefix"
              :label="t('video.bulkPrefix')"
              class="col"
            />
          </div>
          <q-select
            v-model="bulkOut.connector"
            :options="connectorOptions"
            :label="t('video.bulkConnector')"
            emit-value
            map-options
          />
          <q-select
            v-model="bulkOut.device_id"
            :options="deviceOptions"
            :label="t('video.bulkDevice')"
            :hint="t('video.bulkDeviceHint')"
            emit-value
            map-options
            clearable
          />
          <div class="text-caption text-grey-7">
            {{ t('video.bulkHint', { count: Math.max(0, Number(bulkOut.quantity) || 0) }) }}
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
            :label="t('app.actions.add')"
            :disable="!(Number(bulkOut.quantity) > 0)"
            :loading="bulkBusy"
            @click="saveBulkOutputs"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="switcherDialog">
      <q-card style="min-width: 380px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('video.switcherTitle') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <StockwireProductPicker
            :model-value="switcherProduct"
            gear-type="switcher"
            :label="t('video.pickSwitcher')"
            :hint="switcherProduct?.sku || ''"
            @update:model-value="(v) => chooseSwitcher(v)"
          />
          <div
            v-if="switcherNote"
            class="text-caption text-grey-7"
          >
            {{ switcherNote }}
          </div>
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="switcherIn"
              type="number"
              :label="t('video.switcherInputs')"
              class="col"
            />
            <q-input
              v-model.number="switcherOut"
              type="number"
              :label="t('video.switcherOutputs')"
              class="col"
            />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            flat
            color="negative"
            :label="t('video.switcherClear')"
            :disable="!list.switcher_product_id"
            @click="clearSwitcher"
          />
          <q-space />
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
          />
          <q-btn
            color="primary"
            :label="t('app.actions.save')"
            @click="saveSwitcher"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ editKind === 'input' ? t('video.editInput') : t('video.editOutput') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="editDraft.number"
              type="number"
              :label="t('video.colNumber')"
              style="width: 100px"
            />
            <q-input
              v-if="editKind === 'input'"
              v-model="editDraft.label"
              :label="t('video.colSource')"
              class="col"
            />
            <q-input
              v-else
              v-model="editDraft.label"
              :label="t('video.colOutputName')"
              class="col"
            />
          </div>
          <q-input
            v-if="editKind === 'output'"
            v-model="editDraft.destination"
            :label="t('video.colDestination')"
          />
          <div class="row q-gutter-sm">
            <q-select
              v-if="editKind === 'input'"
              v-model="editDraft.source_type"
              :options="typeOptions"
              :label="t('video.colType')"
              emit-value
              map-options
              class="col"
            />
            <q-select
              v-model="editDraft.connector"
              :options="connectorOptions"
              :label="t('video.colConnector')"
              emit-value
              map-options
              class="col"
            />
          </div>
          <div>
            <div class="text-subtitle2 q-mb-xs">
              {{ t('video.patchFlow') }}
            </div>
            <PatchFlowEditor
              ref="flowEditor"
              :job-id="jobId"
              :points="editTarget?.patch_points || []"
              :exclude-device-types="editKind === 'input' ? ['projector'] : []"
            />
          </div>
          <q-input
            v-model="editDraft.notes"
            type="textarea"
            autogrow
            :label="t('video.notes')"
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
            :label="t('app.actions.save')"
            @click="saveEdit"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

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
            use-input
            hide-selected
            fill-input
            input-debounce="0"
            @new-value="(val, done) => onNewDevice('chain', chainTarget?.kind, chainTarget?.obj, val, done)"
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

    <q-dialog v-model="createDialog">
      <q-card style="min-width: 320px">
        <q-card-section class="text-h6">
          {{ t('video.newDevice') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model="createDraft.name"
            :label="t('devices.name')"
            dense
            autofocus
          />
          <q-select
            v-model="createDraft.device_type"
            :options="deviceTypeChoices"
            :label="t('devices.type')"
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
            :label="t('devices.createDevice')"
            :disable="!createDraft.name.trim()"
            @click="confirmCreateDevice"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="flowDialog">
      <q-card style="min-width: 360px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('channels.signalFlow') }}
        </q-card-section>
        <q-card-section class="column items-center q-gutter-xs">
          <template
            v-for="(item, i) in flowItems"
            :key="i"
          >
            <q-icon
              v-if="i > 0"
              name="arrow_downward"
              color="grey-7"
            />
            <q-card
              flat
              bordered
              class="full-width q-pa-sm"
            >
              <div class="text-body2">
                {{ item.title }}
              </div>
              <div class="text-caption text-grey-7">
                {{ item.sub || '—' }}
              </div>
            </q-card>
          </template>
          <div
            v-if="flowItems.length <= 1"
            class="text-grey-7"
          >
            {{ t('video.flowEmpty') }}
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useVideoStore } from '@/stores/video';
import { useDevicesStore } from '@/stores/devices';
import { useStockwireStore } from '@/stores/stockwire';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import PatchChain from '@/components/PatchChain.vue';
import PatchFlowEditor from '@/components/PatchFlowEditor.vue';
import { VIDEO_DEVICE_KINDS } from '@/constants/videoDevices';

const props = defineProps({
  list: { type: Object, required: true },
  jobId: { type: String, required: true },
});

const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const store = useVideoStore();
const devicesStore = useDevicesStore();
const stockwire = useStockwireStore();
const jobId = props.jobId;

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
function firstDeviceId(obj) {
  return (obj.patch_points || [])[0]?.device_id || null;
}
function deviceConnectors(obj) {
  return devicesStore.byId(firstDeviceId(obj))?.stockwire_connectors || [];
}

async function run(fn) {
  try {
    await fn();
  } catch (err) {
    $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('common.errorOccurred') });
  }
}

function renameList(value) {
  const name = String(value || '').trim();
  if (!name || name === props.list.name) return;
  run(() => store.updateList(jobId, props.list.id, { name }));
}
function removeList() {
  $q.dialog({
    title: t('video.deleteList'),
    message: t('video.deleteListConfirm', { name: props.list.name }),
    cancel: true,
    persistent: true,
  }).onOk(() => run(() => store.deleteList(jobId, props.list.id)));
}

function saveInput(input, payload) {
  run(() => store.updateInput(jobId, input.id, payload));
}
function removeInput(input) {
  run(() => store.deleteInput(jobId, input.id));
}
function saveOutput(output, payload) {
  run(() => store.updateOutput(jobId, output.id, payload));
}
function removeOutput(output) {
  run(() => store.deleteOutput(jobId, output.id));
}

function setFirstDevice(kind, obj, deviceId) {
  run(async () => {
    const first = (obj.patch_points || [])[0];
    const create = kind === 'input' ? store.createPatchPoint : store.createOutputPatchPoint;
    const update = kind === 'input' ? store.updatePatchPoint : store.updateOutputPatchPoint;
    const remove = kind === 'input' ? store.deletePatchPoint : store.deleteOutputPatchPoint;
    if (!deviceId) {
      if (first) await remove(jobId, obj.id, first.id);
      return;
    }
    if (first) {
      await update(jobId, obj.id, first.id, { device_id: deviceId });
    } else {
      await create(jobId, obj.id, { position: 0, device_id: deviceId });
    }
  });
}

const deviceTypeChoices = VIDEO_DEVICE_KINDS.map((v) => ({ value: v, label: t(`devices.types.${v}`) }));
const createDialog = ref(false);
const createDraft = ref({ name: '', device_type: 'switcher', mode: null, kind: null, obj: null });
function onNewDevice(mode, kind, obj, val, done) {
  done();
  const name = String(val || '').trim();
  if (!name) return;
  createDraft.value = { name, device_type: 'switcher', mode, kind, obj };
  createDialog.value = true;
}
function confirmCreateDevice() {
  const draft = createDraft.value;
  run(async () => {
    const device = await devicesStore.createDevice(jobId, {
      name: draft.name.trim(),
      device_type: draft.device_type,
    });
    if (draft.mode === 'first') setFirstDevice(draft.kind, draft.obj, device.id);
    else if (draft.mode === 'draft') editDraft.value.device_id = device.id;
    else if (draft.mode === 'chain') chainDevice.value = device.id;
    createDialog.value = false;
  });
}

const flowDialog = ref(false);
const flowItems = ref([]);
// 'OUT 3 → HDMI 1' for a step that takes from an output port and feeds an input port.
function portsLabel(point) {
  if (point.source_port && point.input_port) return `${point.source_port} → ${point.input_port}`;
  if (point.source_port) return `${point.source_port} →`;
  return point.input_port || '';
}
function openFlow(kind, obj) {
  const root =
    kind === 'input'
      ? {
          title: obj.source_label || t('video.inputNumber', { n: obj.input_number }),
          sub: [t(`video.types.${obj.source_type}`), obj.connector].filter(Boolean).join(' · '),
        }
      : {
          title: obj.name || t('video.outputNumber', { n: obj.output_number }),
          sub: [obj.destination_label, obj.connector].filter(Boolean).join(' · '),
        };
  const chain = (obj.patch_points || []).map((p) => ({
    title: deviceName(p.device_id),
    sub: [portsLabel(p), p.connector, p.patch_label].filter(Boolean).join(' · '),
  }));
  flowItems.value = [root, ...chain];
  flowDialog.value = true;
}

const editDialog = ref(false);
const editKind = ref('input');
const editTarget = ref(null);
const editDraft = ref({});
function openEdit(kind, obj) {
  editKind.value = kind;
  editTarget.value = obj;
  const isInput = kind === 'input';
  editDraft.value = {
    number: isInput ? obj.input_number : obj.output_number,
    label: isInput ? obj.source_label : obj.name,
    destination: isInput ? '' : obj.destination_label,
    source_type: isInput ? obj.source_type : null,
    connector: obj.connector,
    notes: obj.notes || '',
  };
  editDialog.value = true;
}
const flowEditor = ref(null);
function saveEdit() {
  const kind = editKind.value;
  const obj = editTarget.value;
  const d = editDraft.value;
  const steps = flowEditor.value?.collect();
  if (!steps) return;
  run(async () => {
    const number = Number(d.number) || 1;
    if (kind === 'input') {
      await store.updateInput(jobId, obj.id, {
        input_number: number,
        source_label: d.label,
        source_type: d.source_type,
        connector: d.connector,
        notes: d.notes,
      });
      await store.replaceInputChain(jobId, obj.id, steps);
    } else {
      await store.updateOutput(jobId, obj.id, {
        output_number: number,
        name: d.label,
        destination_label: d.destination,
        connector: d.connector,
        notes: d.notes,
      });
      await store.replaceOutputChain(jobId, obj.id, steps);
    }
    editDialog.value = false;
  });
}

const chainDialog = ref(false);
const chainTarget = ref(null);
const chainDevice = ref(null);
function openChain(kind, obj) {
  chainTarget.value = { kind, obj };
  chainDevice.value = null;
  chainDialog.value = true;
}
function addChainPoint() {
  const target = chainTarget.value;
  if (!target || !chainDevice.value) return;
  run(async () => {
    const payload = {
      position: (target.obj.patch_points || []).length,
      device_id: chainDevice.value,
    };
    if (target.kind === 'input') {
      await store.createPatchPoint(jobId, target.obj.id, payload);
    } else {
      await store.createOutputPatchPoint(jobId, target.obj.id, payload);
    }
    chainDialog.value = false;
  });
}
function removePoint(kind, obj, point) {
  run(() =>
    kind === 'input'
      ? store.deletePatchPoint(jobId, obj.id, point.id)
      : store.deleteOutputPatchPoint(jobId, obj.id, point.id),
  );
}

const bulkInputDialog = ref(false);
const bulkOutputDialog = ref(false);
const bulkBusy = ref(false);
const bulkIn = ref({
  quantity: 4,
  start_number: 1,
  prefix: 'Cam',
  source_type: 'camera',
  connector: 'sdi',
  device_id: null,
});
const bulkOut = ref({
  quantity: 4,
  start_number: 1,
  prefix: 'Out',
  connector: 'sdi',
  device_id: null,
});
function openBulkInputs() {
  const start = (props.list.inputs || []).reduce((max, i) => Math.max(max, i.input_number), 0);
  bulkIn.value.start_number = start + 1;
  bulkInputDialog.value = true;
}
function openBulkOutputs() {
  const start = (props.list.outputs || []).reduce((max, o) => Math.max(max, o.output_number), 0);
  bulkOut.value.start_number = start + 1;
  bulkOutputDialog.value = true;
}
function saveBulkInputs() {
  bulkBusy.value = true;
  run(async () => {
    await store.bulkCreateInputs(jobId, props.list.id, {
      ...bulkIn.value,
      quantity: Number(bulkIn.value.quantity),
      start_number: Number(bulkIn.value.start_number) || 1,
    });
    bulkInputDialog.value = false;
  }).finally(() => {
    bulkBusy.value = false;
  });
}
function saveBulkOutputs() {
  bulkBusy.value = true;
  run(async () => {
    await store.bulkCreateOutputs(jobId, props.list.id, {
      ...bulkOut.value,
      quantity: Number(bulkOut.value.quantity),
      start_number: Number(bulkOut.value.start_number) || 1,
    });
    bulkOutputDialog.value = false;
  }).finally(() => {
    bulkBusy.value = false;
  });
}

const switcherDialog = ref(false);
const switcherProduct = ref(null);
const switcherIn = ref(null);
const switcherOut = ref(null);
const switcherNote = ref('');
function openSwitcher() {
  switcherProduct.value = props.list.switcher_product_id
    ? { id: props.list.switcher_product_id, name: props.list.switcher_product_name }
    : null;
  switcherIn.value = props.list.switcher_inputs ?? null;
  switcherOut.value = props.list.switcher_outputs ?? null;
  switcherNote.value = '';
  switcherDialog.value = true;
}
async function chooseSwitcher(product) {
  switcherProduct.value = product;
  switcherNote.value = '';
  if (!product?.id) return;
  try {
    const prod = await stockwire.getProduct(product.id);
    const specs = prod?.specs || {};
    const inputs = specs.inputs ?? null;
    const outputs = specs.outputs ?? null;
    if (inputs != null) switcherIn.value = inputs;
    if (outputs != null) switcherOut.value = outputs;
    const connectors = Array.isArray(specs.connectors) ? specs.connectors.join(', ') : '';
    switcherNote.value =
      inputs == null && outputs == null
        ? t('video.switcherNoSpecs')
        : t('video.switcherSpecsLoaded', { inputs: inputs ?? '–', outputs: outputs ?? '–', connectors: connectors || '–' });
  } catch (err) {
    switcherNote.value = t('video.switcherSpecsError');
  }
}
function saveSwitcher() {
  const product = switcherProduct.value;
  run(async () => {
    await store.updateList(jobId, props.list.id, {
      switcher_product_id: product?.id ? String(product.id) : null,
      switcher_product_name: product?.name || null,
      switcher_inputs: switcherIn.value === '' ? null : switcherIn.value,
      switcher_outputs: switcherOut.value === '' ? null : switcherOut.value,
    });
    const result = await store.fillFromSwitcher(jobId, props.list.id);
    $q.notify({
      type: 'positive',
      message: t('video.switcherFilled', {
        inputs: result.inputs_added,
        outputs: result.outputs_added,
        patched: result.inputs_patched + result.outputs_patched,
      }),
    });
    switcherDialog.value = false;
  });
}
function clearSwitcher() {
  run(() =>
    store.updateList(jobId, props.list.id, {
      switcher_product_id: null,
      switcher_product_name: null,
    }),
  ).then(() => {
    switcherDialog.value = false;
  });
}
</script>
