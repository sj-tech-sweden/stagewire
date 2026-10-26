<template>
  <div class="row items-center q-gutter-xs">
    <q-chip
      v-for="point in chainPoints"
      :key="point.id"
      dense
      removable
      color="grey-9"
      text-color="white"
      :label="deviceName(point.device_id)"
      @remove="emit('remove', point)"
    />
    <q-btn
      v-if="canAdd"
      flat
      dense
      icon="add"
      :label="t('video.addStage')"
      @click="emit('add')"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps({
  points: { type: Array, default: () => [] },
  canAdd: { type: Boolean, default: false },
  deviceName: { type: Function, required: true },
});
const emit = defineEmits(['add', 'remove']);
const { t } = useI18n({ useScope: 'global' });

const chainPoints = computed(() => (props.points || []).slice(1));
</script>
