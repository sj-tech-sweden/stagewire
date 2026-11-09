<template>
  <q-dialog
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 560px; max-width: 95vw">
      <q-card-section class="row items-center">
        <div class="text-h6">
          {{ t('workspace.bind.title') }}
        </div>
        <q-space />
        <q-btn
          icon="close"
          flat
          round
          dense
          @click="emit('update:modelValue', false)"
        />
      </q-card-section>

      <q-card-section>
        <p class="text-caption text-grey-7 q-mt-none">
          {{ t('workspace.bind.hint') }}
        </p>

        <ScanCapture
          :active="modelValue"
          data-testid="bind-scan"
          @captured="onCaptured"
        />

        <q-input
          v-model="code"
          dense
          outlined
          class="q-mt-sm"
          :label="t('workspace.bind.code')"
          data-testid="bind-code"
        />

        <q-banner
          v-if="error"
          class="bg-negative text-white q-mt-sm rounded-borders"
          dense
        >
          {{ error }}
        </q-banner>

        <q-banner
          v-if="bound"
          class="bg-positive text-white q-mt-sm rounded-borders"
          data-testid="bind-result"
        >
          <div class="text-caption text-white-8">
            {{ t('workspace.bind.bound') }}
          </div>
          <div
            v-if="bound.attributes?.stockwire_asset_tag"
            data-testid="bind-tag"
          >
            {{ t('workspace.bind.tag') }}: {{ bound.attributes.stockwire_asset_tag }}
          </div>
          <div
            v-if="bound.attributes?.stockwire_asset_serial"
            data-testid="bind-serial"
          >
            {{ t('workspace.bind.serial') }}: {{ bound.attributes.stockwire_asset_serial }}
          </div>
          <div
            v-if="bound.attributes?.stockwire_asset_description"
            data-testid="bind-description"
          >
            {{ bound.attributes.stockwire_asset_description }}
          </div>
        </q-banner>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          no-caps
          :label="t('workspace.bind.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          color="primary"
          no-caps
          :disable="!code.trim() || loading"
          :loading="loading"
          :label="t('workspace.bind.bind')"
          data-testid="bind-confirm"
          @click="doBind"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { apiErrorText } from '@/utils/errors';
import ScanCapture from '@/components/ScanCapture.vue';

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  device: { type: Object, required: true },
});
const emit = defineEmits(['update:modelValue', 'bound']);

const code = ref('');
const loading = ref(false);
const error = ref('');
const bound = ref(null);

function onCaptured(value) {
  code.value = value;
}

async function doBind() {
  const value = code.value.trim();
  if (!value) return;
  loading.value = true;
  error.value = '';
  bound.value = null;
  try {
    const device = await graph.bindStockwireAsset(props.jobId, props.device.id, {
      code: value,
    });
    bound.value = device;
    emit('bound', device);
    $q.notify({ type: 'positive', message: t('workspace.bind.success') });
  } catch (err) {
    error.value = apiErrorText(err);
  } finally {
    loading.value = false;
  }
}
</script>
