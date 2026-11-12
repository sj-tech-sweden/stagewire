<template>
  <div
    v-if="asset.isBound"
    class="q-mb-xs"
  >
    <div
      v-if="asset.code"
      class="text-caption"
    >
      <span class="text-grey-5">{{ t('workspace.bind.code') }}:</span> {{ asset.code }}
    </div>
    <div
      v-if="asset.tag"
      class="text-caption"
    >
      <span class="text-grey-5">{{ t('workspace.bind.tag') }}:</span> {{ asset.tag }}
    </div>
    <div
      v-if="asset.serial"
      class="text-caption"
    >
      <span class="text-grey-5">{{ t('workspace.bind.serial') }}:</span> {{ asset.serial }}
    </div>
    <div
      v-if="asset.barcode"
      class="text-caption"
    >
      <span class="text-grey-5">{{ t('workspace.bind.barcode') }}:</span> {{ asset.barcode }}
    </div>
    <div
      v-if="asset.qrCode"
      class="text-caption"
    >
      <span class="text-grey-5">{{ t('workspace.bind.qrCode') }}:</span> {{ asset.qrCode }}
    </div>
    <div
      v-if="asset.rfid"
      class="text-caption"
    >
      <span class="text-grey-5">{{ t('workspace.bind.rfid') }}:</span> {{ asset.rfid }}
    </div>
    <div
      v-if="asset.description"
      class="text-caption"
    >
      {{ asset.description }}
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n';

defineProps({
  asset: { type: Object, required: true },
});

const { t } = useI18n();
</script>
