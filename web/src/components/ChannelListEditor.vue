<template>
  <div data-testid="channel-list-editor">
    <div class="row items-center q-gutter-sm q-mb-md">
      <q-tabs
        v-model="listId"
        dense
        align="left"
        class="col"
        active-color="primary"
        indicator-color="primary"
        inline-label
        mobile-arrows
      >
        <q-tab
          v-for="entry in graph.channelLists"
          :key="entry.id"
          :name="entry.id"
          :label="entry.name"
          no-caps
          data-testid="list-tab"
        />
      </q-tabs>
      <q-btn
        flat
        no-caps
        icon="playlist_add"
        :label="t('workspace.addList')"
        data-testid="add-list"
        @click="addList"
      />
    </div>

    <div
      v-if="!list"
      class="text-grey-6"
    >
      {{ t('workspace.noLists') }}
    </div>

    <template v-else>
      <q-card
        flat
        bordered
        class="q-pa-sm q-mb-sm row items-center q-gutter-sm"
        data-testid="list-mixer"
      >
        <q-icon
          name="tune"
          color="primary"
          size="sm"
        />
        <div class="col">
          <div class="text-caption text-grey-7">
            {{ t('stockwire.mixerOfList') }}
          </div>
          <div v-if="list.attributes.mixer_product_name || list.attributes.mixer_inputs != null || list.attributes.mixer_buses != null">
            {{ list.attributes.mixer_product_name }}
            <span
              v-if="list.attributes.mixer_inputs != null"
              class="text-grey-7"
            > · {{ list.attributes.mixer_inputs }} {{ t('stockwire.inputsShort') }}</span>
            <span
              v-if="list.attributes.mixer_buses != null"
              class="text-grey-7"
            > · {{ list.attributes.mixer_buses }} {{ t('stockwire.busesShort') }}</span>
          </div>
          <div
            v-else
            class="text-grey-7"
          >
            {{ t('stockwire.mixerNotSet') }}
          </div>
        </div>
        <div
          v-if="listMixers.length"
          class="row q-gutter-xs"
          data-testid="list-mixer-devices"
        >
          <q-chip
            v-for="mixer in listMixers"
            :key="mixer.id"
            dense
            clickable
            square
            icon="edit"
            data-testid="chain-device"
            @click="editDevice(mixer)"
          >
            {{ mixer.name }}
            <q-tooltip>{{ t('workspace.editDevice') }}</q-tooltip>
          </q-chip>
        </div>
        <q-btn
          outline
          no-caps
          color="primary"
          icon="edit"
          :label="list.attributes.mixer_product_name || list.attributes.mixer_inputs != null ? t('stockwire.changeMixer') : t('stockwire.setMixer')"
          data-testid="set-mixer"
          @click="mixerOpen = true"
        />
      </q-card>
      <div class="row items-center q-gutter-sm q-mb-sm">
        <q-input
          :model-value="list.name"
          dense
          outlined
          class="col-12 col-sm-4"
          :label="t('workspace.listName')"
          @change="(v) => save(list, { name: v })"
        />
        <q-btn
          color="primary"
          no-caps
          icon="add"
          :label="t('workspace.addChannel')"
          data-testid="add-channel"
          @click="addChannels(1)"
        />
        <q-btn
          flat
          no-caps
          icon="playlist_add"
          :label="t('workspace.bulkAdd')"
          data-testid="bulk-channels"
          @click="bulkChannels = true"
        />
        <q-btn
          flat
          no-caps
          icon="cloud_upload"
          :loading="syncing"
          :label="t('workspace.syncStockwire')"
          data-testid="sync-stockwire"
          @click="syncStockwire"
        />
        <q-space />
        <q-btn
          flat
          dense
          no-caps
          color="negative"
          icon="delete"
          :label="t('workspace.deleteList')"
          @click="removeList"
        />
      </div>

      <div class="text-subtitle1 q-mt-md">
        {{ t('workspace.inputs') }}
      </div>
      <q-list
        v-if="$q.screen.lt.sm"
        separator
        bordered
      >
        <q-item
          v-for="ch in channels"
          :key="ch.id"
        >
          <q-item-section avatar>
            {{ ch.attributes.channel_number }}
          </q-item-section>
          <q-item-section>
            <q-input
              :model-value="ch.name"
              dense
              borderless
              @change="(v) => save(ch, { name: v })"
            />
            <q-item-label caption>
              {{ chain(ch) || t('workspace.chainEmpty') }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-btn
              flat
              dense
              round
              icon="route"
              :aria-label="t('workspace.editChain')"
              @click="openChain(ch, 'channel')"
            />
            <q-btn
              flat
              dense
              round
              icon="account_tree"
              :aria-label="t('workspace.showFlow')"
              @click="openFlow(ch, 'channel')"
            />
            <q-btn
              flat
              dense
              round
              color="negative"
              icon="delete"
              :aria-label="t('workspace.remove')"
              @click="removeNode(ch)"
            />
          </q-item-section>
        </q-item>
      </q-list>
      <q-table
        v-else
        flat
        dense
        bordered
        virtual-scroll
        :virtual-scroll-item-size="44"
        :rows="channels"
        :columns="columns"
        row-key="id"
        :rows-per-page-options="[0]"
        hide-bottom
        class="sticky-header-table"
        style="max-height: 70vh"
        data-testid="channel-table"
      >
        <template #body-cell-number="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.attributes.channel_number"
              dense
              borderless
              type="number"
              style="width: 60px"
              @change="(v) => setNumber(slot.row, Number(v))"
            />
          </q-td>
        </template>
        <template #body-cell-name="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.name"
              dense
              borderless
              data-testid="channel-label"
              @change="(v) => save(slot.row, { name: v })"
            />
          </q-td>
        </template>
        <template #body-cell-input_type="slot">
          <q-td :props="slot">
            <q-select
              :model-value="slot.row.attributes.input_type"
              dense
              borderless
              clearable
              emit-value
              map-options
              :options="inputTypes"
              @update:model-value="(v) => saveAttr(slot.row, 'input_type', v)"
            />
            <div
              v-if="slot.row.attributes.input_type === 'wireless'"
              class="row no-wrap q-gutter-xs"
            >
              <q-input
                :model-value="slot.row.attributes.wireless_pack"
                dense
                borderless
                :placeholder="t('channels.fieldWirelessPack')"
                data-testid="wireless-pack"
                @change="(v) => saveAttr(slot.row, 'wireless_pack', v)"
              />
              <q-input
                :model-value="slot.row.attributes.wireless_frequency"
                dense
                borderless
                :placeholder="t('channels.fieldWirelessFrequency')"
                data-testid="wireless-frequency"
                @change="(v) => saveAttr(slot.row, 'wireless_frequency', v)"
              />
            </div>
          </q-td>
        </template>
        <template #body-cell-device="slot">
          <q-td
            :props="slot"
            style="min-width: 160px; max-width: 200px"
          >
            <StockwireProductPicker
              :model-value="sourceOf(slot.row)"
              own
              :local-items="gearItems"
              :label="t('channels.fieldDevice')"
              :hint="''"
              borderless
              data-testid="source-picker"
              @update:model-value="(p) => setSource(slot.row, p)"
            />
          </q-td>
        </template>
        <template #body-cell-stand_type="slot">
          <q-td
            :props="slot"
            style="min-width: 150px; max-width: 190px"
          >
            <StockwireProductPicker
              :model-value="standOf(slot.row)"
              gear-type="stand"
              own
              :label="t('stockwire.selectStand')"
              :hint="''"
              borderless
              data-testid="stand-picker"
              @update:model-value="(p) => setStand(slot.row, p)"
            />
          </q-td>
        </template>
        <template #body-cell-connector="slot">
          <q-td :props="slot">
            <ConnectorSelect
              :model-value="slot.row.attributes.connector || ''"
              borderless
              @update:model-value="(v) => saveAttr(slot.row, 'connector', v)"
            />
          </q-td>
        </template>
        <template #body-cell-stereo="slot">
          <q-td :props="slot">
            <q-checkbox
              :model-value="!!slot.row.attributes.stereo"
              dense
              data-testid="channel-stereo"
              @update:model-value="(v) => setStereo(slot.row, v)"
            />
            <q-chip
              v-if="stereoView(slot.row, channels).linked"
              dense
              color="primary"
              text-color="white"
              size="sm"
              data-testid="stereo-side"
            >
              {{ stereoView(slot.row, channels).isL ? 'L' : 'R' }}
              <q-tooltip>{{ t('channels.stereoLinkedTo', { ch: slot.row.attributes.stereo_channel }) }}</q-tooltip>
            </q-chip>
          </q-td>
        </template>
        <template
          v-for="flag in ['phantom_power']"
          #[`body-cell-${flag}`]="slot"
          :key="flag"
        >
          <q-td :props="slot">
            <q-checkbox
              :model-value="!!slot.row.attributes[flag]"
              dense
              @update:model-value="(v) => saveAttr(slot.row, flag, v)"
            />
          </q-td>
        </template>
        <template #body-cell-notes="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.notes"
              dense
              borderless
              @change="(v) => save(slot.row, { notes: v })"
            />
          </q-td>
        </template>
        <template #body-cell-chain="slot">
          <q-td
            :props="slot"
            class="chain-cell"
          >
            <q-btn
              flat
              dense
              no-caps
              icon="route"
              :label="chain(slot.row) || t('workspace.chainEmpty')"
              data-testid="edit-chain"
              @click="openChain(slot.row, 'channel')"
            />
            <ChainDeviceChips
              :node="slot.row"
              @edit="editDevice"
            />
            <q-btn
              flat
              dense
              round
              icon="account_tree"
              :aria-label="t('workspace.showFlow')"
              data-testid="show-flow"
              @click="openFlow(slot.row, 'channel')"
            />
          </q-td>
        </template>
        <template #body-cell-actions="slot">
          <q-td :props="slot">
            <q-btn
              flat
              dense
              round
              color="negative"
              icon="delete"
              :aria-label="t('workspace.remove')"
              @click="removeNode(slot.row)"
            />
          </q-td>
        </template>
      </q-table>

      <div class="row items-center q-mt-lg q-mb-sm">
        <div class="text-subtitle1 col">
          {{ t('workspace.outputs') }}
        </div>
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('workspace.addOutput')"
          data-testid="add-output"
          @click="addOutput"
        />
        <q-btn
          flat
          no-caps
          icon="playlist_add"
          :label="t('workspace.bulkAdd')"
          data-testid="bulk-outputs"
          @click="bulkOutputs = true"
        />
      </div>
      <q-list
        bordered
        separator
      >
        <q-item
          v-for="out in outputs"
          :key="out.id"
          data-testid="output-row"
        >
          <q-item-section>
            <q-input
              :model-value="out.name"
              dense
              borderless
              @change="(v) => save(out, { name: v })"
            />
            <q-item-label caption>
              {{ chain(out) || t('workspace.chainEmpty') }}
            </q-item-label>
            <ChainDeviceChips
              :node="out"
              @edit="editDevice"
            />
          </q-item-section>
          <q-item-section
            side
            style="min-width: 150px"
          >
            <q-select
              :model-value="out.attributes.mode || 'mono'"
              :options="modeOptions"
              emit-value
              map-options
              dense
              outlined
              :label="t('channels.outputMode')"
              data-testid="output-mode"
              @update:model-value="(v) => saveAttr(out, 'mode', v)"
            />
          </q-item-section>
          <q-item-section side>
            <div class="row">
              <q-btn
                flat
                dense
                round
                icon="route"
                :aria-label="t('workspace.editChain')"
                @click="openChain(out, 'output')"
              />
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('workspace.showFlow')"
                data-testid="show-output-flow"
                @click="openFlow(out, 'output')"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                @click="removeNode(out)"
              />
            </div>
          </q-item-section>
        </q-item>
        <q-item v-if="!outputs.length">
          <q-item-section class="text-grey-6">
            {{ t('workspace.noOutputs') }}
          </q-item-section>
        </q-item>
      </q-list>
    </template>

    <ListBulkDialog
      v-model="bulkChannels"
      :next-number="nextChannelNumber(channels)"
      :busy="bulkBusy"
      :devices="gear"
      @create="(items, opts) => bulkCreate('channels', items, opts)"
    />
    <ListBulkDialog
      v-model="bulkOutputs"
      outputs
      :busy="bulkBusy"
      @create="(items) => bulkCreate('outputs', items)"
    />
    <DeviceEditDialog
      v-model="deviceOpen"
      :device="editedDevice"
      :job-id="jobId"
    />
    <MixerDialog
      v-model="mixerOpen"
      :list="list"
      :channel-count="channels.length"
      @save="saveMixer"
    />
    <ChainFlowDialog
      v-model="flowOpen"
      :title="`${t('workspace.showFlow')}: ${chainNode?.name || ''}`"
      :steps="flowSteps"
      @edit="editFromFlow"
    />
    <ChainDialog
      v-model="chainOpen"
      :job-id="jobId"
      :title="chainTitle"
      :initial="chainInitial"
      :devices="gear"
      :branching="chainKind === 'output'"
      :bus-channels="chainKind === 'output' ? busChannelsFor(chainNode?.attributes?.mode) : []"
      @save="saveChain"
    />
  </div>
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import ChainDialog from '@/components/ChainDialog.vue';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import { api } from '@/boot/api';
import ListBulkDialog from '@/components/ListBulkDialog.vue';
import ChainDeviceChips from '@/components/ChainDeviceChips.vue';
import DeviceEditDialog from '@/components/DeviceEditDialog.vue';
import MixerDialog from '@/components/MixerDialog.vue';
import ChainFlowDialog from '@/components/ChainFlowDialog.vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import {
  chainForm,
  busChannelsFor,
  chainDevices,
  chainSteps,
  flowTree,
  OUTPUT_MODES,
  channelsOf,
  isPlotElement,
  isVirtual,
  mixerSlotsToAdd,
  nextChannelNumber,
  outputsOf,
  stereoPairPlan,
  stereoView,
} from '@/utils/workspace';

