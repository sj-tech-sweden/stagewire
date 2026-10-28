<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="col-12 col-sm">
        <div class="text-h5">
          {{ t('reports.title') }}
        </div>
        <div class="text-caption text-grey-7">
          {{ t('reports.subtitle') }}
        </div>
      </div>
      <div class="col-12 col-sm-auto row justify-end q-gutter-sm q-mt-sm q-sm-mt-none">
        <q-btn
          v-if="selectedTemplate && !selectedTemplate.is_builtin && !selectedTemplate.is_default"
          color="negative"
          flat
          icon="delete"
          :label="t('reports.deleteTemplate')"
          @click="deleteTemplate"
        />
        <q-btn
          color="primary"
          icon="content_copy"
          :label="t('reports.duplicateTemplate')"
          :disable="!selectedTemplate"
          @click="duplicateTemplate"
        />
      </div>
    </div>

    <q-banner
      v-if="pageError"
      class="bg-negative text-white q-mb-md"
    >
      {{ pageError }}
    </q-banner>

    <div
      v-else-if="!isAdmin"
      class="text-center q-pa-xl text-grey"
    >
      {{ t('common.errorOccurred') }}
    </div>
    <div
      v-else-if="loading"
      class="row justify-center q-pa-xl"
    >
      <q-spinner
        color="primary"
        size="36px"
      />
    </div>
    <template v-else>
      <div class="row q-col-gutter-md">
        <div class="col-12 col-md-8">
          <q-card class="ec-card">
            <q-card-section class="row q-col-gutter-sm items-center">
              <div class="col-12 col-md-3">
                <q-select
                  v-model="selectedLocale"
                  :options="localeOptions"
                  emit-value
                  map-options
                  outlined
                  dense
                  :label="t('reports.templateLanguage')"
                />
              </div>
              <div class="col-12 col-md-5">
                <q-select
                  v-model="selectedTemplateId"
                  :options="templateOptions"
                  emit-value
                  map-options
                  outlined
                  dense
                  :label="t('reports.template')"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-input
                  v-model="draft.name"
                  outlined
                  dense
                  :label="t('reports.templateName')"
                />
              </div>
              <div class="col-12 text-caption text-grey-7">
                <span v-if="selectedTemplate">{{ selectedTemplate.domain }} · {{ selectedTemplate.report_type }}</span>
                <q-badge
                  v-if="selectedTemplate?.is_builtin"
                  class="q-ml-sm"
                  color="secondary"
                  :label="t('reports.builtIn')"
                />
                <q-toggle
                  v-model="draft.is_default"
                  :disable="selectedTemplate?.is_default"
                  :label="t('reports.defaultForType')"
                />
              </div>
            </q-card-section>

            <q-separator />

            <q-card-section>
              <div class="text-subtitle2 q-mb-xs">
                {{ t('reports.insertData') }}
              </div>
              <div class="row q-gutter-xs q-mb-md">
                <q-btn
                  outline
                  dense
                  no-caps
                  icon="text_fields"
                  :label="t('reports.addText')"
                  @click="addLayoutObject('text')"
                />
                <q-btn
                  v-for="field in currentType?.fields || []"
                  :key="field.key"
                  outline
                  dense
                  no-caps
                  :label="field.label"
                  @click="addLayoutObject('field', `{{${field.key}}}`)"
                />
                <q-btn
                  v-for="table in currentType?.tables || []"
                  :key="table.key"
                  outline
                  dense
                  no-caps
                  icon="table_chart"
                  :label="table.label"
                  @click="addLayoutObject('table', `{{table:${table.key}}}`)"
                />
                <q-btn
                  v-if="currentType?.has_stage_plot"
                  outline
                  dense
                  no-caps
                  icon="map"
                  :label="t('reports.stagePlotDiagram')"
                  @click="addLayoutObject('stage_plot', '{{stage_plot}}')"
                />
              </div>
              <div
                v-if="currentType?.has_stage_plot"
                class="row q-col-gutter-sm q-mb-md"
              >
                <q-select
                  v-model="draft.stage_plot_options.view"
                  class="col-12 col-sm-6"
                  :options="stagePlotViewOptions"
                  emit-value
                  map-options
                  outlined
                  dense
                  :label="t('reports.plotArea')"
                />
                <q-toggle
                  v-model="draft.stage_plot_options.show_coverage"
                  class="col-12 col-sm-6"
                  :label="t('reports.showSpeakerCoverage')"
                />
                <q-toggle
                  v-model="draft.stage_plot_options.show_camera_coverage"
                  class="col-12 col-sm-6"
                  :label="t('reports.showCameraCoverage')"
                />
                <q-toggle
                  v-model="draft.stage_plot_options.show_projector_coverage"
                  class="col-12 col-sm-6"
                  :label="t('reports.showProjectorCoverage')"
                />
                <q-btn-toggle
                  v-model="draft.stage_plot_options.camera_view_mode"
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
                  v-model="draft.stage_plot_options.show_cables"
                  class="col-12 col-sm-6"
                  :label="t('reports.showCables')"
                />
                <q-toggle
                  v-model="draft.stage_plot_options.show_cableways"
                  class="col-12 col-sm-6"
                  :label="t('reports.showCableways')"
                />
              </div>
              <div class="row q-col-gutter-md">
                <div class="col-12 col-lg-6">
                  <div class="row items-center q-mb-sm">
                    <q-tabs
                      v-model="currentLayoutPage"
                      dense
                      inline-label
                      class="col"
                      active-color="primary"
                    >
                      <q-tab
                        v-for="page in layoutPageOptions"
                        :key="page.value"
                        :name="page.value"
                        :label="page.label"
                      />
                    </q-tabs>
                    <q-btn
                      flat
                      round
                      icon="add"
                      :aria-label="t('reports.addPage')"
                      @click="addLayoutPage"
                    />
                  </div>
                  <ReportLayoutEditor
                    v-model="draft.layout_json"
                    v-model:selected-id="selectedLayoutId"
                    :page-index="currentLayoutPage"
                    :page-aspect-ratio="layoutPageAspectRatio"
                    :drag-label="t('reports.dragObject')"
                    :resize-label="t('reports.resizeObject')"
                    :empty-label="t('reports.emptyLayout')"
                    :object-label="layoutObjectLabel"
                    :fields="currentType?.fields || []"
                    :tables="currentType?.tables || []"
                    :preview-job="previewJob"
                    :stage-plot-elements="stagePlotElements"
                    :stage-plot-cables="stagePlotCables"
                    :stage-plot-devices="stagePlotDevices"
                    :stage-plot-cameras="stagePlotCameras"
                    :stage-plot-options="draft.stage_plot_options"
                    :stage-width="previewJob?.stage_width_cm || 0"
                    :stage-height="previewJob?.stage_height_cm || 0"
                    :venue-width="previewJob?.venue_width_cm || 0"
                    :venue-height="previewJob?.venue_height_cm || 0"
                    :stage-x="previewJob?.stage_x_cm || 0"
                    :stage-y="previewJob?.stage_y_cm || 0"
                    :cable-plan="previewJob?.cable_plan || {}"
                    :stage-plot-label="t('reports.stagePlotDiagram')"
                  />
                </div>
                <div class="col-12 col-lg-6">
                  <div class="text-caption text-grey-7 q-mb-xs">
                    {{ t('reports.editSelectedObject') }}
                  </div>
                  <q-editor
                    v-if="selectedLayoutItem"
                    v-model="selectedLayoutItem.html"
                    min-height="220px"
                    :toolbar="[
                      ['bold', 'italic', 'underline', 'strike'],
                      ['unordered', 'ordered', 'outdent', 'indent'],
                      ['align', 'quote'],
                      ['undo', 'redo', 'viewsource'],
                    ]"
                  />
                  <div
                    v-else
                    class="text-caption text-grey-7 q-pa-md"
                  >
                    {{ t('reports.selectObjectHint') }}
                  </div>
                  <div
                    v-if="selectedLayoutItem"
                    class="row q-col-gutter-xs q-mt-sm"
                  >
                    <q-input
                      v-model.number="selectedLayoutItem.x"
                      class="col-3"
                      type="number"
                      min="0"
                      max="100"
                      outlined
                      dense
                      label="X %"
                    />
                    <q-input
                      v-model.number="selectedLayoutItem.y"
                      class="col-3"
                      type="number"
                      min="0"
                      max="100"
                      outlined
                      dense
                      label="Y %"
                    />
                    <q-input
                      v-model.number="selectedLayoutItem.width"
                      class="col-3"
                      type="number"
                      min="1"
                      max="100"
                      outlined
                      dense
                      :label="t('reports.widthPercent')"
                    />
                    <q-input
                      v-model.number="selectedLayoutItem.height"
                      class="col-3"
                      type="number"
                      min="1"
                      max="100"
                      outlined
                      dense
                      :label="t('reports.heightPercent')"
                    />
                    <q-select
                      v-model.number="selectedLayoutItem.page"
                      class="col-12"
                      :options="layoutPageOptions"
                      emit-value
                      map-options
                      outlined
                      dense
                      :label="t('reports.objectPage')"
                    />
                    <q-select
                      v-if="selectedLayoutItem.html.includes('{{stage_plot}}')"
                      v-model="selectedLayoutItem.stage_plot_scale"
                      class="col-12"
                      :options="stagePlotScaleOptions"
                      emit-value
                      map-options
                      outlined
                      dense
                      :label="t('reports.stagePlotScale')"
                    />
                    <div class="col-12 row justify-end">
                      <q-btn
                        flat
                        color="negative"
                        icon="delete"
                        :label="t('reports.removeObject')"
                        @click="removeLayoutObject(selectedLayoutItem.id)"
                      />
                    </div>
                  </div>
                </div>
              </div>
              <div class="text-caption text-grey-7 q-mt-sm">
                {{ t('reports.editorHint') }}
              </div>
            </q-card-section>

            <q-card-section class="row items-center q-gutter-sm">
              <q-select
                v-model="draft.letterhead_id"
                :options="letterheadOptions"
                emit-value
                map-options
                clearable
                outlined
                dense
                class="letterhead-select"
                :label="t('reports.letterhead')"
              />
              <div class="col text-caption text-grey-7">
                {{ draft.letterhead_id ? t('reports.selectedLetterhead') : t('reports.usesDefaultLetterhead') }}
              </div>
              <q-btn
                color="primary"
                unelevated
                icon="save"
                :label="t('app.actions.save')"
                :loading="saving"
                :disable="!selectedTemplate || !draft.name.trim() || !draft.body_html.trim()"
                @click="saveTemplate"
              />
            </q-card-section>
          </q-card>
        </div>

        <div class="col-12 col-md-4">
          <q-card class="ec-card">
            <q-card-section>
              <div class="text-subtitle1">
                {{ t('reports.preview') }}
              </div>
              <q-select
                v-model="previewJobId"
                :options="jobOptions"
                emit-value
                map-options
                outlined
                dense
                class="q-mt-sm"
                :label="t('reports.previewJob')"
              />
              <q-select
                v-if="currentType?.requires_patchpoint"
                v-model="previewPatchpointId"
                :options="previewPatchpointOptions"
                emit-value
                map-options
                outlined
                dense
                class="q-mt-sm"
                :loading="loadingPreviewPatchpoints"
                :label="t('reports.patchpoint')"
              />
              <q-btn
                class="full-width q-mt-sm"
                outline
                color="primary"
                icon="picture_as_pdf"
                :label="t('reports.previewPdf')"
                :loading="previewing"
                :disable="!canPreview"
                @click="previewTemplate"
              />
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
          </q-card>

          <q-card class="ec-card q-mt-md">
            <q-card-section class="row items-center justify-between">
              <div>
                <div class="text-subtitle1">
                  {{ t('reports.letterheads') }}
                </div>
                <div class="text-caption text-grey-7">
                  {{ t('reports.letterheadHelp') }}
                </div>
              </div>
              <q-btn
                flat
                round
                icon="add"
                :aria-label="t('reports.uploadLetterhead')"
                @click="showUpload = true"
              />
            </q-card-section>
            <q-separator />
            <q-list
              v-if="letterheads.length"
              separator
            >
              <q-expansion-item
                v-for="letterhead in letterheads"
                :key="letterhead.id"
                dense
                @show="loadLetterheadPreview(letterhead)"
              >
                <template #header>
                  <q-item-section>
                    <q-item-label>{{ letterhead.name }}</q-item-label>
                    <q-item-label caption>
                      {{ letterhead.page_width_pt.toFixed(0) }} × {{ letterhead.page_height_pt.toFixed(0) }} pt
                      <span v-if="letterhead.is_default"> · {{ t('reports.default') }}</span>
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-btn
                      v-if="!letterhead.is_default"
                      flat
                      dense
                      round
                      icon="star"
                      color="amber"
                      :aria-label="t('reports.setAsDefault')"
                      @click.stop="setDefaultLetterhead(letterhead)"
                    />
                  </q-item-section>
                </template>
                <q-card-section class="q-pt-none">
                  <div
                    class="letterhead-preview-frame"
                    :style="letterheadPageStyle(letterhead)"
                  >
                    <img
                      v-if="letterheadPreviewUrl && activeLetterheadId === letterhead.id"
                      :src="letterheadPreviewUrl"
                      :alt="letterhead.name"
                      class="letterhead-pdf"
                    >
                    <div
                      class="letterhead-printable"
                      :style="marginStyle(letterhead)"
                    >
                      {{ t('reports.printableArea') }}
                    </div>
                  </div>
                  <div class="row q-col-gutter-xs q-mt-sm">
                    <q-input
                      v-model.number="marginDraft.top"
                      class="col-6 col-sm-3"
                      type="number"
                      min="0"
                      max="200"
                      outlined
                      dense
                      :label="t('reports.topMm')"
                    />
                    <q-input
                      v-model.number="marginDraft.bottom"
                      class="col-6 col-sm-3"
                      type="number"
                      min="0"
                      max="200"
                      outlined
                      dense
                      :label="t('reports.bottomMm')"
                    />
                    <q-input
                      v-model.number="marginDraft.left"
                      class="col-6 col-sm-3"
                      type="number"
                      min="0"
                      max="200"
                      outlined
                      dense
                      :label="t('reports.leftMm')"
                    />
                    <q-input
                      v-model.number="marginDraft.right"
                      class="col-6 col-sm-3"
                      type="number"
                      min="0"
                      max="200"
                      outlined
                      dense
                      :label="t('reports.rightMm')"
                    />
                  </div>
                  <div class="row justify-end q-gutter-sm q-mt-xs">
                    <q-btn
                      flat
                      color="negative"
                      :label="t('app.actions.delete')"
                      @click="deleteLetterhead(letterhead)"
                    />
                    <q-btn
                      color="primary"
                      unelevated
                      :label="t('app.actions.save')"
                      @click="saveMargins(letterhead)"
                    />
                  </div>
                </q-card-section>
              </q-expansion-item>
            </q-list>
            <q-card-section
              v-else
              class="text-caption text-grey-7"
            >
              {{ t('reports.noLetterheads') }}
            </q-card-section>
          </q-card>
        </div>
      </div>
    </template>

    <q-dialog v-model="showUpload">
      <q-card class="ec-card upload-card">
        <q-card-section>
          <div class="text-h6">
            {{ t('reports.uploadLetterhead') }}
          </div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <q-input
            v-model="uploadName"
            outlined
            dense
            :label="t('reports.letterheadName')"
          />
          <q-file
            v-model="uploadFile"
            outlined
            dense
            accept=".pdf,application/pdf"
            class="q-mt-sm"
            :label="t('reports.selectPdfFile')"
          />
          <q-toggle
            v-model="uploadDefault"
            class="q-mt-sm"
            :label="t('reports.setAsDefault')"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            flat
            :label="t('app.actions.cancel')"
            @click="showUpload = false"
          />
          <q-btn
            color="primary"
            unelevated
            :loading="uploading"
            :disable="!uploadFile || !uploadName.trim()"
            :label="t('app.actions.upload')"
            @click="uploadLetterhead"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import ReportLayoutEditor from '@/components/ReportLayoutEditor.vue'
