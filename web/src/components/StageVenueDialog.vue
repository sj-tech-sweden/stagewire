<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 520px; max-width: 100vw">
      <q-card-section class="text-h6">
        {{ t('workspace.stageVenue') }}
      </q-card-section>
      <q-card-section class="q-pt-none">
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t('workspace.stageVenueHint') }}
        </div>
        <div class="text-subtitle2">
          {{ t('stagePlot.stageSetup') }}
        </div>
        <div class="row q-col-gutter-sm q-mb-md">
          <q-input
            v-model.number="form.stageW"
            class="col-6"
            dense
            outlined
            type="number"
            min="1"
            step="0.5"
            :label="t('workspace.stageWidthM')"
            data-testid="stage-width"
          />
          <q-input
            v-model.number="form.stageH"
            class="col-6"
            dense
            outlined
            type="number"
            min="1"
            step="0.5"
            :label="t('workspace.stageDepthM')"
            data-testid="stage-height"
          />
          <q-input
            v-model.number="form.stageX"
            class="col-6"
            dense
            outlined
            type="number"
            step="0.5"
            :label="t('workspace.stageXM')"
          />
          <q-input
            v-model.number="form.stageY"
            class="col-6"
            dense
            outlined
            type="number"
            step="0.5"
            :label="t('workspace.stageYM')"
          />
        </div>
        <div class="text-subtitle2">
          {{ t('stagePlot.venueSize') }}
        </div>
        <div class="row q-col-gutter-sm">
          <q-input
            v-model.number="form.venueW"
            class="col-6"
            dense
            outlined
            type="number"
            min="0"
            step="0.5"
            :label="t('workspace.venueWidthM')"
            data-testid="venue-width"
          />
          <q-input
            v-model.number="form.venueH"
            class="col-6"
            dense
            outlined
            type="number"
            min="0"
            step="0.5"
            :label="t('workspace.venueDepthM')"
            data-testid="venue-height"
          />
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          no-caps
          :label="t('common.cancel')"
        />
        <q-btn
          color="primary"
          no-caps
          :loading="busy"
          :label="t('workspace.save')"
          data-testid="stage-venue-save"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { api } from '@/boot/api';

// Edits the job's stage and venue in metres (the job stores cm). A venue of 0 means "no venue":
// the canvas then frames the stage only. Saved with PATCH /jobs/{id}, the same fields the stage
// plot page writes, so both views show the same stage.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  frame: { type: Object, required: true },
});
const emit = defineEmits(['update:modelValue', 'saved', 'error']);
const { t } = useI18n();
const busy = ref(false);
const form = reactive({ stageW: 10, stageH: 6, stageX: 0, stageY: 0, venueW: 0, venueH: 0 });
const m = (cm) => Math.round(cm) / 100;

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    Object.assign(form, {
      stageW: m(props.frame.stageW),
      stageH: m(props.frame.stageH),
      stageX: m(props.frame.stageX),
      stageY: m(props.frame.stageY),
      venueW: m(props.frame.venueW),
      venueH: m(props.frame.venueH),
    });
  },
);

async function save() {
  busy.value = true;
  const cm = (v) => Math.round((Number(v) || 0) * 100);
  try {
    await api.patch(`/jobs/${props.jobId}`, {
      stage_width_cm: cm(form.stageW),
      stage_height_cm: cm(form.stageH),
      stage_x_cm: cm(form.stageX),
      stage_y_cm: cm(form.stageY),
      venue_width_cm: cm(form.venueW),
      venue_height_cm: cm(form.venueH),
    });
    emit('saved');
    emit('update:modelValue', false);
  } catch (err) {
    emit('error', err);
  } finally {
    busy.value = false;
  }
}
</script>
