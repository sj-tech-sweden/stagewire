<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="video-row-edit-card">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">
          {{ kind === 'video_input' ? t('workspace.editVideoInput') : t('workspace.editVideoOutput') }}
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

      <q-card-section
        v-if="row"
        class="q-pt-none q-gutter-sm"
      >
        <StockwireProductPicker
          v-if="kind === 'video_input'"
          :model-value="sourceOfForm"
          own
          :local-items="gearItems"
          gear-type="video"
          :label="t('workspace.videoSource')"
          :hint="''"
          @update:model-value="onPickSource"
        />

        <q-input
          v-if="kind === 'video_input'"
          v-model="form.name"
          dense
          outlined
          :label="t('workspace.colSource')"
          data-testid="video-edit-name"
        />
        <q-input
          v-else
          v-model="form.name"
          dense
          outlined
          :label="t('workspace.colName')"
          data-testid="video-edit-name"
        />

        <q-select
          v-if="kind === 'video_input'"
          v-model="form.source_type"
          dense
          outlined
          emit-value
          map-options
          :options="sourceTypes"
          :label="t('workspace.colSourceType')"
          data-testid="video-edit-source-type"
        />

        <ConnectorSelect
          v-model="form.connector"
          data-testid="video-edit-connector"
        />

        <div class="text-subtitle2 q-mt-sm">
          {{ t('workspace.videoSignal') }}
        </div>
        <div class="row q-col-gutter-sm">
          <q-input
            v-model="form.resolution"
            class="col-12 col-sm-6"
            dense
            outlined
            :label="t('workspace.videoFieldResolution')"
            data-testid="video-edit-resolution"
          />
          <q-input
            v-model="form.frame_rate"
            class="col-12 col-sm-6"
            dense
            outlined
            :label="t('workspace.videoFieldFrameRate')"
            data-testid="video-edit-frame-rate"
          />
        </div>
        <div class="row q-col-gutter-sm">
          <q-select
            v-model="form.signal_format"
            class="col-12 col-sm-4"
            dense
            outlined
            clearable
            emit-value
            map-options
            :options="signalFormats"
            :label="t('workspace.videoFieldSignalFormat')"
            data-testid="video-edit-signal-format"
          />
          <q-select
            v-model="form.color_space"
            class="col-12 col-sm-4"
            dense
            outlined
            clearable
            emit-value
            map-options
            :options="colorSpaces"
            :label="t('workspace.videoFieldColorSpace')"
            data-testid="video-edit-color-space"
          />
          <q-input
            v-model="form.aspect_ratio"
            class="col-12 col-sm-4"
            dense
            outlined
            :label="t('workspace.videoFieldAspectRatio')"
            data-testid="video-edit-aspect-ratio"
          />
        </div>

        <div class="text-subtitle2 q-mt-sm">
          {{ t('workspace.colNotes') }}
        </div>
        <div class="row items-start q-gutter-xs">
          <NotesDisplay
            v-if="form.notes"
            class="col"
            :notes="form.notes"
            :rows="4"
          />
          <q-btn
            dense
            flat
            no-caps
            size="sm"
            :icon="form.notes ? 'edit' : 'add'"
            :label="form.notes ? undefined : t('workspace.colNotes')"
            :aria-label="t('workspace.editNotes')"
            data-testid="video-edit-notes"
            @click="notesOpen = true"
          />
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          :label="t('workspace.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          color="primary"
          unelevated
          :label="t('workspace.save')"
          data-testid="video-edit-save"
          @click="onSave"
        />
      </q-card-actions>

      <MarkdownEditorDialog
        v-model="notesOpen"
        :title="t('workspace.colNotes')"
        :value="form.notes || ''"
        @save="(text) => (form.notes = text)"
      />
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import NotesDisplay from '@/components/NotesDisplay.vue';
import MarkdownEditorDialog from '@/components/MarkdownEditorDialog.vue';

// A consolidated editor for one video input/output row. It exposes the row's source, connector and
// the new signal-metadata fields (resolution, frame rate, signal format, colour space, aspect ratio)
// in one modal. All fields are graph-node attributes, so the parent applies the diff through the same
// graph save path and realtime sync is unchanged.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  row: { type: Object, default: null },
  kind: { type: String, default: 'video_input' },
  gearItems: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const $q = useQuasar();

const sourceTypes = ['camera', 'computer', 'other'].map((v) => ({
  value: v,
  label: t(`workspace.source${v[0].toUpperCase()}${v.slice(1)}`),
}));
const signalFormats = ['SDI', 'HDMI', 'NDI', 'SRT', 'ST2110', 'Analog'].map((v) => ({
  value: v,
  label: v,
}));
const colorSpaces = ['Rec709', 'Rec2020', 'HDR'].map((v) => ({ value: v, label: v }));

const notesOpen = ref(false);
const form = ref(rowForm());

function rowForm() {
  const r = props.row;
  const a = r?.attributes || {};
  return {
    name: props.kind === 'video_input' ? (r?.name ?? '') : (a.name ?? ''),
    source_type: a.source_type ?? 'camera',
    connector: a.connector ?? '',
    resolution: a.resolution ?? null,
    frame_rate: a.frame_rate ?? null,
    signal_format: a.signal_format ?? null,
    color_space: a.color_space ?? null,
    aspect_ratio: a.aspect_ratio ?? null,
    stockwire_product_id: a.stockwire_product_id ?? null,
    stockwire_product_name: a.stockwire_product_name ?? null,
    notes: r?.notes ?? '',
  };
}

watch(
  () => props.modelValue,
  (open) => {
    if (open && props.row) Object.assign(form.value, rowForm());
  },
  { immediate: true },
);

const sourceOfForm = () =>
  form.value.stockwire_product_name
    ? { id: form.value.stockwire_product_id, name: form.value.stockwire_product_name }
    : null;
function onPickSource(pick) {
  form.value.stockwire_product_id = pick?.id ? String(pick.id) : null;
  form.value.stockwire_product_name = pick?.name || null;
  if (pick?.name && !form.value.source_label) form.value.source_label = pick.name;
}

function norm(value) {
  return value === '' || value == null ? null : value;
}

const ATTRIBUTE_KEYS = [
  'connector',
  'source_type',
  'resolution',
  'frame_rate',
  'signal_format',
  'color_space',
  'aspect_ratio',
  'stockwire_product_id',
  'stockwire_product_name',
];

function onSave() {
  const r = props.row;
  if (!r) return;
  const changes = {};
  if (props.kind === 'video_input') {
    if (form.value.name !== r.name) changes.name = form.value.name;
  } else if (form.value.name !== (r.attributes?.name ?? '')) {
    changes.attributes = { name: form.value.name };
  }

  const attributes = {};
  for (const key of ATTRIBUTE_KEYS) {
    const next = norm(form.value[key]);
    const current = norm(r.attributes?.[key]);
    if (props.kind === 'video_input' || key !== 'source_type') {
      if (next !== current) attributes[key] = next;
    }
  }
  if (Object.keys(attributes).length) {
    changes.attributes = { ...(changes.attributes || {}), ...attributes };
  }
  if (form.value.notes !== (r.notes ?? '')) changes.notes = form.value.notes;

  if (Object.keys(changes).length) {
    emit('save', changes);
    emit('update:modelValue', false);
  } else {
    emit('update:modelValue', false);
  }
}
</script>

<style scoped>
.video-row-edit-card {
  width: 680px;
  max-width: 100vw;
}
</style>