import { useReportsStore } from '@/stores/reports'
import { useAuthStore } from '@/stores/auth'

const { t, locale } = useI18n()
const $q = useQuasar()
const store = useReportsStore()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')
const loading = ref(true)
const saving = ref(false)
const previewing = ref(false)
const uploading = ref(false)
const pageError = ref('')
const templates = ref([])
const reportTypes = ref([])
const letterheads = ref([])
const jobs = ref([])
const stagePlotElements = ref([])
const stagePlotCables = ref([])
const stagePlotDevices = ref([])
const stagePlotCameras = ref({})
const previewPatchpointSheets = ref([])
const previewPatchpointId = ref(null)
const loadingPreviewPatchpoints = ref(false)
const selectedTemplateId = ref(null)
const selectedLocale = ref(locale.value === 'sv' ? 'sv' : 'en')
const selectedLayoutId = ref(null)
const currentLayoutPage = ref(0)
const previewJobId = ref(null)
const showUpload = ref(false)
const uploadFile = ref(null)
const uploadName = ref('')
const uploadDefault = ref(false)
const previewUrl = ref('')
const letterheadPreviewUrl = ref('')
const activeLetterheadId = ref(null)
const draft = reactive({
  name: '',
  body_html: '',
  layout_json: [],
  page_count: 1,
  stage_plot_options: {
    view: 'stage',
    show_coverage: false,
    show_camera_coverage: false,
    show_projector_coverage: false,
    camera_view_mode: 'range',
    show_cables: false,
    show_cableways: false,
  },
  letterhead_id: null,
  is_default: false,
})
const marginDraft = reactive({ top: 20, bottom: 20, left: 20, right: 20 })
const selectedTemplate = computed(() => templates.value.find((item) => item.id === selectedTemplateId.value) || null)
const selectedLayoutItem = computed(
  () => draft.layout_json.find((item) => item.id === selectedLayoutId.value) || null,
)
const layoutPageOptions = computed(() =>
  Array.from({ length: draft.page_count }, (_, page) => ({
    label: `${t('reports.page')} ${page + 1}`,
    value: page,
  })),
)
const currentType = computed(() =>
  reportTypes.value.find(
    (item) => item.domain === selectedTemplate.value?.domain && item.report_type === selectedTemplate.value?.report_type,
  ),
)
const previewJob = computed(() => jobs.value.find((job) => job.id === previewJobId.value) || null)
const canPreview = computed(
  () =>
    !!selectedTemplate.value &&
    !!previewJobId.value &&
    (!currentType.value?.requires_patchpoint ||
      (!!previewPatchpointId.value && !loadingPreviewPatchpoints.value)),
)
const previewPatchpointOptions = computed(() =>
  previewPatchpointSheets.value.map((sheet) => ({
    label: sheet.name,
    value: sheet.device_id,
  })),
)
const templateOptions = computed(() =>
  templates.value.filter((item) => item.locale === selectedLocale.value).map((item) => ({
    label: `${item.name}${item.is_default ? ` · ${t('reports.default')}` : ''}`,
    value: item.id,
  })),
)
const localeOptions = computed(() => [
  { label: t('app.language.english'), value: 'en' },
  { label: t('app.language.swedish'), value: 'sv' },
])
const stagePlotScaleOptions = computed(() => [
  { label: t('reports.fitToPage'), value: 'fit' },
  { label: '1:50', value: '1:50' },
  { label: '1:100', value: '1:100' },
])
const stagePlotViewOptions = computed(() => [
  { label: t('reports.stageOnly'), value: 'stage' },
  { label: t('reports.wholeVenue'), value: 'venue' },
])
const layoutPageAspectRatio = computed(() => {
  const letterhead = selectedLetterhead.value
  const widthMm = letterhead ? (letterhead.page_width_pt * 25.4) / 72 : 210
  const heightMm = letterhead ? (letterhead.page_height_pt * 25.4) / 72 : 297
  const margins = letterhead
    ? {
        top:
          activeLetterheadId.value === letterhead.id
            ? marginDraft.top
            : letterhead.margin_top_mm,
        bottom:
          activeLetterheadId.value === letterhead.id
            ? marginDraft.bottom
            : letterhead.margin_bottom_mm,
        left:
          activeLetterheadId.value === letterhead.id
            ? marginDraft.left
            : letterhead.margin_left_mm,
        right:
          activeLetterheadId.value === letterhead.id
            ? marginDraft.right
            : letterhead.margin_right_mm,
      }
    : { top: 18, bottom: 18, left: 18, right: 18 }
  return `${Math.max(1, widthMm - margins.left - margins.right)} / ${Math.max(
    1,
    heightMm - margins.top - margins.bottom,
  )}`
})
const selectedLetterhead = computed(
  () =>
    letterheads.value.find((item) => item.id === draft.letterhead_id) ||
    letterheads.value.find((item) => item.is_default) ||
    null,
)
const letterheadOptions = computed(() => [
  { label: t('reports.useDefaultLetterheadOption'), value: null },
  ...letterheads.value.map((item) => ({
    label: `${item.name}${item.is_default ? ` · ${t('reports.default')}` : ''}`,
    value: item.id,
  })),
])
const jobOptions = computed(() =>
  jobs.value.map((job) => ({ label: `${job.title}${job.venue_name ? ` · ${job.venue_name}` : ''}`, value: job.id })),
)

