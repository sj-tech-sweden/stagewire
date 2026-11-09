<template>
  <q-dialog
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 360px; max-width: 92vw">
      <q-card-section class="row items-center">
        <div class="text-h6">
          {{ t('workspace.share.dialogTitle') }}
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
          {{ t('workspace.share.dialogHint') }}
        </p>

        <div
          v-if="error"
          class="text-negative text-caption q-mb-sm"
        >
          {{ error }}
        </div>

        <div class="text-center q-py-md">
          <q-spinner
            v-if="loading"
            color="primary"
            size="2rem"
          />
          <img
            v-else-if="qrDataUrl"
            :src="qrDataUrl"
            alt="QR code"
            style="width: 200px; height: 200px"
            data-testid="share-qr"
          >
        </div>

        <q-input
          :model-value="link"
          readonly
          dense
          outlined
          class="q-mb-sm"
          data-testid="share-link"
        >
          <template #append>
            <q-btn
              flat
              round
              icon="content_copy"
              :label="$q.screen.lt.sm ? '' : t('workspace.share.copyLink')"
              data-testid="share-copy"
              @click="copy"
            />
          </template>
        </q-input>
        <div class="text-caption text-grey-6 text-center">
          {{ t('workspace.share.qrHint') }}
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import QRCode from 'qrcode';
import { api } from '@/boot/api';

const { t } = useI18n();
const $q = useQuasar();

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
});
const emit = defineEmits(['update:modelValue']);

const loading = ref(false);
const error = ref('');
const link = ref('');
const qrDataUrl = ref('');

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return;
    await mint();
  },
);

async function mint() {
  loading.value = true;
  error.value = '';
  qrDataUrl.value = '';
  link.value = '';
  try {
    const { data } = await api.post(`/jobs/${props.jobId}/share`);
    const base = window.location.href.split('#')[0];
    const url = `${base}#/jobs/${props.jobId}/view?token=${encodeURIComponent(data.token)}`;
    link.value = url;
    qrDataUrl.value = await QRCode.toDataURL(url, { width: 240, margin: 1 });
  } catch {
    error.value = t('workspace.share.invalidOrExpired');
  } finally {
    loading.value = false;
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(link.value);
    $q.notify({ type: 'positive', message: t('workspace.share.linkCopied') });
  } catch {
    $q.notify({ type: 'negative', message: t('workspace.share.copyLink') });
  }
}
</script>
