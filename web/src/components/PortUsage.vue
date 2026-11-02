<template>
  <div
    v-if="usage.length"
    data-testid="port-usage"
  >
    <div class="text-subtitle2">
      {{ t('devices.portUsage') }}
    </div>
    <div
      v-for="port in usage"
      :key="port.id"
      class="row items-center q-gutter-xs q-mt-xs"
      data-testid="port-usage-row"
    >
      <div
        class="text-caption ellipsis"
        style="width: 96px"
      >
        {{ port.direction === 'out' ? t('devices.directionOut') : t('devices.directionIn') }}
        · {{ port.connector || port.id }}
      </div>
      <q-linear-progress
        :value="Math.min(1, port.used / (port.capacity || 1))"
        :color="port.direction === 'out' ? 'secondary' : 'primary'"
        class="col"
        style="height: 8px"
      />
      <div class="text-caption">
        {{ port.used }}/{{ port.capacity }}
      </div>
      <q-badge
        v-if="port.used >= port.capacity"
        color="negative"
      >
        {{ t('devices.full') }}
      </q-badge>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useGraphStore } from '@/stores/graph';
import { portUsage } from '@/utils/workspace';

// How much of each port of one device the connections in the graph use (used / capacity, and a
// "full" badge). Shared by the inspector and the device dialog, so it is found from either.
const props = defineProps({ device: { type: Object, default: null } });
const { t } = useI18n();
const graph = useGraphStore();
const usage = computed(() => portUsage(props.device, graph.edges));
</script>