function applyTemplate(template) {
  if (!template) return
  draft.name = template.name
  draft.body_html = template.body_html
  draft.layout_json = Array.isArray(template.layout_json)
    ? template.layout_json.map((item) => ({ page: 0, ...item }))
    : [{ id: crypto.randomUUID(), page: 0, x: 0, y: 0, width: 100, height: 100, html: template.body_html }]
  draft.page_count = Math.max(template.page_count || 1, 1)
  Object.assign(draft.stage_plot_options, {
    view: 'stage',
    show_coverage: false,
    show_camera_coverage: false,
    show_projector_coverage: false,
    camera_view_mode: 'range',
    show_cables: false,
    show_cableways: false,
    ...(template.stage_plot_options || {}),
  })
  currentLayoutPage.value = 0
  selectedLayoutId.value = draft.layout_json.find((item) => item.page === 0)?.id || null
  draft.letterhead_id = template.letterhead_id
  draft.is_default = template.is_default
}

function layoutObjectLabel(item) {
  if (item.html.includes('{{stage_plot}}')) return t('reports.stagePlotDiagram')
  if (item.html.includes('{{table:')) return t('reports.dataTableObject')
  if (item.html.includes('{{')) return t('reports.dataFieldObject')
  return t('reports.textObject')
}

function addLayoutObject(type, token) {
  const index = draft.layout_json.length
  const height = type === 'stage_plot' ? 42 : type === 'table' ? 32 : type === 'text' ? 20 : 12
  const y = Math.min(5 + index * 12, 100 - height)
  const html = type === 'text' ? '<p>Text</p>' : `<p>${token}</p>`
  const item = {
    id: crypto.randomUUID(),
    page: currentLayoutPage.value,
    x: 5,
    y,
    width: 90,
    height,
    html,
    stage_plot_scale: 'fit',
  }
  draft.layout_json = [...draft.layout_json, item]
  selectedLayoutId.value = item.id
}

