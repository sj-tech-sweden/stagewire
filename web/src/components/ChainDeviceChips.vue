<template>
  <div class="row q-gutter-xs">
    <q-chip
      v-for="device in devices"
      :key="device.id"
      dense
      clickable
      square
      icon="edit"
      data-testid="chain-device"
      @click.stop="emit('edit', device)"
    >
      {{ device.name }}
      <q-tooltip>{{ t('workspace.editDevice') }}</q-tooltip>
    </q-chip>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useGraphStore } from '@/stores/graph';
import { chainDevices, videoChainDevices } from '@/utils/workspace';

// The gear a channel, output or video chain passes through, one chip each. Clicking a chip asks
// the parent to open that device for editing, so the gear can be changed from the list that uses
// it instead of by finding it on the map or in All gear.
const props = defineProps({
  node: { type: Object, required: true },
  // a video input or output chain is stored differently from an audio one
  video: { type: Boolean, default: false },
});
const emit = defineEmits(['edit']);
const { t } = useI18n();
const graph = useGraphStore();
const devices = computed(() =>
  (props.video ? videoChainDevices : chainDevices)(props.node, graph.edges, graph.devices),
);
</script>
