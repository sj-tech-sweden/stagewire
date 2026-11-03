<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 640px; max-width: 100vw">
      <q-card-section class="row items-center">
        <div class="text-h6">
          {{ t('stockwire.availabilityTitle') }}
        </div>
        <q-space />
        <q-btn
          flat
          round
          icon="close"
          :aria-label="t('common.close')"
          @click="emit('update:modelValue', false)"
        />
      </q-card-section>
      <q-card-section class="q-pt-none">
        <div
          v-if="job"
          class="text-subtitle2 text-grey-7 q-mb-xs"
        >
          {{ t('stockwire.dateRangeLabel') }}:
          <span data-testid="availability-range">{{ job.start_date || '—' }} → {{ job.end_date || '—' }}</span>
        </div>
        <div class="text-caption text-grey-6 q-mb-md">
          {{ t('stockwire.availabilityHint') }}
        </div>

        <div
          v-if="loading"
          class="text-center q-pa-lg"
        >
          <q-spinner
            color="primary"
            size="2em"
          />
        </div>
        <template v-else-if="availability">
          <q-banner
            v-if="!availability.configured"
            class="bg-grey-9 text-white q-mb-md"
            dense
          >
            {{ t('stockwire.notConfigured') }}
          </q-banner>
          <q-banner
            v-else-if="availability.missing_dates"
            class="bg-warning text-black q-mb-md"
            dense
          >
            {{ t('stockwire.missingDates') }}
          </q-banner>
          <q-list
            v-else
            bordered
            separator
          >
            <q-item
              v-for="item in availability.items"
              :key="item.product_id"
              data-testid="availability-row"
            >
              <q-item-section>
                <q-item-label>{{ item.product_name || `#${item.product_id}` }}</q-item-label>
                <q-item-label caption>
                  {{ t('stockwire.available') }}: {{ item.available }}
                  · {{ t('stockwire.needed') }}: {{ item.needed }}
                  <span v-if="item.total || item.reserved">
                    · {{ t('stockwire.availabilityDetail', { total: item.total, reserved: item.reserved }) }}
                  </span>
                </q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-chip
                  :color="item.short ? 'negative' : 'positive'"
                  text-color="white"
                  dense
                >
                  {{ item.short ? t('stockwire.shortBy', { n: item.needed - item.available }) : t('stockwire.inStock') }}
                </q-chip>
              </q-item-section>
            </q-item>
            <q-item v-if="!availability.items.length">
              <q-item-section class="text-grey-6">
                {{ t('stockwire.availabilityEmpty') }}
              </q-item-section>
            </q-item>
          </q-list>
        </template>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useStockwireStore } from '@/stores/stockwire';

// Job-level availability: the minimum Stockwire stock per product across the job's date range
// compared to how many the job needs. Surfaced from the workspace header; the data is cached in
// the stockwire store so the device dialog can reuse it inline without a second request.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  job: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();
const stockwire = useStockwireStore();
const loading = ref(false);
const availability = ref(null);

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return;
    loading.value = true;
    availability.value = null;
    try {
      availability.value = await stockwire.getJobAvailability(props.jobId);
    } finally {
      loading.value = false;
    }
  },
);
</script>