function addLayoutPage() {
  if (draft.page_count >= 100) return
  draft.page_count += 1
  currentLayoutPage.value = draft.page_count - 1
  selectedLayoutId.value = null
}

function removeLayoutObject(id) {
  draft.layout_json = draft.layout_json.filter((item) => item.id !== id)
  selectedLayoutId.value =
    draft.layout_json.find((item) => item.page === currentLayoutPage.value)?.id || null
}

async function loadPage() {
  loading.value = true
  pageError.value = ''
  try {
    const [types, loadedTemplates, loadedLetterheads, loadedJobs] = await Promise.all([
      store.fetchTypes(selectedLocale.value),
      store.fetchTemplates(),
      store.fetchLetterheads(),
      store.fetchJobs(),
    ])
    reportTypes.value = types
    templates.value = loadedTemplates
    letterheads.value = loadedLetterheads
    jobs.value = loadedJobs
    selectedTemplateId.value =
      loadedTemplates.find((item) => item.locale === selectedLocale.value && item.is_default)?.id ||
      loadedTemplates.find((item) => item.locale === selectedLocale.value)?.id ||
      null
    previewJobId.value = loadedJobs[0]?.id || null
  } catch (error) {
    pageError.value = error?.response?.data?.detail || t('reports.failedLoad')
  } finally {
    loading.value = false
  }
}

