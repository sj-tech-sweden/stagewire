<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="col">
        <div class="text-h6">
          {{ t('lights.title') }}
        </div>
        <div class="text-caption text-grey-7">
          {{ t('lights.subtitle') }}
        </div>
      </div>
      <q-btn
        flat
        icon="upload_file"
        :label="t('lights.import')"
        @click="openImport"
      />
      <q-btn
        color="primary"
        icon="add"
        class="q-ml-sm"
        :label="t('lights.add')"
        @click="openNew"
      />
    </div>

    <div
      v-if="error"
      class="text-negative q-mb-md"
    >
      {{ error }}
    </div>
    <div
      v-if="loading"
      class="q-my-md"
    >
      <q-spinner color="primary" />
    </div>
    <div
      v-else-if="!fixtures.length"
      class="text-grey-7 q-pa-md text-center"
    >
      {{ t('lights.empty') }}
    </div>

    <q-list
      v-else-if="$q.screen.lt.sm"
      separator
    >
      <q-card
        v-for="f in fixtures"
        :key="f.id"
        flat
        bordered
        class="q-ma-xs q-pa-xs"
      >
        <q-card-section class="q-gutter-xs">
          <div class="row items-center justify-between">
            <div class="text-subtitle2">
              {{ addressLabel(f) }}
            </div>
            <q-btn
              flat
              dense
              round
              icon="edit"
              :aria-label="t('app.actions.edit')"
              @click="openEdit(f)"
            />
          </div>
          <div>{{ f.device_name || '—' }}</div>
          <div class="text-caption text-grey-7">
            {{ [f.fixture_type, f.channel_mode].filter(Boolean).join(' · ') || '—' }}
            <span v-if="f.footprint"> · {{ f.footprint }} ch</span>
          </div>
          <div class="text-caption">
            {{ [f.location, f.gel, f.purpose].filter(Boolean).join(' · ') || '—' }}
          </div>
          <div>
            <q-badge
              v-for="s in statusItems(f)"
              :key="s.label"
              :color="s.color"
              class="q-mr-xs"
            >
              {{ s.label }}
            </q-badge>
          </div>
        </q-card-section>
      </q-card>
    </q-list>

    <q-table
      v-else
      flat
      bordered
      dense
      hide-bottom
      row-key="id"
      :rows="fixtures"
      :columns="columns"
      :pagination="{ rowsPerPage: 0 }"
      @row-click="(_, row) => openEdit(row)"
    >
      <template #body-cell-status="cell">
        <q-td :props="cell">
          <q-badge
            v-for="s in statusItems(cell.row)"
            :key="s.label"
            :color="s.color"
            class="q-mr-xs"
          >
            {{ s.label }}
          </q-badge>
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 340px; max-width: 560px; width: 100%">
        <q-card-section class="text-h6">
          {{ editTarget ? t('lights.editTitle') : t('lights.newTitle') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model="form.device_name"
            :label="t('lights.deviceName')"
            :hint="t('lights.deviceHint')"
            dense
          />

          <div class="text-subtitle2 q-mt-sm">
            {{ t('lights.fixtureSection') }}
          </div>
          <q-select
            v-model="form.fixture_type_id"
            :options="typeOptions"
            :label="t('lights.fixtureType')"
            :hint="t('lights.typeHint')"
            emit-value
            map-options
            clearable
            use-input
            fill-input
            hide-selected
            input-debounce="0"
            dense
            new-value-mode="add-unique"
            @new-value="(val, done) => createType(val, done)"
            @update:model-value="onTypeChange"
          />
          <StockwireProductPicker
            :model-value="null"
            :label="t('lights.fromStockwire')"
            :hint="t('lights.fromStockwireHint')"
            @update:model-value="importFromStockwire"
          />
          <q-select
            v-model="form.fixture_mode_id"
            :options="modeOptions"
            :label="t('lights.mode')"
            :disable="!form.fixture_type_id"
            emit-value
            map-options
            clearable
            use-input
            fill-input
            hide-selected
            input-debounce="0"
            dense
            new-value-mode="add-unique"
            @new-value="(val, done) => createMode(val, done)"
            @update:model-value="onModeChange"
          />
          <div
            v-if="addressCheck.clashes.length || addressCheck.overflow"
            class="text-negative text-caption"
          >
            <span v-if="addressCheck.clashes.length">
              {{ t('lights.clashesWith', { names: addressClashNames }) }}
            </span>
            <span v-if="addressCheck.overflow">
              {{ t('lights.pastChannel512') }}
            </span>
          </div>
          <div class="row items-center q-gutter-sm">
            <span class="text-caption text-grey-7 col">
              {{ t('lights.gridEntry') }}
            </span>
            <q-btn
              flat
              dense
              icon="grid_view"
              :label="t('lights.pickChannel')"
              @click="gridOpen = true"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="form.footprint"
              type="number"
              min="1"
              max="512"
              dense
              class="col"
              :label="t('lights.footprint')"
            />
            <q-input
              v-model.number="form.universe"
              type="number"
              min="1"
              dense
              class="col"
              :label="t('lights.universe')"
            />
            <q-input
              v-model.number="form.dmx_address"
              type="number"
              min="1"
              max="512"
              dense
              class="col"
              :label="t('lights.address')"
            />
          </div>
          <div
            v-if="selectedType"
            class="row q-gutter-sm"
          >
            <q-input
              v-model.number="typeValues.weight_kg"
              type="number"
              min="0"
              step="0.1"
              dense
              class="col"
              :label="t('lights.typeWeight')"
              :hint="t('lights.typeValuesHint')"
              @blur="saveTypeValues"
            />
            <q-input
              v-model.number="typeValues.power_watts"
              type="number"
              min="0"
              step="1"
              dense
              class="col"
              :label="t('lights.typePower')"
              @blur="saveTypeValues"
            />
          </div>

          <div class="text-subtitle2 q-mt-sm">
            {{ t('lights.placement') }}
          </div>
          <div class="row q-gutter-sm">
            <q-select
              v-model="form.rigging_point_id"
              :options="pointOptions"
              :label="t('lights.truss')"
              emit-value
              map-options
              clearable
              dense
              class="col"
            />
            <q-select
              v-model="form.power_node_id"
              :options="nodeOptions"
              :label="t('lights.powerNode')"
              emit-value
              map-options
              clearable
              dense
              class="col"
              @update:model-value="form.power_connector = null"
            />
            <q-select
              v-model="form.power_connector"
              :options="connectorChoices"
              :label="t('lights.powerConnector')"
              :disable="!form.power_node_id"
              emit-value
              map-options
              clearable
              dense
              class="col"
            />
          </div>
          <q-input
            v-model="form.location"
            dense
            :label="t('lights.location')"
          />
          <q-input
            v-model="form.gel"
            dense
            :label="t('lights.gel')"
          />
          <q-input
            v-model="form.purpose"
            dense
            :label="t('lights.purpose')"
          />
          <q-input
            v-model="form.notes"
            type="textarea"
            autogrow
            dense
            :label="t('lights.notes')"
          />
        </q-card-section>
        <q-card-actions align="between">
          <q-btn
            v-if="editTarget"
            flat
            color="negative"
            icon="delete"
            :label="t('app.actions.delete')"
            @click="removeFixture"
          />
          <span v-else />
          <div>
            <q-btn
              v-close-popup
              flat
              :label="t('app.actions.cancel')"
            />
            <q-btn
              color="primary"
              :label="t('app.actions.save')"
              :loading="saving"
              @click="saveFixture"
            />
          </div>
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="gridOpen">
      <q-card style="min-width: 340px; max-width: 680px; width: 100%">
        <q-card-section class="text-h6">
          {{ t('lights.pickChannelTitle') }}
        </q-card-section>
        <q-card-section>
          <DmxGrid
            :model-value="form.dmx_address"
            :fixtures="fixtures"
            :universe="form.universe || 1"
            :footprint="form.footprint || 1"
            :exclude-id="editTarget?.id || null"
            :original-address="editTarget?.dmx_address ?? null"
            @update:model-value="pickFromGrid"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.close')"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="importDialog">
      <q-card style="min-width: 320px; max-width: 520px; width: 100%">
        <q-card-section class="text-h6">
          {{ t('lights.importTitle') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="text-caption">
            {{ t('lights.importHint') }}
          </div>
          <q-file
            v-model="importFile"
            accept=".csv,.mvr"
            dense
            outlined
            :label="t('lights.importTitle')"
          />
          <q-toggle
            v-model="clearImported"
            :label="t('lights.importClear')"
          />
          <div
            v-if="importErrors.length"
            class="text-negative text-caption"
          >
            {{ t('lights.importErrors') }}
            <div
              v-for="(line, i) in importErrors"
              :key="i"
            >
              {{ line }}
            </div>
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
            :label="t('lights.importRun')"
            :loading="importing"
            @click="runImport"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import DmxGrid from '@/components/DmxGrid.vue';
import { clashesFor, firstFreeAddress } from '@/utils/dmx';

const props = defineProps({
  jobId: { type: String, required: true },
});
const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const jobId = props.jobId;

const fixtures = ref([]);
const types = ref([]);
const points = ref([]);
const powerNodes = ref([]);
const loading = ref(false);
const error = ref('');

const editDialog = ref(false);
const gridOpen = ref(false);
const editTarget = ref(null);
const saving = ref(false);
const blankForm = () => ({
  device_name: '',
  fixture_type_id: null,
  fixture_mode_id: null,
  universe: null,
  dmx_address: null,
  footprint: null,
  rigging_point_id: null,
  power_node_id: null,
  power_connector: null,
  location: '',
  gel: '',
  purpose: '',
  notes: '',
});
const form = reactive(blankForm());
const typeValues = reactive({ weight_kg: null, power_watts: null });

const importDialog = ref(false);
const importFile = ref(null);
const clearImported = ref(true);
const importing = ref(false);
const importErrors = ref([]);

const columns = computed(() => [
  { name: 'universe', label: t('lights.colUniverse'), field: 'universe', align: 'left', format: (v) => v ?? '—' },
  { name: 'dmx_address', label: t('lights.colAddress'), field: 'dmx_address', align: 'left', format: (v) => v ?? '—' },
  { name: 'device_name', label: t('lights.colDevice'), field: 'device_name', align: 'left', format: (v) => v || '—' },
  { name: 'fixture_type', label: t('lights.colFixtureType'), field: 'fixture_type', align: 'left' },
  { name: 'channel_mode', label: t('lights.colChannelMode'), field: 'channel_mode', align: 'left' },
  { name: 'footprint', label: t('lights.colFootprint'), field: 'footprint', align: 'left', format: (v) => v ?? '—' },
  { name: 'location', label: t('lights.colLocation'), field: 'location', align: 'left' },
  { name: 'gel', label: t('lights.colGel'), field: 'gel', align: 'left' },
  { name: 'purpose', label: t('lights.colPurpose'), field: 'purpose', align: 'left' },
  { name: 'status', label: t('lights.colStatus'), field: 'status', align: 'left' },
]);

const typeOptions = computed(() => types.value.map((ft) => ({ value: ft.id, label: ft.name })));
const selectedType = computed(() => types.value.find((ft) => ft.id === form.fixture_type_id) || null);
const modeOptions = computed(() =>
  (selectedType.value?.modes || []).map((m) => ({
    value: m.id,
    label: `${m.name} · ${m.footprint} ch`,
  })),
);
const pointOptions = computed(() => points.value.map((p) => ({ value: p.id, label: p.name || '—' })));
const nodeOptions = computed(() => powerNodes.value.map((n) => ({ value: n.id, label: n.name || '—' })));
const connectorChoices = computed(() => {
  const node = powerNodes.value.find((n) => n.id === form.power_node_id);
  return (node?.outputs || []).map((o) => ({
    value: o.connector,
    label: `${o.connector} · ${o.count}×${o.phase ? ' ' + o.phase : ''}`,
  }));
});

function addressLabel(f) {
  return `U${f.universe ?? '—'} · ${f.dmx_address ?? '—'}`;
}

function statusItems(f) {
  const items = [];
  if (f.dmx_conflict) items.push({ label: t('lights.conflict'), color: 'negative' });
  if (f.dmx_overflow) items.push({ label: t('lights.overflow'), color: 'warning' });
  return items;
}

async function fetchAll() {
  loading.value = true;
  error.value = '';
  try {
    const [fixturesRes, typesRes, summaryRes, nodesRes] = await Promise.all([
      api.get(`/jobs/${jobId}/fixtures`),
      api.get(`/jobs/${jobId}/fixture-types`),
      api.get(`/jobs/${jobId}/rigging/summary`),
      api.get(`/jobs/${jobId}/power-nodes`),
    ]);
    fixtures.value = fixturesRes.data;
    types.value = typesRes.data;
    points.value = summaryRes.data.points;
    powerNodes.value = nodesRes.data;
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  } finally {
    loading.value = false;
  }
}

async function reloadTypes() {
  const { data } = await api.get(`/jobs/${jobId}/fixture-types`);
  types.value = data;
}

// A new fixture takes the first free address of its universe. The suggestion follows
// universe and footprint changes until the address is set to something other than it.
let lastSuggestion = null;

function suggestAddress() {
  if (editTarget.value) return;
  if (form.dmx_address !== null && form.dmx_address !== lastSuggestion) return;
  lastSuggestion = firstFreeAddress(fixtures.value, form.universe || 1, form.footprint || 1) ?? null;
  form.dmx_address = lastSuggestion;
}

// The overlap of the address in the form, shown before saving.
const addressCheck = computed(() =>
  clashesFor(
    fixtures.value,
    form.universe || 1,
    form.dmx_address,
    form.footprint || 1,
    editTarget.value?.id || null,
  ),
);
const addressClashNames = computed(() =>
  addressCheck.value.clashes
    .map((f) => `${f.device_name || t('lights.fixtureSection')} (${f.dmx_address}–${f.dmx_address + (f.footprint || 1) - 1})`)
    .join(', '),
);

function pickFromGrid(address) {
  form.dmx_address = address;
  gridOpen.value = false;
}

watch(() => [form.universe, form.footprint, fixtures.value], suggestAddress);

function openNew() {
  editTarget.value = null;
  Object.assign(form, blankForm());
  lastSuggestion = null;
  suggestAddress();
  syncTypeValues();
  editDialog.value = true;
}

function openEdit(f) {
  editTarget.value = f;
  Object.assign(form, {
    device_name: f.device_name || '',
    fixture_type_id: f.fixture_type_id ?? null,
    fixture_mode_id: f.fixture_mode_id ?? null,
    universe: f.universe ?? null,
    dmx_address: f.dmx_address ?? null,
    footprint: f.footprint ?? null,
    rigging_point_id: f.rigging_point_id ?? null,
    power_node_id: f.power_node_id ?? null,
    power_connector: f.power_connector || null,
    location: f.location || '',
    gel: f.gel || '',
    purpose: f.purpose || '',
    notes: f.notes || '',
  });
  syncTypeValues();
  editDialog.value = true;
}

function syncTypeValues() {
  typeValues.weight_kg = selectedType.value?.weight_kg ?? null;
  typeValues.power_watts = selectedType.value?.power_watts ?? null;
}

function onTypeChange() {
  form.fixture_mode_id = null;
  syncTypeValues();
}

function onModeChange(modeId) {
  const mode = selectedType.value?.modes.find((m) => m.id === modeId);
  if (mode) form.footprint = mode.footprint;
}

function failed(err) {
  $q.notify({ type: 'negative', message: err.response?.data?.detail || t('common.errorOccurred') });
}

// A type or mode typed in a select is created by a request; saving waits for it so the new
// value is part of the fixture.
let pendingCreate = Promise.resolve();

function createType(name, done) {
  const trimmed = String(name || '').trim();
  if (!trimmed) return;
  pendingCreate = pendingCreate.then(async () => {
    try {
      const { data } = await api.post(`/jobs/${jobId}/fixture-types`, { name: trimmed });
      await reloadTypes();
      form.fixture_type_id = data.id;
      form.fixture_mode_id = null;
      done(data.id, 'add-unique');
    } catch (err) {
      failed(err);
    }
  });
}

function createMode(name, done) {
  const trimmed = String(name || '').trim();
  const typeId = selectedType.value?.id;
  if (!trimmed || !typeId) return;
  if (!form.footprint) {
    $q.notify({ type: 'warning', message: t('lights.footprintFirst') });
    return;
  }
  const footprint = form.footprint;
  pendingCreate = pendingCreate.then(async () => {
    try {
      const { data } = await api.post(`/jobs/${jobId}/fixture-types/${typeId}/modes`, {
        name: trimmed,
        footprint,
      });
      await reloadTypes();
      form.fixture_mode_id = data.id;
      done(data.id, 'add-unique');
    } catch (err) {
      failed(err);
    }
  });
}

async function importFromStockwire(product) {
  if (!product?.id) return;
  try {
    const { data } = await api.post(`/jobs/${jobId}/fixture-types/from-stockwire`, {
      product_id: String(product.id),
    });
    await reloadTypes();
    form.fixture_type_id = data.id;
    form.fixture_mode_id = null;
    syncTypeValues();
    $q.notify({ type: 'positive', message: t('lights.fromStockwireDone', { name: data.name }) });
  } catch (err) {
    failed(err);
  }
}

async function saveTypeValues() {
  if (!selectedType.value) return;
  try {
    await api.patch(`/jobs/${jobId}/fixture-types/${selectedType.value.id}`, {
      weight_kg: typeValues.weight_kg || null,
      power_watts: typeValues.power_watts || null,
    });
    await reloadTypes();
  } catch (err) {
    failed(err);
  }
}

function payload() {
  return {
    ...form,
    device_name: form.device_name?.trim() || null,
    universe: form.universe || null,
    dmx_address: form.dmx_address || null,
    footprint: form.footprint || null,
  };
}

async function saveFixture() {
  saving.value = true;
  await pendingCreate;
  try {
    if (editTarget.value) {
      await api.patch(`/jobs/${jobId}/fixtures/${editTarget.value.id}`, payload());
    } else {
      await api.post(`/jobs/${jobId}/fixtures`, payload());
    }
    editDialog.value = false;
    $q.notify({ type: 'positive', message: t('lights.saved') });
    await fetchAll();
  } catch (err) {
    failed(err);
  } finally {
    saving.value = false;
  }
}

function removeFixture() {
  if (!editTarget.value) return;
  $q.dialog({
    title: t('app.actions.delete'),
    message: t('lights.deleteConfirm'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    await api.delete(`/jobs/${jobId}/fixtures/${editTarget.value.id}`);
    editDialog.value = false;
    $q.notify({ type: 'positive', message: t('lights.deleted') });
    await fetchAll();
  });
}

function openImport() {
  importFile.value = null;
  importErrors.value = [];
  importDialog.value = true;
}

async function runImport() {
  if (!importFile.value) {
    $q.notify({ type: 'warning', message: t('lights.importNeedFile') });
    return;
  }
  importing.value = true;
  importErrors.value = [];
  try {
    const body = new FormData();
    body.append('file', importFile.value);
    const { data } = await api.post(`/jobs/${jobId}/fixtures/import`, body, {
      params: { clear_imported: clearImported.value },
    });
    importErrors.value = data.errors || [];
    $q.notify({
      type: 'positive',
      message: t('lights.importDone', {
        created: data.created,
        devices: data.devices_created,
        cleared: data.cleared,
      }),
    });
    await fetchAll();
    if (!importErrors.value.length) importDialog.value = false;
  } catch (err) {
    failed(err);
  } finally {
    importing.value = false;
  }
}

onMounted(fetchAll);
</script>
