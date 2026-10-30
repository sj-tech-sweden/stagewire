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
          class="row q-col-gutter-xs items-center q-mb-sm"
          data-testid="chain-step"
        >
          <div class="col-auto text-grey-6">
            {{ i + 1 }}
          </div>
          <q-select
            v-model="step.device_id"
            class="col-12 col-sm"
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
          <q-input
            v-model="step.connector"
            class="col-6 col-sm-2"
            dense
            outlined
            :label="t('workspace.stepConnector')"
          />
          <q-input
            v-model="step.patch_label"
            class="col-6 col-sm-2"
            dense
            outlined
            :label="t('workspace.stepLabel')"
          />
          <q-select
            v-if="branching && i > 0"
            v-model="step.parent_index"
            class="col-6 col-sm-2"
            dense
            outlined
            emit-value
            map-options
            clearable
            :options="parentOptions(i)"
            :label="t('workspace.stepFrom')"
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
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  initial: { type: Array, default: () => [] },
  devices: { type: Array, default: () => [] },
  branching: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const steps = ref([]);
const filtered = ref([]);

const blank = () => ({ device_id: null, connector: '', patch_label: '', notes: '', parent_index: null });
const options = () => props.devices.map((d) => ({ label: d.name, value: d.id }));

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    steps.value = props.initial.map((s) => ({ ...s }));
    filtered.value = options();
  },
);

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
    connector: s.connector || '',
    patch_label: s.patch_label || '',
    notes: s.notes || '',
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