async function saveTemplate() {
  if (!selectedTemplate.value) return
  saving.value = true
  try {
    const updated = await store.updateTemplate(selectedTemplate.value.id, {
      name: draft.name.trim(),
      body_html: draft.body_html,
      layout_json: draft.layout_json,
      page_count: draft.page_count,
      stage_plot_options: { ...draft.stage_plot_options },
      letterhead_id: draft.letterhead_id,
      is_default: draft.is_default,
    })
    templates.value = await store.fetchTemplates()
    selectedTemplateId.value = updated.id
    applyTemplate(updated)
    $q.notify({ type: 'positive', message: t('reports.templateSaved') })
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedSave') })
  } finally {
    saving.value = false
  }
}

async function duplicateTemplate() {
  if (!selectedTemplate.value) return
  try {
    const duplicate = await store.createTemplate({
      domain: selectedTemplate.value.domain,
      report_type: selectedTemplate.value.report_type,
      locale: selectedLocale.value,
      name: `${draft.name} (${t('reports.copy')})`,
      body_html: draft.body_html,
      layout_json: draft.layout_json,
      page_count: draft.page_count,
      stage_plot_options: { ...draft.stage_plot_options },
      letterhead_id: draft.letterhead_id,
    })
    templates.value = await store.fetchTemplates()
    selectedTemplateId.value = duplicate.id
    applyTemplate(duplicate)
    $q.notify({ type: 'positive', message: t('reports.templateDuplicated') })
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedSave') })
  }
}

