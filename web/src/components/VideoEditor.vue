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
          flat
          no-caps
          icon="tune"
          :label="hasSwitcher ? t('video.changeSwitcher') : t('video.setSwitcher')"
          data-testid="set-switcher"
          @click="switcherOpen = true"
        />
        <div
          v-if="listSwitchers.length || hasSwitcher"
          class="row q-gutter-xs items-center"
          data-testid="list-switcher-devices"
        >
          <q-chip
            v-for="device in listSwitchers"
            :key="device.id"
            dense
            clickable
            square
            icon="edit"
            data-testid="chain-device"
            @click="editDevice(device)"
          >
            {{ device.name }}
            <q-tooltip>{{ t('workspace.editDevice') }}</q-tooltip>
          </q-chip>
        </div>
        <div
          v-if="hasSwitcher"
          class="text-caption text-grey-7 q-mt-xs"
        >
          {{ t('video.switcherSummary', { name: list.attributes.switcher_product_name, inputs: list.attributes.switcher_inputs ?? '–', outputs: list.attributes.switcher_outputs ?? '–' }) }}
        </div>
        <q-btn
          v-if="hasSwitcher"
          flat
          no-caps
          icon="auto_fix_high"
          :label="t('workspace.fillFromSwitcher')"
          data-testid="fill-from-switcher"
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

      <!-- Match the sound channel list's console view: the inputs/outputs tabs live inside a card
           with icons (like the console's profile/inputs/buses tabs), so the two editors read as
           one product. -->
      <q-card
        flat
        bordered
        class="q-mb-md"
        data-testid="video-io-card"
      >
        <q-tabs
          v-model="videoTab"
          dense
          align="left"
          active-color="primary"
          indicator-color="primary"
          inline-label
          mobile-arrows
          data-testid="video-io-tabs"
        >
          <q-tab
            name="video_input"
            icon="input"
            :label="t('workspace.videoInputs')"
            no-caps
            data-testid="video-tab-inputs"
          />
          <q-tab
            name="video_output"
            icon="output"
            :label="t('workspace.videoOutputs')"
            no-caps
            data-testid="video-tab-outputs"
          />
        </q-tabs>
        <q-separator />
        <q-tab-panels
          v-model="videoTab"
          animated
        >
          <q-tab-panel
            v-for="section in sections"
            :key="section.kind"
            :name="section.kind"
          >
            <div class="row items-center q-gutter-sm">
              <div class="text-subtitle1">
                {{ section.title }}
              </div>
              <q-space />
              <q-btn
                flat
                dense
                no-caps
                icon="add"
                :label="section.kind === 'video_input' ? t('workspace.addVideoInput') : t('workspace.addVideoOutput')"
                :data-testid="section.kind === 'video_input' ? 'add-video-input' : 'add-video-output'"
                @click="addRows(section.kind === 'video_input' ? 'inputs' : 'outputs', 1)"
              />
              <q-btn
                flat
                dense
                no-caps
                icon="playlist_add"
                :label="section.kind === 'video_input' ? t('video.bulkInputs') : t('video.bulkOutputs')"
                :data-testid="`bulk-${section.kind === 'video_input' ? 'inputs' : 'outputs'}`"
                @click="openBulk(section.kind)"
              />
            </div>
            <!-- Phones get one card per row with the same editors as the table: number, name and the
             chain actions in the header, a summary line, and the rest under "Details". -->
            <div
              v-if="$q.screen.lt.sm"
              class="column q-gutter-sm"
              :data-testid="`video-${section.kind}-cards`"
            >
              <q-card
                v-for="row in section.rows"
                :key="row.id"
                flat
                bordered
                data-testid="video-card"
              >
                <q-card-section class="q-pa-sm">
                  <div class="row items-center no-wrap">
                    <div class="text-subtitle2 q-pr-sm">
                      {{ row.position }}
                    </div>
                    <q-input
                      :model-value="row.name"
                      dense
                      borderless
                      class="col"
                      @change="(v) => save(row, { name: v })"
                    />
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
                      icon="edit"
                      :aria-label="t('workspace.editVideoInput')"
                      data-testid="video-edit-open"
                      @click="openVideoRowEdit(row, section.kind)"
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
                  </div>
                  <div class="text-caption text-grey-6">
                    {{ videoSummary(row, section.kind) || t('workspace.chainEmpty') }}
                  </div>
                  <div class="text-caption text-grey-6">
                    {{ chain(row) || t('workspace.chainEmpty') }}
                  </div>
                </q-card-section>
                <q-expansion-item
                  dense
                  :label="t('workspace.details')"
                  header-class="text-caption"
                >
                  <div class="q-pa-sm q-gutter-sm">
                    <template v-if="section.kind === 'video_input'">
                      <StockwireProductPicker
                        :model-value="sourceOf(row)"
                        own
                        :local-items="gearItems"
                        gear-type="video"
                        :label="t('workspace.videoSource')"
                        :hint="''"
                        @update:model-value="(p) => setSource(row, p)"
                      />
                      <q-select
                        :model-value="row.attributes.source_type"
                        :options="sourceTypes"
                        emit-value
                        map-options
                        dense
                        outlined
                        :label="t('workspace.colSourceType')"
                        @update:model-value="(v) => saveAttr(row, 'source_type', v)"
                      />
                    </template>
                    <q-input
                      v-else
                      :model-value="row.attributes.name"
                      dense
                      outlined
                      :label="t('workspace.colName')"
                      @change="(v) => saveAttr(row, 'name', v)"
                    />
                    <ConnectorSelect
                      :model-value="row.attributes.connector || ''"
                      @update:model-value="(v) => saveAttr(row, 'connector', v)"
                    />
                    <div class="row items-start q-gutter-xs">
                      <NotesDisplay
                        v-if="row.notes"
                        class="col"
                        :notes="row.notes"
                        :rows="3"
                      />
                      <q-btn
                        dense
                        flat
                        no-caps
                        size="sm"
                        :icon="row.notes ? 'edit' : 'add'"
                        :label="row.notes ? undefined : t('workspace.colNotes')"
                        :aria-label="t('workspace.editNotes')"
                        data-testid="video-edit-notes"
                        @click="openVideoNotes(row)"
                      />
                    </div>
                  </div>
                </q-expansion-item>
              </q-card>
            </div>
            <AdaptiveTable
              v-else
              :table-id="section.kind === 'video_input' ? 'video-inputs' : 'video-outputs'"
              flat
              dense
              bordered
              virtual-scroll
              :virtual-scroll-item-size="80"
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
                  <div class="row items-start q-gutter-xs">
                    <NotesDisplay
                      v-if="slot.row.notes"
                      class="col"
                      :notes="slot.row.notes"
                      :rows="2"
                    />
                    <q-btn
                      dense
                      flat
                      no-caps
                      size="sm"
                      :icon="slot.row.notes ? 'edit' : 'add'"
                      :label="slot.row.notes ? undefined : t('workspace.colNotes')"
                      :aria-label="t('workspace.editNotes')"
                      data-testid="video-edit-notes"
                      @click="openVideoNotes(slot.row)"
                    />
                  </div>
                </q-td>
              </template>
              <template #body-cell-chain="slot">
                <q-td :props="slot">
                  <!-- a long chain shortens its label instead of pushing the flow button under the
                   next column, where it cannot be clicked -->
                  <div class="row no-wrap items-center video-chain-cell">
                    <q-btn
                      flat
                      dense
                      no-caps
                      icon="route"
                      class="video-chain-btn"
                      :label="chain(slot.row) || t('workspace.chainEmpty')"
                      :title="chain(slot.row)"
                      data-testid="edit-video-chain"
                      @click="openChain(slot.row, section.kind)"
                    />
                    <q-btn
                      flat
                      dense
                      round
                      icon="account_tree"
                      class="col-auto"
                      :aria-label="t('workspace.showFlow')"
                      data-testid="show-video-flow"
                      @click="openFlow(slot.row, section.kind)"
                    />
                  </div>
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
                    icon="edit"
                    :aria-label="t('workspace.editVideoInput')"
                    data-testid="video-edit-open"
                    @click="openVideoRowEdit(slot.row, section.kind)"
                  />
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
            </AdaptiveTable>
          </q-tab-panel>
        </q-tab-panels>
      </q-card>
    </template>

    <ChainFlowDialog
      v-model="flowOpen"
      :title="`${t('workspace.showFlow')}: ${chainNode?.name || ''}`"
      :steps="flowSteps"
      @edit="editFromFlow"
      @device="(id) => editDevice({ id })"
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

    <!-- Shared markdown editor for video (input/output) notes; opened from the card and table. -->
    <MarkdownEditorDialog
      v-model="videoNotesOpen"
      :title="t('workspace.colNotes')"
      :value="videoNotesTarget?.notes || ''"
      @save="(text) => videoNotesTarget && save(videoNotesTarget, { notes: text })"
    />

    <VideoBulkDialog
      v-model="bulkVideoOpen"
      :kind="bulkVideoKind"
      :next-number="nextVideoNumber(bulkVideoKind)"
      :busy="bulkBusy"
      @create="(items) => bulkCreate(bulkVideoKind, items)"
    />

    <SwitcherDialog
      v-model="switcherOpen"
      :list="list"
      @save="saveSwitcher"
    />

    <!-- Consolidated editor for one video row: source, connector and signal metadata in one modal. -->
    <VideoRowEditDialog
      v-model="videoRowEditOpen"
      :row="editRow"
      :kind="editKind"
      :gear-items="gearItems"
      data-testid="video-edit-dialog"
      @save="(changes) => editRow && save(editRow, changes)"
    />
  </div>
</template>

<script setup>
import AdaptiveTable from '@/components/AdaptiveTable.vue';
import NotesDisplay from '@/components/NotesDisplay.vue';
import MarkdownEditorDialog from '@/components/MarkdownEditorDialog.vue';
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import ChainDialog from '@/components/ChainDialog.vue';
import ChainFlowDialog from '@/components/ChainFlowDialog.vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import VideoBulkDialog from '@/components/VideoBulkDialog.vue';
import SwitcherDialog from '@/components/SwitcherDialog.vue';
import VideoRowEditDialog from '@/components/VideoRowEditDialog.vue';
import {
  flowTree,
  isPlotElement,
  isVirtual,
  videoChainDevices,
  videoChainForm,
  videoChainNames,
  videoRowsOf,
} from '@/utils/workspace';

// A venue's Standard Base Rig reuses this editor, so it accepts an optional `venueId`; store calls
// route by the active graph scope, so passing the right id (venue when present, else job) is enough.
const props = defineProps({
  jobId: { type: String, default: null },
  venueId: { type: String, default: null },
});
const scopeId = computed(() => props.venueId || props.jobId);
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const listId = ref(null);
// Inputs and outputs live on their own tabs (like the sound channel list), so only the active
// section's rows are in the DOM — the bulk/add controls for each live in that tab's header.
const videoTab = ref('video_input');
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
// A switcher is "set" either by picking a catalog product or by entering manual
// input/output counts on a house switcher. Both must reveal the summary and the
// fill action — and both should fill the list when set (parity with the sound
// mixer, which pads its channels on set).
const hasSwitcher = computed(
  () =>
    !!list.value?.attributes?.switcher_product_id ||
    list.value?.attributes?.switcher_inputs != null ||
    list.value?.attributes?.switcher_outputs != null,
);
const gear = computed(() => graph.devices.filter((d) => !isVirtual(d) && !isPlotElement(d)));

// The gear in a chain is edited from the signal flow or the chain dialog (an edit button on each
// device); the toolbar lists the switchers and routers the list's inputs and outputs use.
function editDevice(device) {
  flowOpen.value = false;
  graph.selectedDeviceId = device.id;
}
const listSwitchers = computed(() => {
  const seen = new Map();
  const nodes = graph.devices.filter(
    (d) => ['video_input', 'video_destination'].includes(d.kind) && d.attributes?.list_id === listId.value,
  );
  for (const node of nodes) {
    for (const device of videoChainDevices(node, graph.edges, graph.devices)) {
      if (['switcher', 'router'].includes(device.kind)) seen.set(device.id, device);
    }
  }
  return [...seen.values()];
});
const chainTitle = computed(() => `${t('workspace.editChain')}: ${chainNode.value?.name || ''}`);

// Layout meta per column (see utils/columnLayout.js): the number and actions are compact, the
// descriptive columns share the space by weight.
const number = { name: 'number', label: '#', field: () => '', align: 'left', min: 56, width: 64, grow: 0, required: true };
const col = (name, label, meta = {}) => ({ name, label, field: () => '', align: 'left', min: 120, width: 180, grow: 1.5, ...meta });
const tail = [
  col('notes', t('workspace.colNotes'), { min: 120, width: 180, grow: 1.5 }),
  col('chain', t('workspace.chain'), { min: 200, width: 260, grow: 2 }),
  { name: 'actions', label: '', field: () => '', align: 'right', min: 96, width: 96, grow: 0 },
];
const sections = computed(() => [
  {
    kind: 'video_input',
    title: t('workspace.videoInputs'),
    rows: videoRowsOf(graph.devices, listId.value, 'video_input'),
    columns: [
      number,
      col('name', t('workspace.colSource'), { min: 150, width: 200, grow: 3, required: true }),
      col('source', t('workspace.videoSource')),
      col('source_type', t('workspace.colSourceType')),
      col('connector', t('workspace.stepConnector'), { min: 110, width: 130, grow: 0.5 }),
      ...tail,
    ],
  },
  {
    kind: 'video_output',
    title: t('workspace.videoOutputs'),
    rows: videoRowsOf(graph.devices, listId.value, 'video_destination'),
    columns: [
      number,
      col('name', t('workspace.colDestination'), { min: 150, width: 200, grow: 3, required: true }),
      col('output_name', t('workspace.colName'), { min: 130, width: 180, grow: 2 }),
      col('connector', t('workspace.stepConnector'), { min: 110, width: 130, grow: 0.5 }),
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

// One line saying what a video row has set, for the phone card.
const videoSummary = (row, kind) =>
  [
    kind === 'video_input' ? sourceOf(row)?.name : row.attributes.name,
    kind === 'video_input' ? sourceTypes.find((o) => o.value === row.attributes.source_type)?.label : '',
    row.attributes.connector,
  ]
    .filter(Boolean)
    .join(' · ');
const chain = (node) => videoChainNames(node, graph.edges, graph.devices).join(' → ');
const failed = (err) =>
  $q.notify({ type: 'negative', message: apiErrorText(err) });

async function save(node, changes) {
  try {
    await graph.updateDevice(scopeId.value, node.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const saveAttr = (node, key, value) => save(node, { attributes: { [key]: value } });

// Video (input/output) notes open the shared MarkdownEditorDialog; the dialog seeds from the row and
// saves back through the normal video-device save.
const videoNotesOpen = ref(false);
const videoNotesTarget = ref(null);
function openVideoNotes(row) {
  videoNotesTarget.value = row;
  videoNotesOpen.value = true;
}

// The row edit dialog replaces the cramped inline card expansion with one modal exposing the row's
// source, connector and signal metadata; it emits a diff that save() applies (realtime-synced).
const videoRowEditOpen = ref(false);
const editRow = ref(null);
const editKind = ref('video_input');
function openVideoRowEdit(row, kind) {
  editRow.value = row;
  editKind.value = kind;
  videoRowEditOpen.value = true;
}
const setNumber = (node, kind, value) =>
  save(node, {
    position: value,
    attributes: { [kind === 'video_input' ? 'input_number' : 'output_number']: value },
  });

async function addList() {
  try {
    const created = await graph.createVideoList(scopeId.value, { name: t('workspace.newVideoList') });
    listId.value = created.id;
  } catch (err) {
    failed(err);
  }
}

async function addRows(kind, count) {
  try {
    await graph.createVideoRows(
      scopeId.value,
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
    await graph.fillVideoFromSwitcher(scopeId.value, list.value.id);
  } catch (err) {
    failed(err);
  }
}

// Bulk-add many inputs or outputs at once through the existing batch endpoint
// (graph.createVideoRows already publishes a graph.device.upsert per row, so the
// other client updates live). The dialog builds the item bodies; we only map the
// section kind to the endpoint's `inputs`/`outputs` vocabulary and persist.
const bulkVideoOpen = ref(false);
const bulkVideoKind = ref('inputs'); // 'inputs' | 'outputs' for dialog + endpoint
const bulkBusy = ref(false);
function openBulk(sectionKind) {
  bulkVideoKind.value = sectionKind === 'video_input' ? 'inputs' : 'outputs';
  bulkVideoOpen.value = true;
}
// Continue the existing numbering for the list so bulk rows don't collide with
// what's already there. Input rows are stored as `video_input`, outputs as
// `video_destination`; the number lives in `input_number` / `output_number`.
function nextVideoNumber(kind) {
  const rowKind = kind === 'inputs' ? 'video_input' : 'video_destination';
  const numberKey = kind === 'inputs' ? 'input_number' : 'output_number';
  let max = 0;
  for (const row of videoRowsOf(graph.devices, listId.value, rowKind)) {
    const n = Number(row.attributes?.[numberKey]);
    if (Number.isFinite(n)) max = Math.max(max, n);
  }
  return max + 1;
}
async function bulkCreate(kind, items) {
  bulkBusy.value = true;
  try {
    await graph.createVideoRows(scopeId.value, list.value.id, kind, items);
    bulkVideoOpen.value = false;
  } catch (err) {
    failed(err);
  } finally {
    bulkBusy.value = false;
  }
}

// Set (or clear) the list's switcher. Stored on the list node's attributes, then —
// like the sound mixer, which pads its channels the moment a mixer is chosen — the
// list is filled up to the switcher's size (manual counts or product-derived).
// Saving through updateDevice publishes a graph.device.upsert so the summary
// updates live; fillVideoFromSwitcher wires the rows to the switcher device too.
const switcherOpen = ref(false);
async function saveSwitcher({ product, inputs, outputs }) {
  const setting = !!product || inputs != null || outputs != null;
  try {
    await graph.updateDevice(scopeId.value, list.value.id, {
      attributes: {
        switcher_product_id: product?.id ? String(product.id) : null,
        switcher_product_name: product?.name || null,
        switcher_inputs: inputs ?? null,
        switcher_outputs: outputs ?? null,
      },
    });
    // Only fill when actually setting a switcher; clearing (all null) just removes it.
    if (setting) await graph.fillVideoFromSwitcher(scopeId.value, list.value.id);
    switcherOpen.value = false;
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
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
    await graph.replaceChain(scopeId.value, chainKind.value, chainNode.value.id, steps);
    chainOpen.value = false;
  } catch (err) {
    failed(err);
  }
}

function removeNode(node) {
  $q.dialog({ title: t('workspace.remove'), message: node.name, cancel: true, persistent: true }).onOk(
    async () => {
      try {
        await graph.deleteDevice(scopeId.value, node.id);
      } catch (err) {
        if (!isRevisionConflict(err)) failed(err);
      }
    },
  );
}
</script>

<style scoped>
.video-chain-cell {
  min-width: 0;
  max-width: 100%;
}
.video-chain-btn {
  min-width: 0;
  flex: 0 1 auto;
}
.video-chain-btn :deep(.q-btn__content) {
  min-width: 0;
  flex-wrap: nowrap;
}
.video-chain-btn :deep(.block) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
