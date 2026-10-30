<template>
  <div data-testid="lights-editor">
    <div class="row items-center q-mb-md q-gutter-sm">
      <div class="text-subtitle1 col">
        {{ t('lights.title') }}
      </div>
      <q-btn
        color="primary"
        no-caps
        icon="add"
        :label="t('workspace.addFixture')"
        data-testid="add-fixture"
        @click="addFixtures(1)"
      />
      <q-btn
        flat
        no-caps
        icon="playlist_add"
        :label="t('workspace.addFixtures', { n: 8 })"
        @click="addFixtures(8)"
      />
      <q-btn
        flat
        no-caps
        icon="inventory"
        :label="t('workspace.library')"
        data-testid="open-library"
        @click="libraryOpen = true"
      />
      <q-btn
        flat
        no-caps
        icon="upload_file"
        :label="t('workspace.importFixtures')"
        data-testid="import-fixtures"
        @click="fileInput.click()"
      />
      <input
        ref="fileInput"
        type="file"
        accept=".csv,.mvr"
        class="hidden"
        data-testid="import-file"
        @change="importFile"
      >
    </div>

    <div
      v-if="!fixtures.length"
      class="text-grey-6"
    >
      {{ t('workspace.noFixtures') }}
    </div>

    <q-list
      v-else-if="$q.screen.lt.sm"
      bordered
      separator
    >
      <q-item
        v-for="fixture in fixtures"
        :key="fixture.id"
      >
        <q-item-section>
          <q-item-label>{{ fixture.name }}</q-item-label>
          <q-item-label caption>
            U{{ fixture.attributes.universe ?? '–' }} · {{ fixture.attributes.dmx_address ?? '–' }}
            · {{ fixture.attributes.footprint ?? 1 }} ch · {{ fixture.attributes.fixture_type || '' }}
          </q-item-label>
          <q-item-label
            v-if="flagsOf(fixture).conflict || flagsOf(fixture).overflow"
            class="text-negative"
            caption
          >
            {{ flagsOf(fixture).conflict ? t('lights.conflict') : t('lights.overflow') }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="remove(fixture)"
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
      :rows="fixtures"
      :columns="columns"
      row-key="id"
      :rows-per-page-options="[0]"
      hide-bottom
      style="max-height: 560px"
      data-testid="fixture-table"
    >
      <template
        v-for="field in numberFields"
        #[`body-cell-${field}`]="slot"
        :key="field"
      >
        <q-td :props="slot">
          <q-input
            :model-value="slot.row.attributes[field]"
            dense
            borderless
            type="number"
            style="width: 76px"
            :data-testid="`fixture-${field}`"
            @change="(v) => saveAttr(slot.row, field, v === '' ? null : Number(v))"
          />
        </q-td>
      </template>
      <template
        v-for="field in textFields"
        #[`body-cell-${field}`]="slot"
        :key="field"
      >
        <q-td :props="slot">
          <q-input
            :model-value="slot.row.attributes[field]"
            dense
            borderless
            @change="(v) => saveAttr(slot.row, field, v || null)"
          />
        </q-td>
      </template>
      <template #body-cell-fixture_type="slot">
        <q-td :props="slot">
          <q-select
            :model-value="slot.row.attributes.fixture_type"
            dense
            borderless
            use-input
            hide-dropdown-icon
            input-debounce="0"
            new-value-mode="add-unique"
            :options="typeOptions"
            style="min-width: 130px"
            data-testid="fixture-fixture_type"
            @filter="filterTypes"
            @update:model-value="(v) => saveAttr(slot.row, 'fixture_type', v || null)"
          />
        </q-td>
      </template>
      <template #body-cell-channel_mode="slot">
        <q-td :props="slot">
          <q-select
            :model-value="slot.row.attributes.channel_mode"
            dense
            borderless
            use-input
            hide-dropdown-icon
            input-debounce="0"
            new-value-mode="add-unique"
            :options="modeOptions"
            style="min-width: 100px"
            data-testid="fixture-channel_mode"
            @filter="(v, update) => filterModes(slot.row, v, update)"
            @update:model-value="(v) => chooseMode(slot.row, v)"
          />
        </q-td>
      </template>
      <template #body-cell-check="slot">
        <q-td :props="slot">
          <q-icon
            v-if="flagsOf(slot.row).conflict"
            name="warning"
            color="negative"
            data-testid="dmx-conflict"
          >
            <q-tooltip>{{ t('lights.conflict') }}</q-tooltip>
          </q-icon>
          <q-icon
            v-if="flagsOf(slot.row).overflow"
            name="error"
            color="negative"
            data-testid="dmx-overflow"
          >
            <q-tooltip>{{ t('lights.overflow') }}</q-tooltip>
          </q-icon>
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
            @click="remove(slot.row)"
          />
        </q-td>
      </template>
    </q-table>

    <div class="row items-center q-mt-xl q-mb-sm">
      <div class="text-subtitle1 col">
        {{ t('workspace.universes') }}
      </div>
      <q-btn
        flat
        no-caps
        icon="add"
        :label="t('workspace.addUniverse')"
        data-testid="add-universe"
        @click="addUniverse"
      />
    </div>
    <q-list
      bordered
      separator
    >
      <q-item
        v-for="uni in universes"
        :key="uni.id"
        class="column"
        data-testid="universe-row"
      >
        <div class="row items-center q-col-gutter-sm full-width">
          <div class="col-auto text-weight-bold">
            U{{ uni.attributes.number }}
          </div>
          <q-input
            :model-value="uni.name"
            class="col"
            dense
            borderless
            @change="(v) => save(uni, { name: v })"
          />
          <q-select
            :model-value="sourceOf(uni)"
            class="col-12 col-sm-3"
            dense
            outlined
            clearable
            emit-value
            map-options
            :options="gearOptions"
            :label="t('workspace.universeSource')"
            data-testid="universe-source"
            @update:model-value="(v) => setSource(uni, v)"
          />
          <q-input
            :model-value="uni.attributes.source_port"
            class="col-6 col-sm-2"
            dense
            outlined
            :label="t('workspace.sourcePort')"
            @change="(v) => saveAttr(uni, 'source_port', v)"
          />
          <q-btn
            flat
            dense
            no-caps
            icon="route"
            :label="t('workspace.editChain')"
            data-testid="edit-universe-chain"
            @click="openChain(uni)"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="remove(uni)"
          />
        </div>
        <div class="text-caption text-grey-6">
          {{ chainText(uni) || t('workspace.chainEmpty') }}
        </div>
        <q-expansion-item
          v-if="treeOf(uni).length"
          dense
          icon="account_tree"
          :label="t('workspace.flowDiagram')"
          class="full-width"
        >
          <DmxFlowDiagram
            :steps="treeOf(uni)"
            :universe-number="uni.attributes.number"
          />
        </q-expansion-item>
      </q-item>
      <q-item v-if="!universes.length">
        <q-item-section class="text-grey-6">
          {{ t('workspace.noUniverses') }}
        </q-item-section>
      </q-item>
    </q-list>

    <FixtureLibraryDialog
      v-model="libraryOpen"
      :job-id="jobId"
    />
    <ChainDialog
      v-model="chainOpen"
      :title="`${t('workspace.editChain')}: ${chainNode?.name || ''}`"
      :initial="chainInitial"
      :devices="chainDevices"
      :fields="dmxFields"
      branching
      @save="saveChain"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import ChainDialog from '@/components/ChainDialog.vue';
import DmxFlowDiagram from '@/components/DmxFlowDiagram.vue';
import FixtureLibraryDialog from '@/components/FixtureLibraryDialog.vue';
import { useFixtureLibraryStore } from '@/stores/fixtureLibrary';
import { dmxFlags } from '@/utils/dmx';
import {
  chainForm,
  chainSteps,
  dmxTree,
  fixtureView,
  fixturesOf,
  isGear,
  modeAttributes,
  modesForType,
  universeSource,
  universesOf,
} from '@/utils/workspace';

const props = defineProps({ jobId: { type: String, required: true } });
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();

const library = useFixtureLibraryStore();
const libraryOpen = ref(false);
const typeOptions = ref([]);
const fileInput = ref(null);
const chainOpen = ref(false);
const chainNode = ref(null);
const chainInitial = ref([]);
const dmxFields = [
  { key: 'connector', label: 'workspace.stepConnector' },
  { key: 'in_port', label: 'workspace.stepIn' },
  { key: 'out_port', label: 'workspace.stepOut' },
];
const numberFields = ['universe', 'dmx_address', 'footprint'];
const textFields = ['location', 'gel', 'purpose'];
const fixtures = computed(() => fixturesOf(graph.devices));
const universes = computed(() => universesOf(graph.devices));
const chainDevices = computed(() => graph.devices.filter(isGear));
const gearOptions = computed(() =>
  chainDevices.value.map((d) => ({ label: d.name, value: d.id })),
);
const sourceOf = (uni) => universeSource(uni, graph.edges);
const treeOf = (uni) => dmxTree(uni, graph.edges, graph.devices);
const chainText = (uni) => chainSteps(uni, graph.edges, graph.devices).join(' → ');
const flags = computed(() => dmxFlags(fixtures.value.map(fixtureView)));
const flagsOf = (fixture) => flags.value.get(fixture.id) || { conflict: false, overflow: false };

const columns = computed(() => [
  { name: 'name', label: t('workspace.colName'), field: 'name', align: 'left' },
  { name: 'universe', label: t('lights.colUniverse'), field: () => '', align: 'left' },
  { name: 'dmx_address', label: t('lights.colAddress'), field: () => '', align: 'left' },
  { name: 'fixture_type', label: t('lights.colFixtureType'), field: () => '', align: 'left' },
  { name: 'channel_mode', label: t('lights.colChannelMode'), field: () => '', align: 'left' },
  { name: 'footprint', label: t('lights.colFootprint'), field: () => '', align: 'left' },
  { name: 'location', label: t('lights.colLocation'), field: () => '', align: 'left' },
  { name: 'gel', label: t('lights.colGel'), field: () => '', align: 'left' },
  { name: 'purpose', label: t('lights.colPurpose'), field: () => '', align: 'left' },
  { name: 'check', label: t('lights.colStatus'), field: () => '', align: 'center' },
  { name: 'actions', label: '', field: () => '', align: 'right' },
]);

const failed = (err) =>
  $q.notify({ type: 'negative', message: err.response?.data?.detail?.message || err.response?.data?.detail || err.message });

async function saveAttr(node, key, value) {
  try {
    await graph.updateDevice(props.jobId, node.id, { attributes: { [key]: value } });
  } catch (err) {
    if (err.response?.status !== 409) failed(err);
  }
}

function filterTypes(value, update) {
  update(() => {
    const needle = value.toLowerCase();
    typeOptions.value = library.types.map((t_) => t_.name).filter((n) => n.toLowerCase().includes(needle));
  });
}

const modeOptions = ref([]);
function filterModes(fixture, value, update) {
  update(() => {
    const needle = value.toLowerCase();
    const current = graph.devices.find((d) => d.id === fixture.id) || fixture;
    modeOptions.value = modesForType(library.types, current.attributes.fixture_type)
      .map((m) => m.name)
      .filter((n) => n.toLowerCase().includes(needle));
  });
}

// A library mode brings its footprint; a name typed in for the first time is created in the
// library with the row's current footprint.
async function chooseMode(row, name) {
  const fixture = graph.devices.find((d) => d.id === row.id) || row;
  const mode = modesForType(library.types, fixture.attributes.fixture_type).find((m) => m.name === name);
  await save(fixture, {
    attributes: mode ? modeAttributes(mode) : { channel_mode: name || null },
  });
  library.fetch(props.jobId).catch(() => {});
}

async function save(node, changes) {
  try {
    await graph.updateDevice(props.jobId, node.id, changes);
  } catch (err) {
    if (err.response?.status !== 409) failed(err);
  }
}

async function addUniverse() {
  try {
    await graph.createUniverse(props.jobId, {});
  } catch (err) {
    failed(err);
  }
}

async function setSource(uni, deviceId) {
  try {
    await graph.setUniverseSource(props.jobId, uni.id, deviceId || null, uni.attributes.source_port || '');
  } catch (err) {
    failed(err);
  }
}

function openChain(uni) {
  chainNode.value = uni;
  chainInitial.value = chainForm(uni, graph.edges, graph.devices);
  chainOpen.value = true;
}

async function saveChain(steps) {
  try {
    await graph.replaceChain(props.jobId, 'universe', chainNode.value.id, steps);
    chainOpen.value = false;
  } catch (err) {
    failed(err);
  }
}

async function importFile(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  try {
    const result = await graph.importFixtures(props.jobId, file);
    $q.notify({
      type: result.errors?.length ? 'warning' : 'positive',
      message: t('workspace.imported', { n: result.created }),
    });
  } catch (err) {
    failed(err);
  }
}

async function addFixtures(count) {
  try {
    for (let i = 0; i < count; i += 1) {
      await graph.createFixture(props.jobId, { footprint: 1 });
    }
  } catch (err) {
    failed(err);
  }
}

onMounted(() => library.fetch(props.jobId).catch(() => {}));

function remove(fixture) {
  $q.dialog({ title: t('workspace.remove'), message: fixture.name, cancel: true, persistent: true }).onOk(
    async () => {
      try {
        await graph.deleteDevice(props.jobId, fixture.id);
      } catch (err) {
        if (err.response?.status !== 409) failed(err);
      }
    },
  );
}
</script>
