<template>
  <div
    class="q-pa-md"
    data-testid="outlet-inspector"
  >
    <div class="row items-center q-mb-sm">
      <div class="text-subtitle1 col">
        {{ t('workspace.venueOutlet') }}
      </div>
      <q-btn
        flat
        dense
        round
        icon="close"
        :aria-label="t('workspace.closeFlow')"
        @click="emit('close')"
      />
    </div>
    <q-input
      :model-value="outlet.name"
      dense
      outlined
      class="q-mb-sm"
      :label="t('workspace.trussName')"
      data-testid="outlet-name"
      @change="(v) => save({ name: v })"
    />
    <ConnectorSelect
      :model-value="outlet.connector"
      power
      class="q-mb-sm"
      :label="t('workspace.outputConnector')"
      @update:model-value="(v) => save({ connector: v })"
    />
    <q-select
      :model-value="outlet.group_id"
      dense
      outlined
      clearable
      emit-value
      map-options
      class="q-mb-sm"
      :options="groupOptions"
      :label="t('workspace.venueGroup')"
      data-testid="outlet-group"
      @update:model-value="(v) => save({ group_id: v || null })"
    />
    <q-input
      :model-value="outlet.rating_amps"
      dense
      outlined
      type="number"
      class="q-mb-sm"
      :label="t('workspace.powerRating')"
      @change="(v) => save({ rating_amps: v === '' ? null : Number(v) })"
    />
    <div class="row q-col-gutter-sm q-mb-sm">
      <q-input
        :model-value="outlet.x_cm"
        class="col-6"
        dense
        outlined
        type="number"
        :label="t('workspace.outletX')"
        @change="(v) => save({ x_cm: v === '' ? null : Number(v) })"
      />
      <q-input
        :model-value="outlet.y_cm"
        class="col-6"
        dense
        outlined
        type="number"
        :label="t('workspace.outletY')"
        @change="(v) => save({ y_cm: v === '' ? null : Number(v) })"
      />
    </div>
    <div class="text-caption text-grey-6 q-mb-sm">
      {{ t('workspace.outletHint') }}
    </div>
    <q-btn
      color="primary"
      no-caps
      icon="bolt"
      :label="t('workspace.useOutlet')"
      data-testid="outlet-use"
      @click="useOutlet"
    />
  </div>
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import { useGraphStore } from '@/stores/graph';

// A venue outlet picked on the map: edit it (it belongs to the venue) or bring it into the job's
// power tree, where its group (or the outlet alone) becomes a source things can be plugged into.
const props = defineProps({
  outlet: { type: Object, required: true },
  groups: { type: Array, default: () => [] },
  venueId: { type: String, required: true },
  jobId: { type: String, required: true },
});
const emit = defineEmits(['close', 'changed']);
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const groupOptions = computed(() => props.groups.map((g) => ({ value: g.id, label: g.name || '—' })));
const failed = (err) =>
  $q.notify({ type: 'negative', message: apiErrorText(err) });

async function save(changes) {
  try {
    await api.patch(`/venues/${props.venueId}/power-outlets/${props.outlet.id}`, changes);
    emit('changed');
  } catch (err) {
    failed(err);
  }
}

async function useOutlet() {
  try {
    const { node } = await graph.outletSource(props.jobId, props.outlet.id);
    $q.notify({ type: 'positive', message: t('workspace.outletInTree', { name: node.name }) });
    emit('changed');
  } catch (err) {
    failed(err);
  }
}
</script>
