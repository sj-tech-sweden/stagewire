<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 560px; max-width: 100vw">
      <q-card-section class="text-h6">
        {{ kind === 'inputs' ? t('video.bulkInputs') : t('video.bulkOutputs') }}
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
          :label="t('video.bulkQuantity')"
          data-testid="video-bulk-count"
        />
        <q-input
          v-model.number="form.start"
          class="col-6"
          dense
          outlined
          type="number"
          min="1"
          :label="t('video.bulkStart')"
          data-testid="video-bulk-start"
        />
        <q-input
          v-model="form.prefix"
          class="col-12"
          dense
          outlined
          :label="t('video.bulkPrefix')"
          :hint="t('video.bulkHint', { count: clampedCount })"
          data-testid="video-bulk-prefix"
        />
        <q-select
          v-if="kind === 'inputs'"
          v-model="form.source_type"
          class="col-12 col-sm-6"
          dense
          outlined
          emit-value
          map-options
          :options="sourceTypes"
          :label="t('video.bulkType')"
          data-testid="video-bulk-type"
        />
        <ConnectorSelect
          v-model="form.connector"
          class="col-12 col-sm-6"
          :label="t('video.bulkConnector')"
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
          :label="t('workspace.bulkCreate', { n: clampedCount })"
          data-testid="video-bulk-create"
          @click="create"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, reactive, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import ConnectorSelect from '@/components/ConnectorSelect.vue';

// Bulk-adds many video inputs or outputs to a list at once. Like the sound ListBulkDialog it builds
// the item bodies and emits them; the parent writes them through the existing batch endpoint
// (graph.createVideoRows) so realtime sync is unchanged. An input gets a source type + connector;
// an output gets a connector. Names follow the "Prefix 1", "Prefix 2" convention.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  kind: { type: String, default: 'inputs' },
  nextNumber: { type: Number, default: 1 },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue', 'create']);
const { t } = useI18n();
const $q = useQuasar();

const sourceTypes = ['camera', 'computer', 'other'].map((v) => ({
  value: v,
  label: t(`workspace.source${v[0].toUpperCase()}${v.slice(1)}`),
}));

const form = reactive({
  count: 8,
  start: 1,
  prefix: '',
  source_type: 'camera',
  connector: 'sdi',
});

const clampedCount = computed(() => Math.max(1, Math.min(200, Number(form.count) || 1)));

// Opening starts from the next free number for the list so the new rows continue the sequence.
watch(
  () => props.modelValue,
  (open) => {
    if (open) form.start = props.nextNumber;
  },
);

function create() {
  const count = clampedCount.value;
  const start = Number(form.start) || 1;
  const prefix = form.prefix.trim();
  const items = Array.from({ length: count }, (_, i) => {
    const number = start + i;
    const label = prefix ? `${prefix} ${number}` : '';
    if (props.kind === 'inputs') {
      return {
        input_number: number,
        source_label: label || undefined,
        source_type: form.source_type,
        connector: form.connector || undefined,
      };
    }
    return {
      output_number: number,
      name: label || undefined,
      connector: form.connector || undefined,
    };
  });
  emit('create', items);
}
</script>
