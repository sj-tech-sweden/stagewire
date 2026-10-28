<template>
  <q-dialog
    v-model="open"
    :maximized="$q.screen.lt.sm"
  >
    <q-card class="report-dialog ec-card">
      <q-card-section class="row items-center">
        <div class="text-h6">
          {{ t('reports.openReports') }}
        </div>
        <q-space />
        <q-btn
          flat
          round
          dense
          icon="close"
          :aria-label="t('app.actions.close')"
          @click="open = false"
        />
      </q-card-section>

      <q-card-section
        v-if="loading"
        class="q-pt-none row justify-center"
      >
        <q-spinner
          color="primary"
          size="32px"
        />
      </q-card-section>

      <q-card-section
        v-else
        class="q-pt-none"
      >
        <div
          v-if="error"
          class="text-negative q-mb-sm"
        >
          {{ error }}
        </div>
        <q-select
          v-model="selectedLocale"
          :options="localeOptions"
          emit-value
          map-options
          outlined
          dense
          :label="t('reports.templateLanguage')"
        />
        <q-select
          v-model="selectedTypeKey"
          :options="typeOptions"
          emit-value
          map-options
          outlined
          dense
          :label="t('reports.template')"
        />
        <q-select
          v-model="selectedTemplateId"
          :options="templateOptions"
          emit-value
          map-options
          outlined
          dense
          class="q-mt-sm"
          :label="t('reports.templateName')"
        />
        <q-select
          v-if="selectedType?.requires_patchpoint"
          v-model="selectedPatchpointId"
          :options="patchpointOptions"
          emit-value
          map-options
          outlined
          dense
          class="q-mt-sm"
          :label="t('reports.patchpoint')"
          :disable="patchpointLocked"
        />
        <div
          v-if="selectedType?.has_stage_plot"
          class="row q-col-gutter-sm q-mt-sm"
        >
          <q-select
            v-model="generationPlotOptions.view"
            class="col-12"
            :options="stagePlotViewOptions"
            emit-value
            map-options
            outlined
            dense
            :label="t('reports.plotArea')"
          />
          <q-toggle
            v-model="generationPlotOptions.show_coverage"
            class="col-12 col-sm-6"
            :label="t('reports.showSpeakerCoverage')"
          />
          <q-toggle
            v-model="generationPlotOptions.show_camera_coverage"
            class="col-12 col-sm-6"
            :label="t('reports.showCameraCoverage')"
          />
          <q-toggle
            v-model="generationPlotOptions.show_projector_coverage"
            class="col-12 col-sm-6"
            :label="t('reports.showProjectorCoverage')"
          />
          <q-btn-toggle
            v-model="generationPlotOptions.camera_view_mode"
            class="col-12"
            dense
            no-caps
            toggle-color="primary"
            :options="[
              { label: t('reports.cameraViewRange'), value: 'range' },
              { label: t('reports.cameraViewChosen'), value: 'chosen' },
            ]"
          />
          <q-toggle
            v-model="generationPlotOptions.show_cables"
            class="col-12 col-sm-6"
            :label="t('reports.showCables')"
          />
          <q-toggle
            v-model="generationPlotOptions.show_cableways"
            class="col-12"
            :label="t('reports.showCableways')"
          />
        </div>
      </q-card-section>

      <q-card-section
        v-if="previewUrl"
        class="q-pt-none"
      >
        <object
          :data="previewUrl"
          type="application/pdf"
          class="report-preview"
        >
          <div class="text-caption text-grey-7">{{ t('reports.previewUnavailable') }}</div>
        </object>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          :label="t('app.actions.close')"
          @click="open = false"
        />
        <q-btn
          outline
          color="primary"
          icon="visibility"
          :label="t('reports.previewPdf')"
          :loading="previewing"
          :disable="!canGenerate"
          @click="preview"
        />
        <q-btn
          color="primary"
          unelevated
          icon="download"
          :label="t('reports.generate')"
          :loading="generating"
          :disable="!canGenerate"
          @click="generate"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { useReportsStore } from '@/stores/reports'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  initialTypeKey: { type: String, default: '' },
  initialPatchpointId: { type: String, default: '' },
  patchpointLocked: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
const { t, locale } = useI18n()
const $q = useQuasar()
const store = useReportsStore()
const open = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const loading = ref(false)
const previewing = ref(false)
const generating = ref(false)
const error = ref('')
const reportTypes = ref([])
const templates = ref([])
const patchSheets = ref([])
const selectedLocale = ref(locale.value === 'sv' ? 'sv' : 'en')
const selectedTypeKey = ref('')
const selectedTemplateId = ref(null)
const selectedPatchpointId = ref(null)
const generationPlotOptions = ref({
  view: 'stage',
  show_coverage: false,
  show_camera_coverage: false,
  show_projector_coverage: false,
  camera_view_mode: 'range',
  show_cables: false,
  show_cableways: false,
})
const previewUrl = ref('')
const selectedType = computed(
  () => reportTypes.value.find((type) => type.key === selectedTypeKey.value) || null,
)
const selectedTemplate = computed(
  () => templates.value.find((template) => template.id === selectedTemplateId.value) || null,
)
const canGenerate = computed(
  () =>
    !!selectedType.value &&
    !!selectedTemplateId.value &&
    (!selectedType.value.requires_patchpoint || !!selectedPatchpointId.value),
)
const typeOptions = computed(() =>
  reportTypes.value.map((type) => ({ label: type.name, value: type.key })),
)
const localeOptions = computed(() => [
  { label: t('app.language.english'), value: 'en' },
  { label: t('app.language.swedish'), value: 'sv' },
])
const patchpointOptions = computed(() =>
  patchSheets.value.map((sheet) => ({ label: sheet.name, value: sheet.device_id })),
)
const stagePlotViewOptions = computed(() => [
  { label: t('reports.stageOnly'), value: 'stage' },
  { label: t('reports.wholeVenue'), value: 'venue' },
])
const templateOptions = computed(() =>
  templates.value
    .filter(
      (template) =>
        template.domain === selectedType.value?.domain &&
        template.report_type === selectedType.value?.report_type &&
        template.locale === selectedLocale.value,
    )
    .map((template) => ({
      label: `${template.name}${template.is_default ? ` · ${t('reports.default')}` : ''}`,
      value: template.id,
    })),
)

