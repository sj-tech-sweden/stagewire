<template>
  <DeviceDialog
    :model-value="modelValue"
    :node="device"
    :effective="device ? graph.effective[device.id] : null"
    @update:model-value="(v) => emit('update:modelValue', v)"
    @save="save"
  />
</template>

<script setup>
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import DeviceDialog from '@/components/DeviceDialog.vue';
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import { devicePatch } from '@/utils/workspace';

// The device dialog for a device opened from a list (a chain's device chip, the mixer card). It
// edits the device in place with the same patch as the Devices tab and refreshes the computed
// weight/power values, so the hints in the dialog stay right.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  device: { type: Object, default: null },
  jobId: { type: String, required: true },
});
const emit = defineEmits(['update:modelValue']);
const $q = useQuasar();
const graph = useGraphStore();

async function save(form) {
  if (!props.device) return;
  try {
    await graph.updateDevice(props.jobId, props.device.id, devicePatch(props.device, form));
    emit('update:modelValue', false);
    graph.fetchEffective(props.jobId).catch(() => {});
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}
</script>
