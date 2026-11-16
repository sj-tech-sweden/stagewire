<template>
  <q-dialog
    :model-value="modelValue"
    persistent
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card
      style="min-width: 480px; max-width: 95vw"
      data-testid="switcher-dialog"
    >
      <q-card-section class="text-h6">
        {{ t('video.switcherTitle') }}
      </q-card-section>
      <q-card-section class="q-gutter-md">
        <div class="text-caption text-grey-7">
          {{ t('video.switcherSummary', { name: list?.attributes?.switcher_product_name || '—', inputs: list?.attributes?.switcher_inputs ?? '–', outputs: list?.attributes?.switcher_outputs ?? '–' }) }}
        </div>
        <StockwireProductPicker
          :model-value="product"
          gear-type="switcher"
          own
          :label="t('video.pickSwitcher')"
          :hint="product?.sku || ''"
          data-testid="switcher-picker"
          @update:model-value="choose"
        />
        <div
          v-if="specNote"
          class="text-caption text-grey-7"
        >
          {{ specNote }}
        </div>
        <div class="row q-gutter-sm">
          <q-input
            v-model.number="inputs"
            :label="t('video.switcherInputs')"
            type="number"
            dense
            class="col"
            data-testid="switcher-inputs"
          />
          <q-input
            v-model.number="outputs"
            :label="t('video.switcherOutputs')"
            type="number"
            dense
            class="col"
            data-testid="switcher-outputs"
          />
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="negative"
          no-caps
          :label="t('video.switcherClear')"
          data-testid="switcher-clear"
          @click="clear"
        />
        <q-btn
          flat
          color="primary"
          :label="t('app.actions.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          flat
          color="primary"
          :label="t('app.actions.save')"
          data-testid="switcher-save"
          @click="emit('save', { product, inputs, outputs })"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { apiErrorText } from '@/utils/errors';
import { mixerSpecsOf } from '@/utils/workspace';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import { useStockwireStore } from '@/stores/stockwire';

// Sets the switcher of one video list: a catalog product (its input and output counts are read from
// the product specs, the same fields a mixer uses) or a typed name for a house switcher. Saving hands
// the choice to the editor, which stores it on the list; the existing "Fill from switcher" then adds
// empty inputs/outputs up to the switcher's size and patches them to it (see lists.fill-from-switcher).
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // the video_list node being edited
  list: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const stockwire = useStockwireStore();

const product = ref(null);
const inputs = ref(null);
const outputs = ref(null);
const specNote = ref('');

// Opening the dialog starts from what the list already has.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    const a = props.list?.attributes || {};
    product.value = a.switcher_product_name
      ? { id: a.switcher_product_id ? String(a.switcher_product_id) : null, name: a.switcher_product_name, sku: null }
      : null;
    inputs.value = a.switcher_inputs ?? null;
    outputs.value = a.switcher_outputs ?? null;
    specNote.value = '';
  },
);

async function choose(picked) {
  product.value = picked;
  specNote.value = '';
  if (!picked?.id) return;
  try {
    const specs = mixerSpecsOf(await stockwire.getProduct(picked.id));
    if (specs.inputs == null && specs.outputs == null) {
      specNote.value = t('video.switcherNoSpecs');
      return;
    }
    if (specs.inputs != null) inputs.value = specs.inputs;
    if (specs.outputs != null) outputs.value = specs.outputs;
    specNote.value = t('video.switcherSpecsLoaded', {
      inputs: specs.inputs ?? '–',
      outputs: specs.outputs ?? '–',
      connectors: picked.sku || '–',
    });
  } catch (err) {
    specNote.value = `${t('video.switcherSpecsError')} (${apiErrorText(err)})`;
  }
}

// Removing the switcher clears the selection and the counts on the list.
function clear() {
  emit('save', { product: null, inputs: null, outputs: null });
}
</script>