const props = defineProps({ jobId: { type: String, required: true } });
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const listId = ref(null);
const chainOpen = ref(false);
const chainNode = ref(null);
const chainKind = ref('channel');
const chainInitial = ref([]);

const list = computed(() => graph.channelLists.find((l) => l.id === listId.value) || null);
const channels = computed(() => channelsOf(graph.devices, listId.value));
const outputs = computed(() => outputsOf(graph.devices, listId.value));
const gear = computed(() => graph.devices.filter((d) => !isVirtual(d) && !isPlotElement(d)));
const chainTitle = computed(() => `${t('workspace.editChain')}: ${chainNode.value?.name || ''}`);
const inputTypes = ['microphone', 'di', 'wireless', 'fxReturn'].map((v) => ({
  value: v,
  label: t(`channels.type.${v}`),
}));

const columns = computed(() => [
  { name: 'number', label: '#', field: () => '', align: 'left' },
  { name: 'name', label: t('workspace.colName'), field: 'name', align: 'left' },
  { name: 'input_type', label: t('workspace.colKind'), field: () => '', align: 'left' },
  { name: 'device', label: t('workspace.colDevice'), field: () => '', align: 'left' },
  { name: 'stand_type', label: t('workspace.colStand'), field: () => '', align: 'left' },
  { name: 'connector', label: t('workspace.stepConnector'), field: () => '', align: 'left' },
  { name: 'phantom_power', label: '48V', field: () => '', align: 'center' },
  { name: 'stereo', label: 'ST', field: () => '', align: 'center' },
  { name: 'notes', label: t('workspace.colNotes'), field: 'notes', align: 'left' },
  { name: 'chain', label: t('workspace.chain'), field: () => '', align: 'left' },
  { name: 'actions', label: '', field: () => '', align: 'right' },
]);

