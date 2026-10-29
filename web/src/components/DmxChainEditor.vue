<template>
  <div class="q-mt-lg">
    <div class="row items-center q-mb-sm">
      <div class="text-subtitle1">
        {{ t('dmxChain.title') }}
      </div>
      <q-space />
      <q-btn
        color="primary"
        icon="add"
        dense
        no-caps
        :label="t('dmxChain.addUniverse')"
        @click="openUniverse(null)"
      />
    </div>
    <div class="text-caption text-grey-7 q-mb-sm">
      {{ t('dmxChain.subtitle') }}
    </div>

    <div
      v-if="error"
      class="text-negative q-mb-sm"
    >
      {{ error }}
    </div>
    <q-spinner
      v-if="loading"
      color="primary"
    />
    <div
      v-else-if="!universes.length"
      class="text-grey-7 q-pa-sm"
    >
      {{ t('dmxChain.noUniverses') }}
    </div>

    <q-card
      v-for="u in universes"
      :key="u.id"
      flat
      bordered
      class="q-mb-sm"
    >
      <q-card-section class="q-gutter-xs">
        <div class="row items-center">
          <div class="text-subtitle2">
            Uni {{ u.number }}<span v-if="u.name"> · {{ u.name }}</span>
          </div>
          <q-space />
          <q-btn
            flat
            dense
            round
            icon="edit"
            :aria-label="t('app.actions.edit')"
            @click="openUniverse(u)"
          />
          <q-btn
            flat
            dense
            round
            icon="delete"
            color="negative"
            :aria-label="t('dmxChain.deleteUniverse')"
            @click="removeUniverse(u)"
          />
        </div>
        <div class="row items-center q-gutter-xs text-caption text-grey-7">
          <span>{{ t('dmxChain.source') }}: {{ u.source_label || '—' }}</span>
          <span v-if="u.source_port">· {{ u.source_port }}</span>
        </div>
        <q-separator class="q-my-xs" />
        <div
          v-if="!u.steps.length"
          class="text-caption text-grey-7"
        >
          {{ t('dmxChain.noSteps') }}
        </div>
        <DmxFlowDiagram
          :steps="u.steps"
          :universe-number="u.number"
          @edit="openStep(u, null, $event)"
          @add-child="openStep(u, $event)"
          @delete="removeStep(u, $event)"
        />
        <q-btn
          flat
          dense
          no-caps
          icon="add"
          class="q-mt-xs"
          :label="t('dmxChain.addStep')"
          @click="openStep(u, null)"
        />
      </q-card-section>
    </q-card>

    <q-dialog v-model="universeDialog">
      <q-card style="min-width: 320px; max-width: 520px; width: 100%">
        <q-card-section class="text-h6">
          {{ universeTarget ? t('app.actions.edit') : t('dmxChain.newUniverse') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model.number="universeForm.number"
            type="number"
            min="1"
            dense
            :label="t('dmxChain.number')"
          />
          <q-input
            v-model="universeForm.name"
            dense
            :label="t('dmxChain.universeName')"
          />
          <q-select
            v-model="universeForm.source_device_id"
            :options="deviceOptions"
            emit-value
            map-options
            clearable
            dense
            :label="t('dmxChain.source')"
          />
          <q-input
            v-model="universeForm.source_port"
            dense
            :label="t('dmxChain.sourcePort')"
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
            :disable="!universeForm.number"
            @click="saveUniverse"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="stepDialog">
      <q-card style="min-width: 320px; max-width: 520px; width: 100%">
        <q-card-section class="text-h6">
          {{ stepTarget ? t('app.actions.edit') : t('dmxChain.newStep') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-select
            v-model="stepForm.parent_id"
            :options="stepParentOptions"
            emit-value
            map-options
            clearable
            dense
            :label="t('dmxChain.parent')"
          />
          <q-btn-toggle
            v-model="stepForm.kind"
            dense
            no-caps
            toggle-color="primary"
            :options="[
              { label: t('dmxChain.kindFixture'), value: 'fixture' },
              { label: t('dmxChain.kindDevice'), value: 'device' },
            ]"
          />
          <q-select
            v-if="stepForm.kind === 'fixture'"
            v-model="stepForm.fixture_id"
            :options="availableFixtureOptions"
            emit-value
            map-options
            clearable
            dense
            :label="t('dmxChain.stepFixture')"
          />
          <template v-else>
            <q-select
              v-model="stepForm.device_id"
              :options="availableDeviceOptions"
              emit-value
              map-options
              clearable
              dense
              :label="t('dmxChain.stepDevice')"
            />
            <div class="row items-center q-gutter-xs">
              <q-btn
                v-if="!newDevice.open"
                flat
                dense
                no-caps
                icon="add"
                :label="t('dmxChain.newDevice')"
                @click="newDevice.open = true"
              />
              <template v-else>
                <q-input
                  v-model="newDevice.name"
                  dense
                  class="col"
                  :label="t('dmxChain.deviceName')"
                  @keyup.enter="createDevice"
                />
                <q-select
                  v-model="newDevice.device_type"
                  :options="deviceTypeOptions"
                  use-input
                  new-value-mode="add"
                  dense
                  clearable
                  class="col"
                  :label="t('dmxChain.deviceType')"
                />
                <q-btn
                  flat
                  dense
                  icon="check"
                  color="primary"
                  :aria-label="t('dmxChain.confirmDevice')"
                  :disable="!newDevice.name"
                  @click="createDevice"
                />
                <q-btn
                  flat
                  dense
                  icon="close"
                  :aria-label="t('app.actions.cancel')"
                  @click="newDevice.open = false"
                />
              </template>
            </div>
          </template>
          <div class="row q-gutter-sm">
            <q-input
              v-model="stepForm.in_port"
              dense
              class="col"
              :label="t('dmxChain.inPort')"
            />
            <q-input
              v-model="stepForm.out_port"
              dense
              class="col"
              :label="t('dmxChain.outPort')"
            />
          </div>
          <q-input
            v-model="stepForm.connector"
            dense
            :label="t('dmxChain.connector')"
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
            :disable="!stepValid"
            @click="saveStep"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { api } from '@/boot/api';
import DmxFlowDiagram from '@/components/DmxFlowDiagram.vue';

const props = defineProps({
  jobId: { type: String, required: true },
});

const { t } = useI18n();

const universes = ref([]);
const devices = ref([]);
const fixtures = ref([]);
const loading = ref(false);
const error = ref('');

const deviceOptions = computed(() =>
  devices.value.map((d) => ({ value: d.id, label: d.name || d.device_type || '—' })),
);
const fixtureOptions = computed(() =>
  fixtures.value.map((f) => ({ value: f.id, label: f.device_name || t('dmxChain.kindFixture') })),
);

// Fixtures/devices already used as steps in the active universe are hidden
// from the add-step picker so the same device cannot be added twice.
// A DMX step serialises a fixture's `device_id` (not its fixture id), so we
// map the used device ids back to fixture ids to filter the fixture picker.
const fixtureIdByDevice = computed(() => {
  const m = {};
  for (const f of fixtures.value) m[f.device_id] = f.id;
  return m;
});
const usedFixtureIds = computed(() => {
  const set = new Set();
  if (activeUniverse.value) {
    for (const s of flatten(activeUniverse.value.steps)) {
      if (s.kind === 'fixture' && s.device_id) {
        const fid = fixtureIdByDevice.value[s.device_id];
        if (fid) set.add(fid);
      }
    }
  }
  return set;
});
const usedDeviceIds = computed(() => {
  const set = new Set();
  if (activeUniverse.value) {
    for (const s of flatten(activeUniverse.value.steps)) {
      if (s.kind === 'device' && s.device_id) set.add(s.device_id);
    }
  }
  return set;
});

const availableFixtureOptions = computed(() => {
  const current = stepTarget.value?.kind === 'fixture' ? fixtureIdByDevice.value[stepTarget.value.device_id] : null;
  return fixtureOptions.value.filter((o) => !usedFixtureIds.value.has(o.value) || o.value === current);
});
const availableDeviceOptions = computed(() => {
  const current = stepTarget.value?.kind === 'device' ? stepTarget.value.device_id : null;
  return deviceOptions.value.filter((o) => !usedDeviceIds.value.has(o.value) || o.value === current);
});

async function loadAll() {
  loading.value = true;
  error.value = '';
  try {
    const [uRes, dRes, fRes] = await Promise.all([
      api.get(`/jobs/${props.jobId}/dmx-universes`),
      api.get(`/jobs/${props.jobId}/devices`),
      api.get(`/jobs/${props.jobId}/fixtures`),
    ]);
    universes.value = uRes.data;
    devices.value = dRes.data;
    fixtures.value = fRes.data;
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  } finally {
    loading.value = false;
  }
}

onMounted(loadAll);

function flatten(steps, acc = []) {
  for (const s of steps) {
    acc.push(s);
    flatten(s.children || [], acc);
  }
  return acc;
}

// Steps below `id` plus `id` itself, so a step cannot be moved under its own branch.
function blockedIds(steps, id) {
  const flat = flatten(steps);
  const blocked = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const s of flat) {
      if (s.parent_id && blocked.has(s.parent_id) && !blocked.has(s.id)) {
        blocked.add(s.id);
        grew = true;
      }
    }
  }
  return blocked;
}

const universeDialog = ref(false);
const universeTarget = ref(null);
const universeForm = reactive({ number: 1, name: '', source_device_id: null, source_port: '' });

function openUniverse(u) {
  universeTarget.value = u;
  universeForm.number = u ? u.number : (universes.value.at(-1)?.number || 0) + 1;
  universeForm.name = u ? u.name || '' : '';
  universeForm.source_device_id = u ? u.source_device_id || null : null;
  universeForm.source_port = u ? u.source_port || '' : '';
  universeDialog.value = true;
}

async function saveUniverse() {
  const body = {
    number: universeForm.number,
    name: universeForm.name,
    source_device_id: universeForm.source_device_id || null,
    source_port: universeForm.source_port,
  };
  try {
    if (universeTarget.value) {
      await api.patch(`/jobs/${props.jobId}/dmx-universes/${universeTarget.value.id}`, body);
    } else {
      await api.post(`/jobs/${props.jobId}/dmx-universes`, body);
    }
    universeDialog.value = false;
    await loadAll();
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  }
}

async function removeUniverse(u) {
  if (!confirm(t('dmxChain.deleteUniverseConfirm'))) return;
  try {
    await api.delete(`/jobs/${props.jobId}/dmx-universes/${u.id}`);
    await loadAll();
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  }
}

const stepDialog = ref(false);
const stepTarget = ref(null);
const activeUniverse = ref(null);
const stepForm = reactive({
  parent_id: null,
  kind: 'fixture',
  device_id: null,
  fixture_id: null,
  in_port: '',
  out_port: '',
  connector: '',
});

const deviceTypeOptions = ['split', 'distro', 'processor', 'node', 'other'];
const newDevice = reactive({ open: false, name: '', device_type: 'split' });

async function createDevice() {
  if (!newDevice.name) return;
  try {
    const res = await api.post(`/jobs/${props.jobId}/devices`, {
      name: newDevice.name,
      device_type: newDevice.device_type || 'other',
    });
    await loadAll();
    stepForm.device_id = res.data.id;
    newDevice.open = false;
    newDevice.name = '';
    newDevice.device_type = 'split';
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  }
}

const stepParentOptions = computed(() => {
  const opts = [{ value: null, label: t('dmxChain.root') }];
  if (!activeUniverse.value) return opts;
  const blocked = stepTarget.value ? blockedIds(activeUniverse.value.steps, stepTarget.value.id) : new Set();
  for (const s of flatten(activeUniverse.value.steps)) {
    if (blocked.has(s.id)) continue;
    opts.push({ value: s.id, label: s.label || (s.kind === 'fixture' ? t('dmxChain.kindFixture') : t('dmxChain.kindDevice')) });
  }
  return opts;
});

const stepValid = computed(() => {
  if (stepForm.kind === 'fixture') return !!stepForm.fixture_id;
  return !!stepForm.device_id;
});

function openStep(u, parentId, step) {
  activeUniverse.value = u;
  stepTarget.value = step || null;
  stepForm.parent_id = step ? step.parent_id || null : parentId || null;
  stepForm.kind = step ? (step.kind === 'fixture' ? 'fixture' : 'device') : 'fixture';
  stepForm.device_id = step ? (step.kind === 'device' ? step.device_id : null) : null;
  stepForm.fixture_id = step ? (step.kind === 'fixture' ? step.device_id : null) : null;
  stepForm.in_port = step ? step.in_port || '' : '';
  stepForm.out_port = step ? step.out_port || '' : '';
  stepForm.connector = step ? step.connector || '' : '';
  stepDialog.value = true;
}

async function saveStep() {
  const body = {
    parent_id: stepForm.parent_id || null,
    device_id: stepForm.kind === 'device' ? stepForm.device_id || null : null,
    fixture_id: stepForm.kind === 'fixture' ? stepForm.fixture_id || null : null,
    in_port: stepForm.in_port,
    out_port: stepForm.out_port,
    connector: stepForm.connector,
  };
  try {
    if (stepTarget.value) {
      await api.patch(
        `/jobs/${props.jobId}/dmx-universes/${activeUniverse.value.id}/steps/${stepTarget.value.id}`,
        body,
      );
    } else {
      await api.post(`/jobs/${props.jobId}/dmx-universes/${activeUniverse.value.id}/steps`, body);
    }
    // Link the fixture's universe to the chain's universe so the selector in the
    // fixture patch reflects where it now lives in the DMX chain.
    if (stepForm.kind === 'fixture' && stepForm.fixture_id) {
      await api.patch(`/jobs/${props.jobId}/fixtures/${stepForm.fixture_id}`, {
        universe: activeUniverse.value.number,
      });
    }
    stepDialog.value = false;
    await loadAll();
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  }
}

async function removeStep(u, step) {
  if (!confirm(t('dmxChain.deleteStepConfirm'))) return;
  try {
    await api.delete(`/jobs/${props.jobId}/dmx-universes/${u.id}/steps/${step.id}`);
    await loadAll();
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  }
}
</script>