function deleteTemplate() {
  const deletedTemplate = selectedTemplate.value
  if (!deletedTemplate) return
  $q.dialog({
    title: t('reports.deleteTemplate'),
    message: t('reports.deleteTemplateConfirm', { name: deletedTemplate.name }),
    cancel: t('app.actions.cancel'),
    ok: t('app.actions.delete'),
    persistent: true,
  }).onOk(async () => {
    try {
      await store.deleteTemplate(deletedTemplate.id)
      templates.value = await store.fetchTemplates()
      selectedTemplateId.value = templates.value.find(
        (item) =>
          item.domain === deletedTemplate.domain &&
          item.report_type === deletedTemplate.report_type &&
          item.locale === selectedLocale.value &&
          item.is_default,
      )?.id || templates.value[0]?.id || null
      $q.notify({ type: 'positive', message: t('reports.templateDeleted') })
    } catch (error) {
      $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedDelete') })
    }
  })
}

async function previewTemplate() {
  if (!selectedTemplate.value || !previewJobId.value) return
  previewing.value = true
  try {
    const options = currentType.value?.requires_patchpoint
      ? { patchpoint_id: previewPatchpointId.value }
      : {}
    const blob = await store.fetchPreview(
      previewJobId.value,
      selectedTemplate.value,
      'blob',
      options,
    )
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedPreview') })
  } finally {
    previewing.value = false
  }
}

