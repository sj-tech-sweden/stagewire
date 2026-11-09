<template>
  <div class="scan-capture">
    <div class="row q-gutter-sm q-mb-md justify-center">
      <q-btn-toggle
        v-model="mode"
        toggle-color="primary"
        color="grey-9"
        text-color="grey-3"
        unelevated
        no-caps
        :options="modeButtons"
        data-testid="scan-mode"
      />
    </div>

    <div class="row q-col-gutter-sm">
      <div class="col-12">
        <q-input
          ref="captureInputRef"
          v-model="captureValue"
          :label="t('workspace.scan.enterCode')"
          outlined
          dense
          dark
          data-testid="scan-keyboard-input"
          @keyup.enter="applyValue"
        >
          <template #append>
            <q-btn
              flat
              dense
              round
              color="primary"
              icon="check"
              @click="applyValue"
            />
          </template>
        </q-input>
      </div>

      <div class="col-12 text-caption text-grey-5">
        {{ t('workspace.scan.hint') }}
      </div>

      <!-- Camera: native BarcodeDetector (QR + common 1D symbologies), no extra dependency. -->
      <div
        v-if="cameraActive"
        class="col-12"
      >
        <div class="scan-capture-camera-wrap">
          <video
            ref="videoRef"
            class="scan-capture-video"
            autoplay
            muted
            playsinline
          />
        </div>
        <div class="text-caption text-grey-5 q-mt-xs">
          {{ t('workspace.scan.pointCamera') }}
        </div>
      </div>

      <!-- NFC: Web NFC NDEFReader, best-effort where the browser exposes it. -->
      <div
        v-if="mode === 'nfc'"
        class="col-12"
      >
        <div class="scan-capture-nfc-wrap text-center">
          <q-icon
            name="nfc"
            size="40px"
            :color="nfcActive ? 'primary' : 'grey-5'"
          />
          <div
            class="text-caption q-mt-sm"
            :class="nfcActive ? 'text-primary' : 'text-grey-5'"
          >
            {{ nfcActive ? t('workspace.scan.nfcReady') : t('workspace.scan.nfcStart') }}
          </div>
        </div>
      </div>
    </div>

    <q-banner
      v-if="captureError"
      class="ec-banner ec-banner--danger q-mt-sm rounded-borders"
      dense
    >
      {{ captureError }}
    </q-banner>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps({
  // When true, the component is "active" and should run whichever capture mode is selected.
  active: { type: Boolean, default: true },
});
const emit = defineEmits(['captured']);

const captureInputRef = ref(null);
const videoRef = ref(null);
const captureValue = ref('');
const captureError = ref('');
const mode = ref('keyboard');
const cameraActive = ref(false);
const nfcActive = ref(false);
const stream = ref(null);
const raf = ref(null);
const nfcController = ref(null);

const supportsCamera = computed(
  () =>
    typeof window !== 'undefined' &&
    typeof window.BarcodeDetector === 'function' &&
    !!navigator.mediaDevices?.getUserMedia,
);
const supportsNfc = computed(
  () =>
    typeof window !== 'undefined' &&
    !!window.isSecureContext &&
    typeof window.NDEFReader === 'function',
);
const modeButtons = computed(() => {
  const buttons = [{ label: t('workspace.scan.keyboard'), value: 'keyboard', icon: 'keyboard' }];
  if (supportsCamera.value)
    buttons.push({ label: t('workspace.scan.camera'), value: 'camera', icon: 'photo_camera' });
  if (supportsNfc.value)
    buttons.push({ label: t('workspace.scan.nfc'), value: 'nfc', icon: 'nfc' });
  return buttons;
});

watch(mode, (m) => {
  if (m === 'keyboard') {
    stopCapture();
    focusCaptureInput();
  } else if (m === 'camera') {
    void startCameraCapture();
  } else if (m === 'nfc') {
    void startNfcCapture();
  }
});

function focusCaptureInput() {
  if (mode.value !== 'keyboard') return;
  nextTick(() => captureInputRef.value?.focus?.());
}

function applyValue() {
  const value = captureValue.value.trim();
  if (value) {
    emit('captured', value);
    captureValue.value = '';
  }
}

function stopCapture() {
  if (raf.value) {
    cancelAnimationFrame(raf.value);
    raf.value = null;
  }
  if (nfcController.value) {
    nfcController.value.abort();
    nfcController.value = null;
  }
  if (stream.value) {
    for (const track of stream.value.getTracks()) track.stop();
    stream.value = null;
  }
  if (videoRef.value) videoRef.value.srcObject = null;
  cameraActive.value = false;
  nfcActive.value = false;
}

async function startCameraCapture() {
  captureError.value = '';
  if (!supportsCamera.value) {
    captureError.value = t('workspace.scan.notSupported');
    return;
  }
  stopCapture();
  try {
    const s = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
    });
    stream.value = s;
    cameraActive.value = true;
    await nextTick();
    const videoEl = videoRef.value;
    if (!videoEl) {
      captureError.value = t('workspace.scan.cameraUnavailable');
      return;
    }
    videoEl.srcObject = s;
    await videoEl.play();
    const detector = new window.BarcodeDetector({
      formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e'],
    });
    const detectLoop = async () => {
      if (!props.active || !cameraActive.value) return;
      try {
        const codes = await detector.detect(videoEl);
        const first = Array.isArray(codes) && codes.length ? codes[0] : null;
        const value = String(first?.rawValue || '').trim();
        if (value) {
          captureValue.value = '';
          emit('captured', value);
          stopCapture();
          return;
        }
      } catch {
        /* keep scanning */
      }
      raf.value = requestAnimationFrame(detectLoop);
    };
    raf.value = requestAnimationFrame(detectLoop);
  } catch (error) {
    captureError.value = error?.message || t('workspace.scan.cameraFailed');
    stopCapture();
  }
}

function parseNfcRecordValue(record) {
  try {
    if (!record?.data) return '';
    const decoder = new TextDecoder(record.encoding || 'utf-8');
    return decoder.decode(record.data).trim();
  } catch {
    return '';
  }
}

async function startNfcCapture() {
  captureError.value = '';
  if (!supportsNfc.value) {
    captureError.value = t('workspace.scan.notSupported');
    return;
  }
  stopCapture();
  try {
    const ndef = new window.NDEFReader();
    const controller = new AbortController();
    nfcController.value = controller;
    await ndef.scan({ signal: controller.signal });
    nfcActive.value = true;
    ndef.onreadingerror = () => {
      captureError.value = t('workspace.scan.nfcError');
    };
    ndef.onreading = (event) => {
      const records = event?.message?.records || [];
      for (const record of records) {
        const value = parseNfcRecordValue(record);
        if (value) {
          captureValue.value = '';
          emit('captured', value);
          stopCapture();
          return;
        }
      }
      captureError.value = t('workspace.scan.nfcEmpty');
    };
  } catch (error) {
    captureError.value = error?.message || t('workspace.scan.nfcFailed');
    stopCapture();
  }
}

onUnmounted(() => stopCapture());
</script>

<style scoped>
.scan-capture-camera-wrap {
  width: 100%;
  max-height: 220px;
  overflow: hidden;
  border-radius: 8px;
  background: #000;
}
.scan-capture-video {
  width: 100%;
  height: auto;
  object-fit: cover;
}
</style>
