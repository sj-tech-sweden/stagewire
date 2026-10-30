<template>
  <div>
    <div class="text-caption text-grey-6">
      {{ t('rigging.outputs') }}
    </div>
    <div
      v-for="(output, i) in modelValue"
      :key="i"
      class="row q-col-gutter-xs items-center q-mb-xs"
      data-testid="output-row"
    >
      <q-select
        :model-value="output.connector"
        class="col-12 col-sm-6"
        dense
        outlined
        emit-value
        map-options
        :options="connectors"
        :label="t('workspace.outputConnector')"
        data-testid="output-connector"
        @update:model-value="(v) => change(i, { connector: v })"
      />
      <q-input
        :model-value="output.count"
        class="col-4 col-sm-2"
        dense
        outlined
        type="number"
        :label="t('workspace.outputCount')"
        data-testid="output-count"
        @update:model-value="(v) => change(i, { count: Math.max(1, Number(v) || 1) })"
      />
      <q-select
        :model-value="output.phase || null"
        class="col-4 col-sm-2"
        dense
        outlined
        clearable
        emit-value
        :options="['L1', 'L2', 'L3']"
        :label="t('workspace.outputPhase')"
        @update:model-value="(v) => change(i, { phase: v || null })"
      />
      <q-btn
        flat
        dense
        round
        color="negative"
        icon="close"
        :aria-label="t('workspace.remove')"
        @click="emit('update:modelValue', modelValue.filter((_, j) => j !== i))"
      />
    </div>
    <q-btn
      flat
      no-caps
      icon="add"
      :label="t('workspace.addOutput2')"
      data-testid="add-output-row"
      @click="emit('update:modelValue', [...modelValue, { connector: connectors[0]?.value || '', count: 1, phase: null }])"
    />
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n';

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  connectors: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();

const change = (i, patch) =>
  emit(
    'update:modelValue',
    props.modelValue.map((o, j) => (j === i ? { ...o, ...patch } : o)),
  );
</script>