async function uploadLetterhead() {
  if (!uploadFile.value) return
  uploading.value = true
  try {
    const letterhead = await store.uploadLetterhead(uploadFile.value, {
      name: uploadName.value.trim(),
      is_default: uploadDefault.value,
    })
    letterheads.value = await store.fetchLetterheads()
    showUpload.value = false
    uploadFile.value = null
    uploadName.value = ''
    uploadDefault.value = false
    activeLetterheadId.value = letterhead.id
    $q.notify({ type: 'positive', message: t('reports.letterheadUploaded') })
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedUpload') })
  } finally {
    uploading.value = false
  }
}

async function setDefaultLetterhead(letterhead) {
  try {
    await store.updateLetterhead(letterhead.id, { is_default: true })
    letterheads.value = await store.fetchLetterheads()
    $q.notify({ type: 'positive', message: t('reports.defaultSet') })
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedSave') })
  }
}

async function loadLetterheadPreview(letterhead) {
  try {
    const blob = await store.fetchLetterheadPreview(letterhead.id)
    if (letterheadPreviewUrl.value) URL.revokeObjectURL(letterheadPreviewUrl.value)
    letterheadPreviewUrl.value = URL.createObjectURL(blob)
    activeLetterheadId.value = letterhead.id
    marginDraft.top = letterhead.margin_top_mm
    marginDraft.bottom = letterhead.margin_bottom_mm
    marginDraft.left = letterhead.margin_left_mm
    marginDraft.right = letterhead.margin_right_mm
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedPreview') })
  }
}

async function saveMargins(letterhead) {
  try {
    await store.updateLetterhead(letterhead.id, {
      margin_top_mm: marginDraft.top,
      margin_bottom_mm: marginDraft.bottom,
      margin_left_mm: marginDraft.left,
      margin_right_mm: marginDraft.right,
    })
    letterheads.value = await store.fetchLetterheads()
    $q.notify({ type: 'positive', message: t('reports.marginsSaved') })
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedSave') })
  }
}

async function deleteLetterhead(letterhead) {
  $q.dialog({
    title: t('reports.deleteLetterhead'),
    message: t('reports.deleteLetterheadConfirm', { name: letterhead.name }),
    cancel: t('app.actions.cancel'),
    ok: t('app.actions.delete'),
    persistent: true,
  }).onOk(async () => {
    try {
      await store.deleteLetterhead(letterhead.id)
      letterheads.value = await store.fetchLetterheads()
      if (activeLetterheadId.value === letterhead.id) activeLetterheadId.value = null
      $q.notify({ type: 'positive', message: t('reports.letterheadDeleted') })
    } catch (error) {
      $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedDelete') })
    }
  })
}

function letterheadPageStyle(letterhead) {
  return { aspectRatio: `${letterhead.page_width_pt} / ${letterhead.page_height_pt}` }
}