watch(
  () => graph.channelLists.map((l) => l.id).join(),
  () => {
    if (!graph.channelLists.some((l) => l.id === listId.value)) {
      listId.value = graph.channelLists[0]?.id || null;
    }
  },
  { immediate: true },
);

const chain = (node) => chainSteps(node, graph.edges, graph.devices).join(' → ');
const failed = (err) =>
  $q.notify({ type: 'negative', message: apiErrorText(err) });

async function save(node, changes) {
  try {
    await graph.updateDevice(props.jobId, node.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const saveAttr = (node, key, value) => save(node, { attributes: { [key]: value } });
// Ticking "stereo" pairs the channel with its odd/even neighbour (see stereoPairPlan); unticking
// releases both. The partner is made first so the main row never points at a channel that is not
// there yet.
async function setStereo(node, on) {
  const plan = stereoPairPlan(node, channels.value, on);
  try {
    if (plan.partnerCreate) {
      await graph.createChannels(props.jobId, listId.value, [plan.partnerCreate]);
    } else if (plan.partner && plan.partnerChanges) {
      await graph.updateDevice(props.jobId, plan.partner.id, plan.partnerChanges);
    }
    await graph.updateDevice(props.jobId, node.id, plan.main);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const setNumber = (node, value) =>
  save(node, { position: value, attributes: { channel_number: value } });

async function addList() {
  try {
    const created = await graph.createList(props.jobId, { name: t('workspace.newList') });
    listId.value = created.id;
  } catch (err) {
    failed(err);
  }
}

async function addChannels(count) {
  try {
    await graph.createChannels(
      props.jobId,
      list.value.id,
      Array.from({ length: count }, () => ({})),
    );
  } catch (err) {
    failed(err);
  }
}

// The gear in this list's chains can be edited from the list: a chip next to a chain opens that
// device, and the mixer card lists the mixers (consoles) the list's channels are patched into.
const deviceOpen = ref(false);
const editedId = ref(null);
const editedDevice = computed(() => graph.devices.find((d) => d.id === editedId.value) || null);
function editDevice(device) {
  editedId.value = device.id;
  deviceOpen.value = true;
}
const listMixers = computed(() => {
  const seen = new Map();
  for (const channel of channels.value) {
    for (const device of chainDevices(channel, graph.edges, graph.devices)) {
      if (device.kind === 'mixer') seen.set(device.id, device);
    }
  }
  return [...seen.values()];
});

const mixerOpen = ref(false);
// The mixer is stored on the list, which the server mirrors to the legacy list the Stockwire sync
// reads. The list is then padded with empty inputs and outputs up to the mixer's size.
async function saveMixer({ product, inputs, buses }) {
  const wantInputs = Number(inputs) || 0;
  const wantBuses = Number(buses) || 0;
  try {
    await graph.updateDevice(props.jobId, list.value.id, {
      attributes: {
        mixer_product_id: product?.id || null,
        mixer_product_name: product?.name || null,
        mixer_inputs: inputs ?? null,
        mixer_buses: buses ?? null,
      },
    });
    const add = mixerSlotsToAdd(channels.value, outputs.value, wantInputs, wantBuses);
    if (add.channels.length) await graph.createChannels(props.jobId, list.value.id, add.channels);
    if (add.outputs.length) await graph.createOutputs(props.jobId, list.value.id, add.outputs);
    if (add.channels.length || add.outputs.length) {
      $q.notify({
        type: 'positive',
        message: t('stockwire.mixerFilled', { inputs: add.channels.length, buses: add.outputs.length }),
      });
    }
    mixerOpen.value = false;
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}

const bulkChannels = ref(false);
const bulkOutputs = ref(false);
const bulkBusy = ref(false);

async function bulkCreate(kind, items, opts = {}) {
  bulkBusy.value = true;
  try {
    if (kind === 'channels') {
      const created = await graph.createChannels(props.jobId, list.value.id, items);
      if (opts.deviceId) {
        await graph.setChannelChains(
          props.jobId,
          created.map((c) => c.id),
          [{ device_id: opts.deviceId }],
        );
      }
    } else await graph.createOutputs(props.jobId, list.value.id, items);
    bulkChannels.value = false;
    bulkOutputs.value = false;
  } catch (err) {
    failed(err);
  } finally {
    bulkBusy.value = false;
  }
}

// A stand is a Stockwire product (or a name typed in for something not in the catalog). The
// product is stored on the channel; stand_type keeps the name for lists and exports. "Sync to
// Stockwire" then adds the stands, mixers and gear to the linked Stockwire job.
const standOf = (node) =>
  node.attributes.stand_product_name || node.attributes.stand_type
    ? { id: node.attributes.stand_product_id || null, name: node.attributes.stand_product_name || node.attributes.stand_type }
    : null;
const setStand = (node, product) =>
  save(node, {
    attributes: {
      stand_product_id: product?.id ? String(product.id) : null,
      stand_product_name: product?.name || null,
      stand_type: product?.name || '',
    },
  });

// The source of a channel (the device or microphone it comes from) is something already in the
// job, one of the company's own Stockwire products, or a name typed in.
const gearItems = computed(() =>
  graph.devices
    .filter((d) => !isVirtual(d) && !isPlotElement(d))
    .map((d) => ({ id: d.id, name: d.name, stockwire_product_id: d.stockwire_product_id })),
);
const sourceOf = (node) => {
  const name = node.attributes.device || node.stockwire_product_name;
  return name ? { id: node.stockwire_product_id || null, name } : null;
};
const setSource = (node, pick) =>
  save(node, {
    attributes: { device: pick?.name || '' },
    stockwire_product_id: pick?.id ? String(pick.id) : null,
    stockwire_product_name: pick?.id ? pick.name : null,
  });

const syncing = ref(false);
async function syncStockwire() {
  syncing.value = true;
  try {
    const { data } = await api.post(`/jobs/${props.jobId}/sync-stockwire`);
    $q.notify({
      type: data.errors?.length ? 'warning' : 'positive',
      message: data.errors?.length
        ? `${t('workspace.stockwireSynced', { added: data.added.length, updated: data.updated.length, removed: data.removed.length })}. ${t('workspace.syncErrors', { n: data.errors.length })}: ${data.errors.slice(0, 3).join('; ')}`
        : t('workspace.stockwireSynced', {
            added: data.added.length,
            updated: data.updated.length,
            removed: data.removed.length,
          }),
    });
  } catch (err) {
    failed(err);
  } finally {
    syncing.value = false;
  }
}

async function addOutput() {
  try {
    await graph.createOutput(props.jobId, list.value.id, { name: `${t('workspace.output')} ${outputs.value.length + 1}` });
  } catch (err) {
    failed(err);
  }
}

const modeOptions = computed(() =>
  OUTPUT_MODES.map((m) => ({ value: m.value, label: t(`workspace.busMode.${m.value.replace(/[._]/g, '')}`) })),
);

const flowOpen = ref(false);
const flowSteps = ref([]);

// The chain as a diagram; its branches follow the parent of each step (outputs branch).
function openFlow(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  flowSteps.value = flowTree(node.name, chainForm(node, graph.edges, graph.devices), graph.devices);
  flowOpen.value = true;
}
function editFromFlow() {
  flowOpen.value = false;
  openChain(chainNode.value, chainKind.value);
}

function openChain(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  chainInitial.value = chainForm(node, graph.edges, graph.devices);
  chainOpen.value = true;
}

async function saveChain(steps) {
  try {
    await graph.replaceChain(props.jobId, chainKind.value, chainNode.value.id, steps);
    chainOpen.value = false;
  } catch (err) {
    failed(err);
  }
}

function removeNode(node) {
  $q.dialog({ title: t('workspace.remove'), message: node.name, cancel: true, persistent: true }).onOk(
    async () => {
      try {
        await graph.deleteDevice(props.jobId, node.id);
      } catch (err) {
        if (!isRevisionConflict(err)) failed(err);
      }
    },
  );
}

const removeList = () => removeNode(list.value);
</script>

<style scoped>
/* The chain button shows the whole chain and sits next to the flow button, so the cell must be
   wide enough for both or the next column would cover the flow button. */
.chain-cell {
  min-width: 240px;
  white-space: nowrap;
}
</style>
