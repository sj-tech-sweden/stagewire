<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 560px; max-width: 100vw">
      <q-card-section class="text-h6">
        {{ outputs ? t('workspace.bulkOutputs') : t('workspace.bulkChannels') }}
      </q-card-section>
      <q-card-section class="q-pt-none row q-col-gutter-sm">
        <q-input
          v-model.number="form.count"
          class="col-6"
          dense
          outlined
          type="number"
          min="1"
          max="200"
          :label="t('workspace.bulkQuantity')"
          data-testid="list-bulk-count"
        />
        <q-input
          v-if="!outputs"
          v-model.number="form.start"
          class="col-6"
          dense
          outlined
          type="number"
          min="1"
          :label="t('workspace.bulkStartNumber')"
          data-testid="list-bulk-start"
        />
        <q-input
          v-model="form.prefix"
          class="col-12"
          dense
          outlined
          :label="outputs ? t('workspace.bulkOutputPrefix') : t('workspace.bulkChannelPrefix')"
          :hint="t('workspace.bulkPrefixHint')"
          data-testid="list-bulk-prefix"
        />
        <template v-if="!outputs">
          <q-select
            v-model="form.input_type"
            class="col-12 col-sm-6"
            dense
            outlined
            emit-value
            map-options
            :options="inputTypes"
            :label="t('workspace.colKind')"
          />
          <q-select
            v-model="form.instrument_group"
            class="col-12 col-sm-6"
            dense
            outlined
            emit-value
            map-options
            :options="groupOptions"
            :label="t('channels.instrumentGroup')"
          />
          <q-checkbox
            v-model="form.phantom_power"
            class="col-12"
            label="48V"
          />
        </template>
        <q-select
          v-else
          v-model="form.mode"
          class="col-12 col-sm-6"
          dense
          outlined
          emit-value
          map-options
          :options="modeOptions"
          :label="t('channels.outputMode')"
        />
        <ConnectorSelect
          v-model="form.connector"
          class="col-12 col-sm-6"
          :label="t('workspace.stepConnector')"
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
          :disable="!(form.count >= 1) || busy"
          :loading="busy"
          :label="t('workspace.bulkCreate', { n: form.count || 0 })"
          data-testid="list-bulk-create"
          @click="create"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, reactive, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import { INSTRUMENT_GROUP_KEYS } from '@/utils/instrumentGroups';
import { OUTPUT_MODES } from '@/utils/workspace';

// Adds many channels (inputs) or outputs to a list at once. A prefix names them "Prefix 1",
// "Prefix 2", ...; channels continue from the start number (the next free one by default).
// The parent does the creating (`create` event with the item bodies) so the same dialog serves
// both lists.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  outputs: { type: Boolean, default: false },
  nextNumber: { type: Number, default: 1 },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue', 'create']);
const { t } = useI18n();
const form = reactive({
  count: 8,
  start: 1,
  prefix: '',
  input_type: 'microphone',
  instrument_group: 'other',
  phantom_power: false,
  mode: 'mono',
  connector: '',
});

const inputTypes = ['microphone', 'di', 'wireless', 'fxReturn'].map((v) => ({
  value: v,
  label: t(`channels.type.${v}`),
}));
const groupOptions = INSTRUMENT_GROUP_KEYS.map((v) => ({ value: v, label: t(`channels.instrumentGroups.${v}`) }));
const modeOptions = computed(() =>
  OUTPUT_MODES.map((m) => ({ value: m.value, label: t(`workspace.busMode.${m.value.replace(/[._]/g, '')}`) })),
);

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.start = props.nextNumber;
    }
  },
);

function create() {
  const count = Math.max(1, Math.min(200, Number(form.count) || 1));
  const items = Array.from({ length: count }, (_, i) => {
    const number = (Number(form.start) || 1) + i;
    const label = form.prefix.trim() ? `${form.prefix.trim()} ${props.outputs ? i + 1 : number}` : '';
    if (props.outputs) {
      return { name: label || undefined, mode: form.mode, connector: form.connector || undefined };
    }
    return {
      channel_number: number,
      source_label: label,
      input_type: form.input_type,
      instrument_group: form.instrument_group,
      phantom_power: form.phantom_power,
      connector: form.connector || undefined,
    };
  });
  emit('create', items);
}
</script>
