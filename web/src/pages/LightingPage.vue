<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('channels.backToJobs')"
        class="q-mr-sm"
        @click="goBackToJob"
      />
      <div class="col">
        <div class="text-h5">
          {{ t('lights.title') }}
        </div>
        <div
          v-if="job"
          class="text-subtitle2 text-grey-7"
        >
          {{ job.title }}<span v-if="job.venue_name"> · {{ job.venue_name }}</span>
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
      <q-card style="min-width: 320px; max-width: 520px; width: 100%">
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
          <div class="row q-gutter-sm">
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
          <div class="row q-gutter-sm">
            <q-input
              v-model="form.fixture_type"
              dense
              class="col"
              :label="t('lights.colFixtureType')"
            />
            <q-input
              v-model="form.channel_mode"
              dense
              class="col"
              :label="t('lights.colChannelMode')"
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
              v-model="form.gel"
              dense
              class="col"
              :label="t('lights.gel')"
            />
          </div>
          <q-input
            v-model="form.location"
            dense
            :label="t('lights.location')"
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
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useRoute, useRouter } from 'vue-router';
import { api } from '@/boot/api';

const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const route = useRoute();
const router = useRouter();
const jobId = route.params.jobId;

const job = ref(null);
const fixtures = ref([]);
const loading = ref(false);
const error = ref('');

const editDialog = ref(false);
const editTarget = ref(null);
const saving = ref(false);
const blankForm = () => ({
  device_name: '',
  universe: null,
  dmx_address: null,
  fixture_type: '',
  channel_mode: '',
  footprint: null,
  location: '',
  gel: '',
  purpose: '',
  notes: '',
});
const form = reactive(blankForm());

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

function addressLabel(f) {
  const universe = f.universe ?? '—';
  const address = f.dmx_address ?? '—';
  return `U${universe} · ${address}`;
}

function statusItems(f) {
  const items = [];
  if (f.dmx_conflict) items.push({ label: t('lights.conflict'), color: 'negative' });
  if (f.dmx_overflow) items.push({ label: t('lights.overflow'), color: 'warning' });
  return items;
}

function goBackToJob() {
  router.push({ path: `/jobs/${jobId}`, query: route.query.from === 'video' ? { view: 'video' } : {} });
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [jobRes, fixturesRes] = await Promise.all([
      api.get(`/jobs/${jobId}`),
      api.get(`/jobs/${jobId}/fixtures`),
    ]);
    job.value = jobRes.data;
    fixtures.value = fixturesRes.data;
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  } finally {
    loading.value = false;
  }
}

function openNew() {
  editTarget.value = null;
  Object.assign(form, blankForm());
  editDialog.value = true;
}

function openEdit(f) {
  editTarget.value = f;
  Object.assign(form, {
    device_name: f.device_name || '',
    universe: f.universe ?? null,
    dmx_address: f.dmx_address ?? null,
    fixture_type: f.fixture_type || '',
    channel_mode: f.channel_mode || '',
    footprint: f.footprint ?? null,
    location: f.location || '',
    gel: f.gel || '',
    purpose: f.purpose || '',
    notes: f.notes || '',
  });
  editDialog.value = true;
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
  try {
    if (editTarget.value) {
      await api.patch(`/jobs/${jobId}/fixtures/${editTarget.value.id}`, payload());
    } else {
      await api.post(`/jobs/${jobId}/fixtures`, payload());
    }
    editDialog.value = false;
    $q.notify({ type: 'positive', message: t('lights.saved') });
    await load();
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('common.errorOccurred') });
  } finally {
    saving.value = false;
  }
}

async function removeFixture() {
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
    await load();
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
    await load();
    if (!importErrors.value.length) importDialog.value = false;
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('common.errorOccurred') });
  } finally {
    importing.value = false;
  }
}

onMounted(load);
</script>
