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

        <q-select
          v-if="canLoadProductAssets"
          v-model="selectedAssetId"
          :options="assetOptions"
          :loading="loadingAssets"
          :disable="loadingAssets || loading"
          dense
          outlined
          clearable
          emit-value
          map-options
          option-label="label"
          option-value="id"
          class="q-mt-sm"
          :label="t('workspace.bind.productDevice')"
          data-testid="bind-product-device"
          @update:model-value="onAssetSelected"
        >
          <template #no-option>
            <q-item>
              <q-item-section class="text-grey">
                {{ t('workspace.bind.noProductDevices') }}
              </q-item-section>
            </q-item>
          </template>
        </q-select>
        <q-banner
          v-if="assetListError"
          class="bg-negative text-white q-mt-sm rounded-borders"
          dense
        >
          {{ assetListError }}
        </q-banner>

        <q-input
          v-model="code"
          dense
          outlined
          class="q-mt-sm"
          :label="t('workspace.bind.code')"
          data-testid="bind-code"
          @update:model-value="selectedAssetId = null"
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
          <div v-if="bound.attributes?.stockwire_asset_barcode">
            {{ t('workspace.bind.barcode') }}: {{ bound.attributes.stockwire_asset_barcode }}
          </div>
          <div v-if="bound.attributes?.stockwire_asset_qr_code">
            {{ t('workspace.bind.qrCode') }}: {{ bound.attributes.stockwire_asset_qr_code }}
          </div>
          <div v-if="bound.attributes?.stockwire_asset_rfid">
            {{ t('workspace.bind.rfid') }}: {{ bound.attributes.stockwire_asset_rfid }}
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
          data-testid="bind-dismiss"
          :label="bound ? t('workspace.bind.done') : t('workspace.bind.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          color="primary"
          no-caps
          :disable="(!code.trim() && !selectedAssetId) || loading"
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
import axios from 'axios';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { useStockwireStore } from '@/stores/stockwire';
import { apiErrorText } from '@/utils/errors';
import { getApiBaseUrl } from '@/utils/runtime-config';
import ScanCapture from '@/components/ScanCapture.vue';

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const stockwire = useStockwireStore();
const shareApi = axios.create({ baseURL: `${getApiBaseUrl()}/api/v1` });

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  device: { type: Object, required: true },
  shareToken: { type: String, default: '' },
  stockwireProductId: { type: [String, Number], default: null },
});
const emit = defineEmits(['update:modelValue', 'bound']);

const code = ref('');
const loading = ref(false);
const error = ref('');
const bound = ref(null);
const selectedAssetId = ref(null);
const productDevices = ref([]);
const loadingAssets = ref(false);
const assetListError = ref('');
let assetLoadGeneration = 0;
const productId = computed(() => props.stockwireProductId);
const canLoadProductAssets = computed(
  () => Boolean(productId.value && (props.shareToken || stockwire.isEnabled)),
);
const assetOptions = computed(() =>
  productDevices.value.map((asset) => ({
    ...asset,
    id: String(asset.id),
    label:
      [
        asset.asset_tag,
        asset.serial_number,
        asset.barcode,
        asset.qr_code,
        asset.rfid,
        asset.description || asset.name,
        `#${asset.id}`,
      ]
        .filter(Boolean)
        .join(' · ') || String(asset.id),
  })),
);

watch(
  () => [props.modelValue, productId.value],
  ([open]) => {
    if (open && canLoadProductAssets.value) {
      loadProductDevices();
    } else if (open) {
      assetLoadGeneration += 1;
      productDevices.value = [];
      loadingAssets.value = false;
    } else {
      assetLoadGeneration += 1;
      loadingAssets.value = false;
      selectedAssetId.value = null;
      code.value = '';
      error.value = '';
      assetListError.value = '';
      productDevices.value = [];
    }
  },
);

async function loadProductDevices() {
  const generation = ++assetLoadGeneration;
  const requestedProductId = productId.value;
  productDevices.value = [];
  selectedAssetId.value = null;
  loadingAssets.value = true;
  assetListError.value = '';
  try {
    const devices = props.shareToken
      ? (
          await shareApi.get(`/jobs/${props.jobId}/devices/${props.device.id}/stockwire-assets`, {
            params: { token: props.shareToken },
          })
        ).data.items || []
      : await stockwire.getProductDevices(productId.value);
    if (generation === assetLoadGeneration && requestedProductId === productId.value) {
      productDevices.value = devices;
    }
  } catch (err) {
    if (generation === assetLoadGeneration && requestedProductId === productId.value) {
      assetListError.value = apiErrorText(err);
    }
  } finally {
    if (generation === assetLoadGeneration) loadingAssets.value = false;
  }
}

function onCaptured(value) {
  code.value = value;
  selectedAssetId.value = null;
}

function onAssetSelected(value) {
  if (value) code.value = '';
}

async function doBind() {
  const selected = assetOptions.value.find((asset) => asset.id === selectedAssetId.value);
  const value = selected
    ? String(
        selected.asset_tag ||
          selected.serial_number ||
          selected.barcode ||
          selected.qr_code ||
          selected.rfid ||
          selected.id,
      ).trim()
    : code.value.trim();
  if (!value) return;
  loading.value = true;
  error.value = '';
  bound.value = null;
  try {
    const payload = {
      code: value,
      expected_revision: props.device.revision,
      ...(selected
        ? {
            asset_id: selected.id,
            tag: selected.asset_tag,
            serial: selected.serial_number,
            barcode: selected.barcode,
            qr_code: selected.qr_code,
            rfid: selected.rfid,
            description: selected.description || selected.name,
          }
        : {}),
    };
    const device = props.shareToken
      ? (
          await shareApi.post(
            `/jobs/${props.jobId}/devices/${props.device.id}/bind-asset`,
            payload,
            { params: { token: props.shareToken } },
          )
        ).data
      : await graph.bindStockwireAsset(props.jobId, props.device.id, payload);
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
