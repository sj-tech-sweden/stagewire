<template>
  <q-dialog
    :model-value="modelValue"
    persistent
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card
      style="min-width: 480px; max-width: 95vw"
      data-testid="mixer-dialog"
    >
      <q-card-section class="text-h6">
        {{ t('stockwire.mixerDialogTitle', { name: list?.name || '' }) }}
      </q-card-section>
      <q-card-section class="q-gutter-md">
        <div class="text-caption text-grey-7">
          {{ t('stockwire.mixerDialogHint') }}
        </div>
        <StockwireProductPicker
          :model-value="product"
          gear-type="mixer"
          own
          :label="t('stockwire.mixerPickLabel')"
          :hint="product?.sku || ''"
          data-testid="mixer-picker"
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
            :label="t('stockwire.mixerInputs')"
            type="number"
            dense
            class="col"
            data-testid="mixer-inputs"
          />
          <q-input
            v-model.number="buses"
            :label="t('stockwire.mixerBuses')"
            type="number"
            dense
            class="col"
            data-testid="mixer-buses"
          />
        </div>
        <div class="row items-center q-gutter-sm">
          <q-btn
            flat
            icon="auto_fix_high"
            :label="t('stockwire.suggestMixer')"
            :loading="suggesting"
            @click="suggest"
          />
          <span class="text-caption text-grey-7">
            {{ t('stockwire.suggestMixerHint', { count: channelCount || inputs || 1 }) }}
          </span>
        </div>
        <div
          v-if="need"
          class="text-caption text-grey-7"
          data-testid="mixer-need"
        >
          {{ t('stockwire.proposeNeed', need) }}
        </div>
        <q-list
          v-if="suggestions.length"
          bordered
          separator
        >
          <q-item
            v-for="p in suggestions"
            :key="p.id"
            clickable
            @click="applySuggestion(p)"
          >
            <q-item-section>
              <div class="text-subtitle2">
                {{ p.name }}
              </div>
              <div class="text-caption text-grey-7">
                {{ [p.brand, p.manufacturer, p.sku].filter(Boolean).join(' · ') }}
              </div>
              <div
                v-if="p.fits !== undefined"
                class="q-mt-xs"
              >
                <q-chip
                  dense
                  :color="p.fits ? 'positive' : 'negative'"
                  text-color="white"
                  :label="p.fits ? t('stockwire.proposeFits') : t('stockwire.proposeNoFit')"
                />
                <q-chip
                  dense
                  outline
                  :label="p.simple ? t('stockwire.proposeSimple') : t('stockwire.proposeDigital')"
                />
                <span
                  v-if="p.headroom"
                  class="text-caption text-grey-7"
                >
                  {{ t('stockwire.proposeSpare', { strips: p.headroom.strips ?? '–', slots: p.headroom.bus_slots ?? '–' }) }}
                </span>
                <div
                  v-for="reason in p.reasons || []"
                  :key="reason"
                  class="text-caption text-negative"
                >
                  {{ reason }}
                </div>
                <div
                  v-if="p.unknown?.length"
                  class="text-caption text-warning"
                >
                  {{ t('stockwire.proposeUnknown', { what: p.unknown.join(', ') }) }}
                </div>
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
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
          data-testid="mixer-save"
          @click="emit('save', { product, inputs, buses })"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { api } from '@/boot/api';
import { useStockwireStore } from '@/stores/stockwire';
import { apiErrorText } from '@/utils/errors';
import { mixerSpecsOf, proposalFromResponse } from '@/utils/workspace';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';

// Sets the mixer of one channel list: a catalog product (its input and bus counts are read from
// the product specs) or a typed name for a house console. Saving hands the choice to the editor,
// which stores it on the list and adds empty inputs/outputs up to the mixer's size.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // the channel_list node being edited
  list: { type: Object, default: null },
  channelCount: { type: Number, default: 0 },
  // set for a job list: the proposal then also weighs the list's buses (bus-pool slots)
  jobId: { type: String, default: '' },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const stockwire = useStockwireStore();

const product = ref(null);
const inputs = ref(null);
const buses = ref(null);
const specNote = ref('');
const suggestions = ref([]);
const suggesting = ref(false);
const need = ref(null);

// Opening the dialog starts from what the list already has.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    const a = props.list?.attributes || {};
    product.value = a.mixer_product_name
      ? { id: a.mixer_product_id ? String(a.mixer_product_id) : null, name: a.mixer_product_name, sku: null }
      : null;
    inputs.value = a.mixer_inputs ?? null;
    buses.value = a.mixer_buses ?? null;
    specNote.value = '';
    suggestions.value = [];
    need.value = null;
  },
);

async function choose(picked) {
  product.value = picked;
  specNote.value = '';
  if (!picked?.id) return;
  try {
    const specs = mixerSpecsOf(await stockwire.getProduct(picked.id));
    if (specs.inputs == null && specs.buses == null) {
      specNote.value = t('stockwire.mixerNoSpecs');
      return;
    }
    if (specs.inputs != null) inputs.value = specs.inputs;
    if (specs.buses != null) buses.value = specs.buses;
    specNote.value = t('stockwire.mixerSpecsLoaded', { inputs: specs.inputs ?? '–', buses: specs.buses ?? '–' });
  } catch (err) {
    specNote.value = `${t('stockwire.mixerSpecsError')} (${apiErrorText(err)})`;
  }
}

// Mixers big enough for the list, from the rental catalog. For a job list the backend also weighs
// the buses (bus-pool slots, mix limit, roles) and ranks by fit; a venue list, which has no job
// endpoint, falls back to the input-count search.
async function suggest() {
  suggesting.value = true;
  try {
    if (props.jobId && props.list?.id) {
      const { data } = await api.get(`/jobs/${props.jobId}/channel-lists/${props.list.id}/propose-mixer`, {
        params: { category_id: stockwire.categoriesForGearType('mixer') },
        paramsSerializer: { indexes: null },
      });
      const proposal = proposalFromResponse(data);
      need.value = proposal.need;
      suggestions.value = proposal.suggestions;
      return;
    }
    // (named minInputs: a `const need` here would shadow the `need` ref above and throw before the
    // proposal branch could assign it)
    need.value = null;
    const minInputs = props.channelCount || inputs.value || 1;
    const base = { min_inputs: minInputs, limit: 10 };
    const cats = stockwire.categoriesForGearType('mixer');
    const groups = cats.length
      ? await Promise.all(cats.map((id) => stockwire.searchProducts({ ...base, category_id: id })))
      : [await stockwire.searchProducts(base)];
    suggestions.value = groups.flatMap((g) => g.items || []);
  } catch {
    suggestions.value = [];
  } finally {
    suggesting.value = false;
  }
}

function applySuggestion(p) {
  suggestions.value = [];
  choose({ id: String(p.id), name: p.name, sku: p.sku || null });
}
</script>
