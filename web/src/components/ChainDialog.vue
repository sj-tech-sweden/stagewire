<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="chain-card">
      <q-card-section>
        <div class="text-h6">
          {{ title }}
        </div>
        <div class="text-caption text-grey-6">
          {{ t('workspace.chainHint') }}
        </div>
      </q-card-section>
      <q-card-section class="q-pt-none">
        <div
          v-for="(step, i) in steps"
          :key="i"
          class="row q-col-gutter-xs items-center q-mb-md chain-step"
          data-testid="chain-step"
        >
          <div class="col-auto text-grey-6">
            {{ i + 1 }}
          </div>
          <q-select
            v-model="step.device_id"
            class="col"
            dense
            outlined
            emit-value
            map-options
            use-input
            input-debounce="0"
            :options="filtered"
            :label="t('workspace.stepDevice')"
            data-testid="chain-device"
            @filter="filterDevices"
          />
          <StockwireProductPicker
            class="col-12 col-sm-4"
            :model-value="null"
            own
            :label="t('workspace.stepFromStockwire')"
            :hint="''"
            data-testid="chain-stockwire"
            @update:model-value="(p) => addFromStockwire(step, p)"
          />
          <div class="col-auto">
            <q-btn
              flat
              dense
              round
              icon="arrow_upward"
              :disable="i === 0 || branching"
              :aria-label="t('workspace.stepUp')"
              @click="move(i, -1)"
            />
            <q-btn
              flat
              dense
              round
              icon="arrow_downward"
              :disable="i === steps.length - 1 || branching"
              :aria-label="t('workspace.stepDown')"
              @click="move(i, 1)"
            />
            <q-btn
              flat
              dense
              round
              color="negative"
              icon="close"
              :aria-label="t('workspace.remove')"
              @click="steps.splice(i, 1)"
            />
          </div>
          <div class="col-12 chain-fields-gap" />
          <template
            v-for="field in fields"
            :key="field.key"
          >
            <ConnectorSelect
              v-if="field.key === 'connector'"
              v-model="step.connector"
              class="col-6 col-sm"
              :label="t(field.label)"
              :data-testid="`chain-${field.key}`"
            />
            <q-input
              v-else
              v-model="step[field.key]"
              class="col-6 col-sm"
              dense
              outlined
              :label="t(field.label)"
              :data-testid="`chain-${field.key}`"
            />
          </template>
          <q-select
            v-if="busChannels.length"
            v-model="step.bus_connector"
            class="col-6 col-sm"
            dense
            outlined
            clearable
            use-input
            hide-selected
            fill-input
            new-value-mode="add-unique"
            input-debounce="0"
            :options="busChannels"
            :label="t('workspace.busChannel')"
            data-testid="chain-bus-channel"
            @new-value="(v, done) => done(v.trim(), 'add-unique')"
          />
          <q-select
            v-if="branching && i > 0"
            v-model="step.parent_index"
            class="col-6 col-sm"
            dense
            outlined
            emit-value
            map-options
            clearable
            :options="parentOptions(i)"
            :label="t('workspace.stepFrom')"
          />
        </div>
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('workspace.addStep')"
          data-testid="chain-add-step"
          @click="steps.push(blank())"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          no-caps
          :label="t('common.cancel')"
        />
        <q-btn
          color="primary"
          no-caps
          :disable="steps.some((s) => !s.device_id)"
          :label="t('workspace.save')"
          data-testid="chain-save"
          @click="emit('save', cleaned())"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import { useGraphStore } from '@/stores/graph';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  initial: { type: Array, default: () => [] },
  devices: { type: Array, default: () => [] },
  jobId: { type: String, default: '' },
  branching: { type: Boolean, default: false },
  // the channels of the bus an output chain feeds (L, R, C, Sub ...); empty for other chains
  busChannels: { type: Array, default: () => [] },
  fields: {
    type: Array,
    default: () => [
      { key: 'connector', label: 'workspace.stepConnector' },
      { key: 'patch_label', label: 'workspace.stepLabel' },
    ],
  },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const graph = useGraphStore();
const $q = useQuasar();
const steps = ref([]);
const filtered = ref([]);

const blank = () => ({
  device_id: null,
  connector: '',
  patch_label: '',
  in_port: '',
  out_port: '',
  bus_connector: '',
  notes: '',
  parent_index: null,
});
const options = () => props.devices.map((d) => ({ label: d.name, value: d.id }));

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    steps.value = props.initial.map((s) => ({ ...s }));
    filtered.value = options();
  },
);

// Searching Stockwire from a patch point: the picked product becomes a device in the job (with
// its connectors and power inlet) and is chosen for this step at once.
async function addFromStockwire(step, product) {
  if (!product) return;
  try {
    const created = await graph.createDeviceFromProduct(props.jobId, product);
    await nextTick();
    filtered.value = options();
    if (!filtered.value.some((o) => o.value === created.id)) {
      filtered.value = [...filtered.value, { label: created.name, value: created.id }];
    }
    step.device_id = created.id;
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
  }
}

function filterDevices(value, update) {
  update(() => {
    const needle = value.toLowerCase();
    filtered.value = options().filter((o) => o.label.toLowerCase().includes(needle));
  });
}

function parentOptions(i) {
  return steps.value.slice(0, i).map((_, index) => ({ label: `${t('workspace.stepFrom')} ${index + 1}`, value: index }));
}

function move(i, delta) {
  const target = i + delta;
  if (target < 0 || target >= steps.value.length) return;
  const [item] = steps.value.splice(i, 1);
  steps.value.splice(target, 0, item);
}

function cleaned() {
  return steps.value.map((s) => ({
    device_id: s.device_id,
    ...Object.fromEntries(props.fields.map((f) => [f.key, s[f.key] || ''])),
    notes: s.notes || '',
    ...(props.busChannels.length ? { bus_connector: s.bus_connector || null } : {}),
    ...(props.branching ? { parent_index: s.parent_index ?? null } : {}),
  }));
}
</script>

<style scoped>
.chain-card {
  width: 860px;
  max-width: 100vw;
}
</style>