async function loadDialog() {
  if (!open.value) return
  loading.value = true
  error.value = ''
  try {
    const [types, loadedTemplates, loadedPatchSheets] = await Promise.all([
      store.fetchTypes(selectedLocale.value),
      store.fetchTemplates(),
      store.fetchPatchSheets(props.jobId),
    ])
    reportTypes.value = types
    templates.value = loadedTemplates
    patchSheets.value = loadedPatchSheets
    if (props.initialTypeKey && types.some((item) => item.key === props.initialTypeKey)) {
      selectedTypeKey.value = props.initialTypeKey
    } else if (!selectedTypeKey.value) selectedTypeKey.value = types[0]?.key || ''
    selectedPatchpointId.value =
      props.initialPatchpointId || patchSheets.value[0]?.device_id || null
    selectDefaultTemplate()
  } catch (err) {
    error.value = err?.response?.data?.detail || t('reports.failedLoad')
  } finally {
    loading.value = false
  }
}

function selectedOptions() {
  const options = {}
  if (selectedType.value?.requires_patchpoint) {
    options.patchpoint_id = selectedPatchpointId.value
  }
  if (selectedType.value?.has_stage_plot) {
    options.stage_plot_view = generationPlotOptions.value.view
    options.show_coverage = generationPlotOptions.value.show_coverage
    options.show_camera_coverage = generationPlotOptions.value.show_camera_coverage
    options.show_projector_coverage = generationPlotOptions.value.show_projector_coverage
    options.camera_view_mode = generationPlotOptions.value.camera_view_mode
    options.show_cables = generationPlotOptions.value.show_cables
    options.show_cableways = generationPlotOptions.value.show_cableways
  }
  return options
}

function selectDefaultTemplate() {
  const matching = templates.value.filter(
    (template) =>
      template.domain === selectedType.value?.domain &&
      template.report_type === selectedType.value?.report_type &&
      template.locale === selectedLocale.value,
  )
  selectedTemplateId.value = matching.find((template) => template.is_default)?.id || matching[0]?.id || null
  applyTemplatePlotOptions()
}

function applyTemplatePlotOptions() {
  generationPlotOptions.value = {
    view: 'stage',
    show_coverage: false,
    show_camera_coverage: false,
    show_projector_coverage: false,
    camera_view_mode: 'range',
    show_cables: false,
    show_cableways: false,
    ...(selectedTemplate.value?.stage_plot_options || {}),
  }
}

async function preview() {
  if (!selectedType.value || !selectedTemplateId.value) return
  previewing.value = true
  error.value = ''
  try {
    const template = templates.value.find((item) => item.id === selectedTemplateId.value)
    const blob = await store.fetchPreview(props.jobId, template, 'blob', selectedOptions())
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    error.value = err?.response?.data?.detail || t('reports.failedPreview')
  } finally {
    previewing.value = false
  }
}

async function generate() {
  if (!selectedType.value || !selectedTemplateId.value) return
  generating.value = true
  error.value = ''
  try {
    const result = await store.generate(
      props.jobId,
      selectedType.value,
      selectedTemplateId.value,
      selectedOptions(),
    )
    const url = URL.createObjectURL(result.data)
    const link = document.createElement('a')
    link.href = url
    link.download = result.filename || `${selectedType.value.report_type}.pdf`
    link.click()
    URL.revokeObjectURL(url)
    $q.notify({ type: 'positive', message: t('reports.download') })
  } catch (err) {
    error.value = err?.response?.data?.detail || t('reports.failedPreview')
  } finally {
    generating.value = false
  }
}

watch(open, loadDialog)
watch(selectedTypeKey, selectDefaultTemplate)
watch(selectedTemplateId, applyTemplatePlotOptions)
watch(selectedLocale, async (value) => {
  try {
    reportTypes.value = await store.fetchTypes(value)
    if (!selectedTypeKey.value || !reportTypes.value.some((item) => item.key === selectedTypeKey.value)) {
      selectedTypeKey.value = reportTypes.value[0]?.key || ''
    }
    selectDefaultTemplate()
  } catch (err) {
    error.value = err?.response?.data?.detail || t('reports.failedLoad')
  }
})
watch(locale, (value) => {
  if (value === 'en' || value === 'sv') selectedLocale.value = value
})
onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<style scoped>
.report-dialog {
  width: min(92vw, 640px);
  max-width: 92vw;
}

.report-preview {
  display: block;
  width: 100%;
  height: min(65vh, 760px);
  border: 1px solid var(--ec-border, #394247);
  background: white;
}
</style>
