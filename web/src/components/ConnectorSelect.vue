<template>
  <q-select
    :model-value="modelValue"
    dense
    :outlined="!borderless"
    :borderless="borderless"
    use-input
    hide-selected
    fill-input
    emit-value
    map-options
    input-debounce="0"
    :options="shown"
    :label="label"
    :hint="hint"
    @filter="onFilter"
    @new-value="onNew"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <template #no-option>
      <q-item>
        <q-item-section class="text-grey">
          {{ t('workspace.connectorAddHint') }}
        </q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useConnectorKindsStore } from '@/stores/connectorKinds';

// A connector field. It offers the shared list of connector kinds (presets plus the ones people
// added) and accepts a new name: Enter on something that is not in the list adds it to the
// shared list, so the next field in any job offers it too. Values already stored (older free
// text such as "XLR") are shown as they are.
defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  borderless: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();
const $q = useQuasar();
const kinds = useConnectorKindsStore();
const shown = ref([]);

onMounted(async () => {
  await kinds.fetch().catch(() => {});
  shown.value = kinds.options;
});

function onFilter(value, update) {
  update(() => {
    const needle = value.toLowerCase();
    shown.value = kinds.options.filter(
      (o) => o.label.toLowerCase().includes(needle) || o.value.includes(needle),
    );
  });
}

async function onNew(value, done) {
  const typed = value.trim();
  if (!typed) return;
  const known = kinds.options.find(
    (o) => o.value === typed.toLowerCase() || o.label.toLowerCase() === typed.toLowerCase(),
  );
  if (known) {
    done(known.value, 'add-unique');
    return;
  }
  try {
    const key = await kinds.add(typed);
    shown.value = kinds.options;
    done(key, 'add-unique');
    $q.notify({ type: 'positive', message: t('workspace.connectorAdded', { name: typed }) });
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
  }
}
</script>
