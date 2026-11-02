<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="flow-card">
      <q-card-section>
        <div class="text-h6">
          {{ title }}
        </div>
      </q-card-section>
      <q-card-section
        class="q-pt-none"
        data-testid="chain-flow"
      >
        <DmxFlowDiagram
          v-if="steps.length"
          :steps="steps"
          readonly
          inspectable
          @edit-device="(id) => emit('device', id)"
        />
        <div
          v-else
          class="text-grey-6"
        >
          {{ t('workspace.chainEmpty') }}
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          no-caps
          :label="t('workspace.closeFlow')"
        />
        <q-btn
          color="primary"
          no-caps
          icon="route"
          :label="t('workspace.editChain')"
          data-testid="flow-edit-chain"
          @click="emit('edit')"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { useI18n } from 'vue-i18n';
import DmxFlowDiagram from '@/components/DmxFlowDiagram.vue';

// The signal flow of one chain as a diagram (source, then each device with its connectors and
// ports, branches side by side). It reuses the DMX flow diagram; editing stays in the chain
// dialog, reached from here.
defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  steps: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue', 'edit', 'device']);
const { t } = useI18n();
</script>

<style scoped>
.flow-card {
  width: 900px;
  max-width: 100vw;
}
</style>
