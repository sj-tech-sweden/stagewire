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
const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  borderless: { type: Boolean, default: false },
  // a power connector field offers the power catalog and asks for a rating when adding a new one
  power: { type: Boolean, default: false },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();
const $q = useQuasar();
const kinds = useConnectorKindsStore();
const shown = ref([]);

const all = () => (props.power ? kinds.powerOptions : kinds.options);

onMounted(async () => {
  await kinds.fetch().catch(() => {});
  if (props.power) await kinds.fetchPower().catch(() => {});
  shown.value = all();
});

function onFilter(value, update) {
  update(() => {
    const needle = value.toLowerCase();
    shown.value = all().filter(
      (o) => o.label.toLowerCase().includes(needle) || o.value.includes(needle),
    );
  });
}

// Two short questions: amps per phase and the number of phases.
function ask(title, message, model) {
  return new Promise((resolve) => {
    $q.dialog({ title, message, prompt: { model, type: 'number' }, cancel: true, persistent: true })
      .onOk((value) => resolve(Number(value)))
      .onCancel(() => resolve(null))
      .onDismiss(() => resolve(null));
  });
}

async function addPower(label) {
  const amps = await ask(label, t('workspace.powerAmpsAsk'), '16');
  if (amps == null || Number.isNaN(amps)) return null;
  const phases = await ask(label, t('workspace.powerPhasesAsk'), '1');
  if (phases == null || ![1, 3].includes(phases)) return null;
  return kinds.addPower({ label, amps, phases });
}

async function onNew(value, done) {
  const typed = value.trim();
  if (!typed) return;
  const known = all().find(
    (o) => o.value === typed.toLowerCase() || o.label.toLowerCase() === typed.toLowerCase(),
  );
  if (known) {
    done(known.value, 'add-unique');
    return;
  }
  try {
    const key = props.power ? await addPower(typed) : await kinds.add(typed);
    if (!key) return;
    shown.value = all();
    done(key, 'add-unique');
    $q.notify({ type: 'positive', message: t('workspace.connectorAdded', { name: typed }) });
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
  }
}
</script>
