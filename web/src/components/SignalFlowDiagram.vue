<template>
  <div
    v-if="flows.length"
    data-testid="signal-flow-diagram"
  >
    <section
      v-for="flow in flows"
      :key="flow.channel.id"
      class="q-mb-md"
      :data-testid="`signal-flow-${flow.channel.id}`"
    >
      <div class="text-caption text-grey-5 q-mb-xs">
        {{ flow.channel.name }}
      </div>
      <DmxFlowDiagram
        :steps="flow.routes"
        readonly
      />
    </section>
  </div>
  <div
    v-else
    class="text-grey-6"
    data-testid="signal-flow-empty"
  >
    {{ t('workspace.signalFlowEmpty') }}
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import DmxFlowDiagram from '@/components/DmxFlowDiagram.vue';
import { channelFlowsForDevice } from '@/utils/workspace';

const props = defineProps({
  devices: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  focusId: { type: String, default: '' },
});

const { t } = useI18n();
const flows = computed(() => channelFlowsForDevice(props.focusId, props.devices, props.edges));
</script>
