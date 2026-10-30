<template>
  <div data-testid="video-editor">
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
          v-for="entry in graph.videoLists"
          :key="entry.id"
          :name="entry.id"
          :label="entry.name"
          no-caps
          data-testid="video-list-tab"
        />
      </q-tabs>
      <q-btn
        flat
        no-caps
        icon="playlist_add"
        :label="t('workspace.addVideoList')"
        data-testid="add-video-list"
        @click="addList"
      />
    </div>

    <div
      v-if="!list"
      class="text-grey-6"
    >
      {{ t('workspace.noVideoLists') }}
    </div>

    <template v-else>
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
          :label="t('workspace.addVideoInput')"
          data-testid="add-video-input"
          @click="addRows('inputs', 1)"
        />
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('workspace.addVideoOutput')"
          data-testid="add-video-output"
          @click="addRows('outputs', 1)"
        />
        <q-btn
          v-if="list.attributes.switcher_product_id"
          flat
          no-caps
          icon="auto_fix_high"
          :label="t('workspace.fillFromSwitcher')"
          @click="fill"
        />
        <q-space />
        <q-btn
          flat
          dense
          no-caps
          color="negative"
          icon="delete"
          :label="t('workspace.deleteList')"
          @click="removeNode(list)"
        />
      </div>

      <div
        v-for="section in sections"
        :key="section.kind"
        class="q-mb-md"
      >
        <div class="text-subtitle1">
          {{ section.title }}
        </div>
        <q-list
          v-if="$q.screen.lt.sm"
          separator
          bordered
        >
          <q-item
            v-for="row in section.rows"
            :key="row.id"
          >
            <q-item-section avatar>
              {{ row.position }}
            </q-item-section>
            <q-item-section>
              <q-input
                :model-value="row.name"
                dense
                borderless
                @change="(v) => save(row, { name: v })"
              />
              <q-item-label caption>
                {{ chain(row) || t('workspace.chainEmpty') }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                dense
                round
                icon="route"
                :aria-label="t('workspace.editChain')"
                @click="openChain(row, section.kind)"
              />
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('workspace.showFlow')"
                @click="openFlow(row, section.kind)"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                @click="removeNode(row)"
              />
            </q-item-section>
          </q-item>
        </q-list>
        <q-table
          v-else
          flat
          dense
          bordered
          :rows="section.rows"
          :columns="section.columns"
          row-key="id"
          :rows-per-page-options="[0]"
          hide-bottom
          class="sticky-header-table"
          style="max-height: 70vh"
          :data-testid="`video-${section.kind}-table`"
        >
          <template #body-cell-number="slot">
            <q-td :props="slot">
              <q-input
                :model-value="slot.row.position"
                type="number"
                dense
                borderless
                style="width: 56px"
                @change="(v) => setNumber(slot.row, section.kind, Number(v))"
              />
            </q-td>
          </template>
          <template #body-cell-name="slot">
            <q-td :props="slot">
              <q-input
                :model-value="slot.row.name"
                dense
                borderless
                data-testid="video-name"
                @change="(v) => save(slot.row, { name: v })"
              />
            </q-td>
          </template>
          <template #body-cell-source="slot">
            <q-td
              :props="slot"
              style="min-width: 170px; max-width: 220px"
            >
              <StockwireProductPicker
                :model-value="sourceOf(slot.row)"
                own
                :local-items="gearItems"
                gear-type="video"
                :label="t('workspace.videoSource')"
                :hint="''"
                borderless
                data-testid="video-source-picker"
                @update:model-value="(p) => setSource(slot.row, p)"
              />
            </q-td>
          </template>
          <template #body-cell-source_type="slot">
            <q-td :props="slot">
              <q-select
                :model-value="slot.row.attributes.source_type"
                :options="sourceTypes"
                emit-value
                map-options
                dense
                borderless
                @update:model-value="(v) => saveAttr(slot.row, 'source_type', v)"
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
          <template #body-cell-output_name="slot">
            <q-td :props="slot">
              <q-input
                :model-value="slot.row.attributes.name"
                dense
                borderless
                @change="(v) => saveAttr(slot.row, 'name', v)"
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
            <q-td :props="slot">
              <q-btn
                flat
                dense
                no-caps
                icon="route"
                :label="chain(slot.row) || t('workspace.chainEmpty')"
                data-testid="edit-video-chain"
                @click="openChain(slot.row, section.kind)"
              />
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('workspace.showFlow')"
                data-testid="show-video-flow"
                @click="openFlow(slot.row, section.kind)"
              />
            </q-td>
          </template>
          <template #body-cell-actions="slot">
            <q-td
              :props="slot"
              class="text-right"
            >
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
      </div>
    </template>

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
      :fields="chainFields"
      :branching="chainKind === 'video_output'"
      @save="saveChain"
    />
  </div>
</template>

<script setup>
import { isRevisionConflict } from '@/utils/graph';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import ChainDialog from '@/components/ChainDialog.vue';
import ChainFlowDialog from '@/components/ChainFlowDialog.vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import { flowTree, isPlotElement, isVirtual, videoChainForm, videoChainNames, videoRowsOf } from '@/utils/workspace';

const props = defineProps({ jobId: { type: String, required: true } });
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const listId = ref(null);
const chainOpen = ref(false);
const chainNode = ref(null);
const chainKind = ref('video_input');
const chainInitial = ref([]);

const chainFields = [
  { key: 'connector', label: 'workspace.stepConnector' },
  { key: 'patch_label', label: 'workspace.stepLabel' },
  { key: 'source_port', label: 'workspace.stepSourcePort' },
  { key: 'input_port', label: 'workspace.stepInputPort' },
];
const sourceTypes = ['camera', 'computer', 'other'].map((v) => ({
  value: v,
  label: t(`workspace.source${v[0].toUpperCase()}${v.slice(1)}`),
}));

const list = computed(() => graph.videoLists.find((l) => l.id === listId.value) || null);
const gear = computed(() => graph.devices.filter((d) => !isVirtual(d) && !isPlotElement(d)));
const chainTitle = computed(() => `${t('workspace.editChain')}: ${chainNode.value?.name || ''}`);

const number = { name: 'number', label: '#', field: () => '', align: 'left' };
const col = (name, label) => ({ name, label, field: () => '', align: 'left' });
const tail = [
  col('notes', t('workspace.colNotes')),
  col('chain', t('workspace.chain')),
  { name: 'actions', label: '', field: () => '', align: 'right' },
];
const sections = computed(() => [
  {
    kind: 'video_input',
    title: t('workspace.videoInputs'),
    rows: videoRowsOf(graph.devices, listId.value, 'video_input'),
    columns: [
      number,
      col('name', t('workspace.colSource')),
      col('source', t('workspace.videoSource')),
      col('source_type', t('workspace.colSourceType')),
      col('connector', t('workspace.stepConnector')),
      ...tail,
    ],
  },
  {
    kind: 'video_output',
    title: t('workspace.videoOutputs'),
    rows: videoRowsOf(graph.devices, listId.value, 'video_destination'),
    columns: [
      number,
      col('name', t('workspace.colDestination')),
      col('output_name', t('workspace.colName')),
      col('connector', t('workspace.stepConnector')),
      ...tail,
    ],
  },
]);

watch(
  () => graph.videoLists.map((l) => l.id).join(),
  () => {
    if (!graph.videoLists.some((l) => l.id === listId.value)) {
      listId.value = graph.videoLists[0]?.id || null;
    }
  },
  { immediate: true },
);

const chain = (node) => videoChainNames(node, graph.edges, graph.devices).join(' → ');
const failed = (err) =>
  $q.notify({ type: 'negative', message: err.response?.data?.detail?.message || err.response?.data?.detail || err.message });

async function save(node, changes) {
  try {
    await graph.updateDevice(props.jobId, node.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const saveAttr = (node, key, value) => save(node, { attributes: { [key]: value } });
const setNumber = (node, kind, value) =>
  save(node, {
    position: value,
    attributes: { [kind === 'video_input' ? 'input_number' : 'output_number']: value },
  });

async function addList() {
  try {
    const created = await graph.createVideoList(props.jobId, { name: t('workspace.newVideoList') });
    listId.value = created.id;
  } catch (err) {
    failed(err);
  }
}

async function addRows(kind, count) {
  try {
    await graph.createVideoRows(
      props.jobId,
      list.value.id,
      kind,
      Array.from({ length: count }, () => ({})),
    );
  } catch (err) {
    failed(err);
  }
}

async function fill() {
  try {
    await graph.fillVideoFromSwitcher(props.jobId, list.value.id);
  } catch (err) {
    failed(err);
  }
}

// The source of a video input (a camera, a computer ...) is picked like a microphone's: gear
// already in the job, the company's own Stockwire products, or a typed name. A product is
// requested on the linked Stockwire job (one per input using it) by "Sync gear to Stockwire".
const gearItems = computed(() =>
  graph.devices
    .filter((d) => !isVirtual(d) && !isPlotElement(d))
    .map((d) => ({ id: d.id, name: d.name, stockwire_product_id: d.stockwire_product_id })),
);
const sourceOf = (node) =>
  node.attributes.stockwire_product_name
    ? { id: node.attributes.stockwire_product_id || null, name: node.attributes.stockwire_product_name }
    : null;
const setSource = (node, pick) =>
  save(node, {
    attributes: {
      stockwire_product_id: pick?.id ? String(pick.id) : null,
      stockwire_product_name: pick?.name || null,
      ...(pick?.name && !node.attributes.source_label ? { source_label: pick.name } : {}),
    },
  });

const flowOpen = ref(false);
const flowSteps = ref([]);

// A video output starts one branch per step without a parent; an input is one line of devices.
function openFlow(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  flowSteps.value = flowTree(node.name, videoChainForm(node, graph.edges, graph.devices), graph.devices, {
    separateRoots: kind === 'video_output',
  });
  flowOpen.value = true;
}
function editFromFlow() {
  flowOpen.value = false;
  openChain(chainNode.value, chainKind.value);
}

function openChain(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  chainInitial.value = videoChainForm(node, graph.edges, graph.devices);
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
</script>
