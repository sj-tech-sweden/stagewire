<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="col text-h6">
        {{ t('rigging.title') }}
      </div>
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

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-6">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('rigging.trusses') }}
            </div>
            <div
              v-if="!summary?.points?.length"
              class="text-grey-7 q-mb-sm"
            >
              {{ t('rigging.noTrusses') }}
            </div>
            <div
              v-for="point in summary?.points || []"
              :key="point.id"
              class="q-mb-md"
            >
              <div class="row items-center">
                <div class="col text-body2">
                  {{ point.name || '—' }}
                  <span class="text-caption text-grey-7">
                    · {{ point.load_kg }} / {{ point.weight_capacity_kg ?? '—' }} kg
                  </span>
                </div>
                <q-badge
                  v-if="point.over"
                  color="negative"
                >
                  {{ t('rigging.over') }}
                </q-badge>
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('app.actions.delete')"
                  @click="removePoint(point)"
                />
              </div>
              <q-linear-progress
                v-if="point.percent !== null"
                :value="Math.min(point.percent / 100, 1)"
                :color="point.over ? 'negative' : 'positive'"
                size="8px"
                class="q-mt-xs"
              />
            </div>
            <div class="row q-gutter-sm items-end">
              <q-input
                v-model="newPoint.name"
                :label="t('rigging.trussName')"
                dense
                class="col"
              />
              <q-input
                v-model.number="newPoint.weight_capacity_kg"
                type="number"
                min="0"
                :label="t('rigging.capacity')"
                dense
                style="max-width: 120px"
              />
              <q-btn
                color="primary"
                icon="add"
                :label="t('rigging.addTruss')"
                :disable="!newPoint.name.trim()"
                @click="addPoint"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-6">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('rigging.distros') }}
            </div>
            <div
              v-if="!summary?.distros?.length"
              class="text-grey-7 q-mb-sm"
            >
              {{ t('rigging.noDistros') }}
            </div>
            <div
              v-for="distro in summary?.distros || []"
              :key="distro.id"
              class="q-mb-md"
            >
              <div class="row items-center">
                <div class="col text-body2">
                  {{ distro.name || '—' }}
                  <span class="text-caption text-grey-7">
                    · {{ distro.voltage }} V {{ t('rigging.phaseToNeutral') }} · {{ t('rigging.imbalance') }} {{ distro.imbalance_pct }}%
                  </span>
                </div>
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('app.actions.delete')"
                  @click="removeDistro(distro)"
                />
              </div>
              <q-markup-table
                flat
                dense
                class="q-mt-xs"
              >
                <thead>
                  <tr>
                    <th class="text-left">
                      {{ t('rigging.phase') }}
                    </th>
                    <th class="text-right">
                      {{ t('rigging.watts') }}
                    </th>
                    <th class="text-right">
                      {{ t('rigging.amps') }}
                    </th>
                    <th class="text-right">
                      {{ t('rigging.capacity') }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(phase, name) in distro.phases"
                    :key="name"
                    :class="phase.over ? 'text-negative' : ''"
                  >
                    <td>{{ name }}</td>
                    <td class="text-right">
                      {{ phase.watts }}
                    </td>
                    <td class="text-right">
                      {{ phase.amps }}
                    </td>
                    <td class="text-right">
                      {{ phase.capacity_amps ?? '—' }}
                    </td>
                  </tr>
                </tbody>
              </q-markup-table>
              <div
                v-for="circuit in distro.circuits"
                :key="circuit.id"
                class="row items-center q-mt-xs text-caption"
                :class="circuit.over ? 'text-negative' : ''"
              >
                <div class="col">
                  {{ circuit.label || '—' }} · {{ circuitPhaseLabel(circuit) }} · {{ circuit.amps }} A
                  <span v-if="circuit.breaker_amps">/ {{ circuit.breaker_amps }} A</span>
                </div>
                <q-btn
                  flat
                  dense
                  round
                  size="sm"
                  icon="delete"
                  color="negative"
                  :aria-label="t('app.actions.delete')"
                  @click="removeCircuit(circuit)"
                />
              </div>
              <div class="row q-gutter-xs items-end q-mt-xs">
                <q-input
                  v-model="newCircuit[distro.id].label"
                  :label="t('rigging.circuitLabel')"
                  dense
                  class="col"
                />
                <q-select
                  v-model="newCircuit[distro.id].phases"
                  :options="phasesOptions"
                  :label="t('rigging.circuitType')"
                  emit-value
                  map-options
                  dense
                  style="min-width: 110px"
                />
                <q-select
                  v-if="newCircuit[distro.id].phases === 1"
                  v-model="newCircuit[distro.id].phase"
                  :options="phaseOptions"
                  :label="t('rigging.phase')"
                  emit-value
                  map-options
                  dense
                  style="min-width: 90px"
                />
                <q-input
                  v-model.number="newCircuit[distro.id].breaker_amps"
                  type="number"
                  min="0"
                  :label="t('rigging.breaker')"
                  dense
                  style="max-width: 100px"
                />
                <q-btn
                  flat
                  dense
                  icon="add"
                  :label="t('rigging.addCircuit')"
                  @click="addCircuit(distro)"
                />
              </div>
            </div>
            <div class="row q-gutter-sm items-end">
              <q-input
                v-model="newDistro.name"
                :label="t('rigging.distroName')"
                dense
                class="col"
              />
              <q-input
                v-model.number="newDistro.amps_per_phase"
                type="number"
                min="0"
                :label="t('rigging.ampsPerPhase')"
                dense
                style="max-width: 120px"
              />
              <q-btn
                color="primary"
                icon="add"
                :label="t('rigging.addDistro')"
                :disable="!newDistro.name.trim()"
                @click="addDistro"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-xs">
              {{ t('rigging.loads') }}
            </div>
            <div class="text-caption text-grey-7 q-mb-sm">
              {{ t('rigging.loadsHint') }}
            </div>
            <div
              v-if="!loads.length"
              class="text-grey-7"
            >
              {{ t('rigging.noLoads') }}
            </div>
            <q-list
              v-else-if="$q.screen.lt.sm"
              separator
            >
              <q-item
                v-for="load in loads"
                :key="load.kind + load.id"
                class="q-px-none"
              >
                <q-item-section>
                  <div class="text-body2">
                    {{ load.label }}
                  </div>
                  <div class="text-caption text-grey-7">
                    {{ load.weight_kg ?? '—' }} kg · {{ load.power_w ?? '—' }} W
                  </div>
                  <q-select
                    :model-value="load.rigging_point_id"
                    :options="pointOptions"
                    :label="t('rigging.truss')"
                    emit-value
                    map-options
                    clearable
                    dense
                    @update:model-value="(v) => assign(load, { rigging_point_id: v })"
                  />
                  <q-select
                    :model-value="load.power_circuit_id"
                    :options="circuitOptions"
                    :label="t('rigging.circuit')"
                    emit-value
                    map-options
                    clearable
                    dense
                    @update:model-value="(v) => assign(load, { power_circuit_id: v })"
                  />
                </q-item-section>
              </q-item>
            </q-list>
            <q-markup-table
              v-else
              flat
              dense
            >
              <thead>
                <tr>
                  <th class="text-left">
                    {{ t('rigging.colLoad') }}
                  </th>
                  <th class="text-right">
                    {{ t('rigging.colWeight') }}
                  </th>
                  <th class="text-right">
                    {{ t('rigging.colPower') }}
                  </th>
                  <th class="text-left">
                    {{ t('rigging.truss') }}
                  </th>
                  <th class="text-left">
                    {{ t('rigging.circuit') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="load in loads"
                  :key="load.kind + load.id"
                >
                  <td>{{ load.label }}</td>
                  <td class="text-right">
                    {{ load.weight_kg ?? '—' }}
                  </td>
                  <td class="text-right">
                    {{ load.power_w ?? '—' }}
                  </td>
                  <td>
                    <q-select
                      :model-value="load.rigging_point_id"
                      :options="pointOptions"
                      emit-value
                      map-options
                      clearable
                      dense
                      borderless
                      style="min-width: 160px"
                      @update:model-value="(v) => assign(load, { rigging_point_id: v })"
                    />
                  </td>
                  <td>
                    <q-select
                      :model-value="load.power_circuit_id"
                      :options="circuitOptions"
                      emit-value
                      map-options
                      clearable
                      dense
                      borderless
                      style="min-width: 180px"
                      @update:model-value="(v) => assign(load, { power_circuit_id: v })"
                    />
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
            <div
              v-if="summary?.unassigned_weight?.length"
              class="text-caption q-mt-sm"
            >
              {{ t('rigging.unassignedWeight') }}: {{ summary.unassigned_weight.join(', ') }}
            </div>
            <div
              v-if="summary?.unassigned_power?.length"
              class="text-caption"
            >
              {{ t('rigging.unassignedPower') }}: {{ summary.unassigned_power.join(', ') }}
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';

const props = defineProps({
  jobId: { type: String, required: true },
});
const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const jobId = props.jobId;

const summary = ref(null);
const loads = ref([]);
const loading = ref(false);
const error = ref('');

const newPoint = reactive({ name: '', weight_capacity_kg: null });
const newDistro = reactive({ name: '', amps_per_phase: null });
const newCircuit = reactive({});

const phaseOptions = [
  { value: 'L1', label: 'L1' },
  { value: 'L2', label: 'L2' },
  { value: 'L3', label: 'L3' },
];
const phasesOptions = [
  { value: 1, label: t('rigging.singlePhase') },
  { value: 3, label: t('rigging.threePhase') },
];
function circuitPhaseLabel(circuit) {
  return circuit.phases === 3 ? t('rigging.threePhaseShort') : circuit.phase;
}

const pointOptions = computed(() =>
  (summary.value?.points || []).map((p) => ({ value: p.id, label: p.name || '—' })),
);
const circuitOptions = computed(() =>
  (summary.value?.distros || []).flatMap((d) =>
    (d.circuits || []).map((c) => ({
      value: c.id,
      label: `${d.name || '—'} · ${c.label || '—'} · ${circuitPhaseLabel(c)}`,
    })),
  ),
);

async function fetchAll() {
  loading.value = true;
  error.value = '';
  try {
    const [summaryRes, loadsRes] = await Promise.all([
      api.get(`/jobs/${jobId}/rigging/summary`),
      api.get(`/jobs/${jobId}/rigging/loads`),
    ]);
    summary.value = summaryRes.data;
    loads.value = loadsRes.data;
    for (const distro of summary.value.distros) {
      if (!newCircuit[distro.id]) {
        newCircuit[distro.id] = { label: '', phases: 1, phase: 'L1', breaker_amps: null };
      }
    }
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  } finally {
    loading.value = false;
  }
}

async function run(request, message) {
  try {
    await request();
    await fetchAll();
    if (message) $q.notify({ type: 'positive', message });
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('common.errorOccurred') });
  }
}

function addPoint() {
  const body = {
    name: newPoint.name.trim(),
    weight_capacity_kg: newPoint.weight_capacity_kg || null,
  };
  run(async () => {
    await api.post(`/jobs/${jobId}/rigging-points`, body);
    newPoint.name = '';
    newPoint.weight_capacity_kg = null;
  });
}

function removePoint(point) {
  run(() => api.delete(`/jobs/${jobId}/rigging-points/${point.id}`));
}

function addDistro() {
  const body = {
    name: newDistro.name.trim(),
    amps_per_phase: newDistro.amps_per_phase || null,
  };
  run(async () => {
    await api.post(`/jobs/${jobId}/power-distros`, body);
    newDistro.name = '';
    newDistro.amps_per_phase = null;
  });
}

function removeDistro(distro) {
  run(() => api.delete(`/jobs/${jobId}/power-distros/${distro.id}`));
}

function addCircuit(distro) {
  const form = newCircuit[distro.id];
  run(async () => {
    await api.post(`/jobs/${jobId}/power-circuits`, {
      distro_id: distro.id,
      label: form.label.trim(),
      phases: form.phases,
      phase: form.phases === 1 ? form.phase : null,
      breaker_amps: form.breaker_amps || null,
    });
    form.label = '';
    form.breaker_amps = null;
  });
}

function removeCircuit(circuit) {
  run(() => api.delete(`/jobs/${jobId}/power-circuits/${circuit.id}`));
}

function assign(item, change) {
  run(() => api.patch(`/jobs/${jobId}/rigging/loads/${item.kind}/${item.id}`, change));
}

onMounted(fetchAll);
</script>