function marginStyle(letterhead) {
  const widthMm = (letterhead.page_width_pt * 25.4) / 72
  const heightMm = (letterhead.page_height_pt * 25.4) / 72
  const margins =
    activeLetterheadId.value === letterhead.id
      ? marginDraft
      : {
          top: letterhead.margin_top_mm,
          bottom: letterhead.margin_bottom_mm,
          left: letterhead.margin_left_mm,
          right: letterhead.margin_right_mm,
        }
  return {
    top: `${((Number(margins.top) || 0) / heightMm) * 100}%`,
    bottom: `${((Number(margins.bottom) || 0) / heightMm) * 100}%`,
    left: `${((Number(margins.left) || 0) / widthMm) * 100}%`,
    right: `${((Number(margins.right) || 0) / widthMm) * 100}%`,
  }
}

watch(
  () => draft.layout_json,
  (layout) => {
    draft.body_html = layout.map((item) => item.html).join('')
  },
  { deep: true },
)

watch(selectedTemplateId, (id) => {
  const template = templates.value.find((item) => item.id === id)
  if (!template) return
  applyTemplate(template)
  if (selectedLocale.value !== template.locale) selectedLocale.value = template.locale
})

watch(currentLayoutPage, (page) => {
  const selected = selectedLayoutItem.value
  if (selected && selected.page !== page) selectedLayoutId.value = null
  if (!selectedLayoutId.value) {
    selectedLayoutId.value = draft.layout_json.find((item) => item.page === page)?.id || null
  }
})

watch(selectedLocale, async (value) => {
  try {
    reportTypes.value = await store.fetchTypes(value)
    const selected = selectedTemplate.value
    if (selected?.locale === value) return
    const matching = templates.value.filter(
      (item) =>
        item.locale === value &&
        item.domain === selected?.domain &&
        item.report_type === selected?.report_type,
    )
    selectedTemplateId.value =
      matching.find((item) => item.is_default)?.id || matching[0]?.id || templateOptions.value[0]?.value || null
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedLoad') })
  }
})

watch(locale, (value) => {
  if (value === 'en' || value === 'sv') selectedLocale.value = value
})

watch(previewJobId, async (jobId) => {
  previewPatchpointId.value = null
  previewPatchpointSheets.value = []
  if (!jobId) {
    loadingPreviewPatchpoints.value = false
    stagePlotElements.value = []
    stagePlotCables.value = []
    stagePlotDevices.value = []
    stagePlotCameras.value = {}
    return
  }
  loadingPreviewPatchpoints.value = true
  try {
    const [plotData, patchpointSheets] = await Promise.all([
      store.fetchStagePlotData(jobId, previewJob.value || {}),
      store.fetchPatchSheets(jobId),
    ])
    if (previewJobId.value !== jobId) return
    stagePlotElements.value = plotData.elements
    stagePlotCables.value = plotData.cables
    stagePlotDevices.value = plotData.devices
    stagePlotCameras.value = plotData.cameras
    previewPatchpointSheets.value = patchpointSheets
    previewPatchpointId.value = patchpointSheets[0]?.device_id || null
  } catch (error) {
    $q.notify({ type: 'negative', message: error?.response?.data?.detail || t('reports.failedLoad') })
  } finally {
    if (previewJobId.value === jobId) loadingPreviewPatchpoints.value = false
  }
})

onMounted(() => {
  if (!isAdmin.value) {
    pageError.value = t('common.errorOccurred')
    loading.value = false
    return
  }
  loadPage()
})
onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  if (letterheadPreviewUrl.value) URL.revokeObjectURL(letterheadPreviewUrl.value)
})
</script>

<style scoped>
.letterhead-select {
  min-width: 240px;
}

:deep(.q-editor__content) {
  font-size: 14px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

:deep(.q-editor__content h1) {
  font-size: 1.5em;
  line-height: 1.25;
}

:deep(.q-editor__content h2) {
  font-size: 1.2em;
  line-height: 1.35;
}

.report-preview {
  display: block;
  width: 100%;
  height: min(70vh, 760px);
  border: 1px solid var(--ec-border, #394247);
  background: white;
}

.letterhead-preview-frame {
  position: relative;
  width: min(100%, 240px);
  max-height: 340px;
  margin: 0 auto;
  overflow: hidden;
  background: white;
  border: 1px solid #bbc4c7;
}

.letterhead-pdf {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
}

.letterhead-printable {
  position: absolute;
  display: grid;
  place-items: center;
  border: 1px dashed #3f873f;
  background: rgb(63 135 63 / 8%);
  color: #285e2e;
  font-size: 10px;
  pointer-events: none;
}

.upload-card {
  width: min(92vw, 480px);
}
</style>
