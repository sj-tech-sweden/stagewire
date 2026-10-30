<template>
  <q-page padding>
    <ReportGenerationDialog
      v-model="reportDialog"
      :job-id="jobId"
    />
    <StageVenueDialog
      v-model="stageVenueOpen"
      :job-id="jobId"
      :frame="plotFrame.frame.value"
      @saved="stageVenueSaved"
      @error="(err) => $q.notify({ type: 'negative', message: errorText(err) })"
    />
    <ConflictDialog
      :conflict="graph.conflict"
      @resolve="(r) => graph.resolveConflict(r).catch(() => {})"
      @discard="graph.clearConflict()"
    />

    <div class="row items-center q-col-gutter-sm q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('workspace.back')"
        @click="router.push(`/jobs/${jobId}`)"
      />
      <div class="col">
        <div class="text-h6">
          {{ t('workspace.title') }}
        </div>
        <div
          v-if="job"
          class="text-subtitle2 text-grey-7"
        >
          {{ job.title }}
        </div>
      </div>
      <q-btn
        color="primary"
        no-caps
        icon="inventory_2"
        :label="t('workspace.catalog')"
        data-testid="open-catalog"
        @click="catalogOpen = true"
      />
      <q-btn-dropdown
        flat
        no-caps
        icon="file_upload"
        :label="t('workspace.import')"
        data-testid="import-menu"
      >
        <q-list>
          <q-item
            v-close-popup
            clickable
            data-testid="import-fixtures-file"
            @click="importInput.click()"
          >
            <q-item-section>
              <q-item-label>{{ t('workspace.importFixtures') }}</q-item-label>
              <q-item-label caption>
                CSV, MVR
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-btn-dropdown>
      <input
        ref="importInput"
        type="file"
        accept=".csv,.mvr"
        class="hidden"
        data-testid="header-import-file"
        @change="importFixturesFile"
      >
      <q-btn-dropdown
        v-if="graph.channelLists.length"
        flat
        no-caps
        icon="file_download"
        :label="t('workspace.export')"
        data-testid="export-menu"
        @before-show="loadPlugins"
      >
        <q-list>
          <template
            v-for="list in graph.channelLists"
            :key="list.id"
          >
            <q-item-label header>
              {{ list.name }}
            </q-item-label>
            <q-item
              v-for="plugin in plugins"
              :key="`${list.id}-${plugin.key}`"
              v-close-popup
              clickable
              :data-testid="`export-${plugin.key}`"
              @click="exportList(list, plugin)"
            >
              <q-item-section>
                <q-item-label>{{ plugin.label }}</q-item-label>
              </q-item-section>
            </q-item>
          </template>
        </q-list>
      </q-btn-dropdown>
      <q-btn
        flat
        no-caps
        icon="picture_as_pdf"
        :label="t('workspace.pdfReports')"
        data-testid="open-reports"
        @click="reportDialog = true"
      />
    </div>

    <q-tabs
      :model-value="graph.mode"
      dense
      no-caps
      align="left"
      mobile-arrows
      active-color="primary"
      indicator-color="primary"
      class="q-mb-md workspace-tabs"
      data-testid="mode-toggle"
      @update:model-value="switchMode"
    >
      <q-tab
        v-for="tab in modeTabs"
        :key="tab.value"
        :name="tab.value"
        :icon="tab.icon"
        :label="tab.label"
      />
    </q-tabs>

    <div class="row items-center q-gutter-sm q-mb-md">
      <span class="text-caption text-grey-6">{{ t('workspace.layers') }}</span>
      <q-chip
        v-for="layer in LAYERS"
        :key="layer.key"
        clickable
        dense
        :color="layers[layer.key] ? 'primary' : 'grey-7'"
        text-color="white"
        :data-testid="`layer-${layer.key}`"
        @click="layers[layer.key] = !layers[layer.key]"
      >
        {{ t(layer.label) }}
      </q-chip>
      <q-space />
      <q-chip
        v-for="phase in ['L1', 'L2', 'L3']"
        :key="phase"
        dense
        :color="LEVEL_COLOR[phases[phase].level]"
        text-color="white"
        :data-testid="`phase-${phase}`"
      >
        {{ phase }} {{ Math.round(phases[phase].watts) }} W
      </q-chip>
      <q-chip
        v-if="phases.imbalanceLevel === 'warn'"
        dense
        color="warning"
        text-color="black"
        icon="warning"
      >
        {{ t('workspace.imbalance') }} {{ graph.loads.imbalance_pct }}%
      </q-chip>
    </div>

    <div class="row q-col-gutter-md">
      <div
        class="col-12 col-md"
        data-testid="drop-zone"
        @dragover.prevent
        @drop.prevent="onProductDrop"
      >
        <q-banner
          v-if="!graph.devices.length && !graph.loading && !['lists', 'devices', 'lights', 'video', 'power'].includes(graph.mode)"
          class="bg-grey-9 text-white rounded-borders"
        >
          {{ t('workspace.empty') }}
        </q-banner>
        <template v-else>
          <div
            v-if="graph.mode === 'canvas'"
            class="column items-end"
          >
            <q-btn-group
              flat
              class="q-mb-xs"
            >
              <q-btn
                dense
                no-caps
                icon="cable"
                :color="connectMode ? 'primary' : undefined"
                :label="t('workspace.connectTool')"
                data-testid="connect-tool"
                @click="connectMode = !connectMode"
              />
              <q-btn
                dense
                icon="remove"
                aria-label="zoom out"
                @click="zoom = Math.max(0.05, zoom / 1.2)"
              />
              <q-btn
                dense
                icon="add"
                aria-label="zoom in"
                @click="zoom = Math.min(2, zoom * 1.2)"
              />
              <q-btn
                dense
                icon="fit_screen"
                aria-label="fit"
                data-testid="canvas-fit"
                @click="fitCanvas"
              />
              <q-btn
                dense
                no-caps
                icon="aspect_ratio"
                :label="t('workspace.gearSize')"
              >
                <q-menu>
                  <div class="q-pa-md">
                    <q-slider
                      v-model="deviceScale"
                      :min="0.4"
                      :max="3"
                      :step="0.1"
                      style="width: 180px"
                      label
                      data-testid="gear-size"
                    />
                  </div>
                </q-menu>
              </q-btn>
              <q-btn
                dense
                no-caps
                icon="crop_free"
                :label="t('workspace.stageVenue')"
                data-testid="edit-stage-venue"
                @click="stageVenueOpen = true"
              />
              <q-btn-dropdown
                dense
                no-caps
                icon="category"
                :label="t('workspace.addObject')"
                data-testid="add-object"
              >
                <q-list>
                  <q-item
                    v-for="object in OBJECT_TYPES"
                    :key="object.type"
                    v-close-popup
                    clickable
                    :data-testid="`add-object-${object.type}`"
                    @click="addObject(object)"
                  >
                    <q-item-section avatar>
                      <q-icon
                        :name="object.icon"
                        :style="{ color: object.color }"
                      />
                    </q-item-section>
                    <q-item-section>{{ objectLabel(object) }}</q-item-section>
                  </q-item>
                </q-list>
              </q-btn-dropdown>
              <q-btn
                dense
                no-caps
                icon="power"
                :color="plotFrame.show.outlets.value ? 'primary' : undefined"
                :label="t('workspace.layerOutlets')"
                data-testid="layer-outlets"
                @click="plotFrame.show.outlets.value = !plotFrame.show.outlets.value"
              />
              <q-btn
                dense
                no-caps
                icon="groups"
                :color="plotFrame.show.audience.value ? 'primary' : undefined"
                :label="t('workspace.layerAudience')"
                data-testid="layer-audience"
                @click="plotFrame.show.audience.value = !plotFrame.show.audience.value"
              />
              <q-btn
                dense
                no-caps
                icon="surround_sound"
                :color="plotFrame.show.coverage.value ? 'primary' : undefined"
                :label="t('workspace.layerCoverage')"
                data-testid="layer-coverage"
                @click="plotFrame.show.coverage.value = !plotFrame.show.coverage.value"
              />
              <q-btn
                dense
                no-caps
                icon="videocam"
                :color="plotFrame.show.camera.value ? 'primary' : undefined"
                :label="t('workspace.layerCamera')"
                data-testid="layer-camera"
                @click="plotFrame.show.camera.value = !plotFrame.show.camera.value"
              />
              <q-btn
                dense
                no-caps
                icon="cast"
                :color="plotFrame.show.projector.value ? 'primary' : undefined"
                :label="t('workspace.layerProjector')"
                data-testid="layer-projector"
                @click="plotFrame.show.projector.value = !plotFrame.show.projector.value"
              />
              <q-btn-toggle
                v-if="plotFrame.show.camera.value"
                v-model="plotFrame.cameraMode.value"
                dense
                no-caps
                unelevated
                toggle-color="primary"
                :options="[
                  { label: t('stagePlot.cameraViewRange'), value: 'range' },
                  { label: t('stagePlot.cameraViewChosen'), value: 'chosen' },
                ]"
              />
            </q-btn-group>
            <div
              v-if="unplacedGear.length"
              class="row items-center q-gutter-xs q-mb-xs full-width"
              data-testid="unplaced-gear"
            >
              <span class="text-caption text-grey-6">{{ t('workspace.notOnPlot') }}</span>
              <q-chip
                v-for="gear in unplacedGear"
                :key="gear.id"
                dense
                clickable
                icon="add_location_alt"
                data-testid="place-gear"
                @click="placeGear(gear)"
              >
                {{ gear.name }}
              </q-chip>
            </div>
            <WorkspaceCanvas
              class="full-width"
              :devices="canvasDevices"
              :edges="canvasEdges"
              :selected-id="graph.selectedDeviceId"
              :zoom="zoom"
              :device-scale="deviceScale"
              :frame="plotFrame.frame.value"
              :outlets="plotFrame.outlets.value"
              :show-outlets="plotFrame.show.outlets.value"
              :show-audience="plotFrame.show.audience.value"
              :coverage-image="plotFrame.coverageImage.value"
              :shapes="viewShapes"
              :connect-mode="connectMode"
              @select="select"
              @move="move"
              @connect="connectDevices"
            />
          </div>
          <ChannelListEditor
            v-else-if="graph.mode === 'lists'"
            :job-id="jobId"
          />
          <DeviceEditor
            v-else-if="graph.mode === 'devices'"
            :job-id="jobId"
          />
          <LightsEditor
            v-else-if="graph.mode === 'lights'"
            :job-id="jobId"
          />
          <VideoEditor
            v-else-if="graph.mode === 'video'"
            :job-id="jobId"
          />
          <RiggingEditor
            v-else-if="graph.mode === 'power'"
            :job-id="jobId"
          />
          <WorkspaceTable
            v-else
            :job-id="jobId"
            :devices="listDevices"
            :selected-id="graph.selectedDeviceId"
            @select="select"
            @request-booking="requestBooking"
          />
        </template>
      </div>

      <div
        v-if="$q.screen.gt.sm"
        class="col-md-4 col-lg-3"
      >
        <q-card
          flat
          bordered
        >
          <DeviceInspector
            :job-id="jobId"
            :device="graph.selectedDevice"
            @request-booking="requestBooking"
            @remove="removeDevice"
          />
        </q-card>
      </div>
    </div>

    <q-dialog
      v-if="$q.screen.lt.md"
      :model-value="inspectorOpen"
      position="bottom"
      @update:model-value="(v) => !v && (graph.selectedDeviceId = null)"
    >
      <q-card style="width: 100%; max-height: 80vh; overflow: auto">
        <DeviceInspector
          :job-id="jobId"
          :device="graph.selectedDevice"
          @request-booking="requestBooking"
          @remove="removeDevice"
        />
      </q-card>
    </q-dialog>

    <div class="q-mt-md">
      <MultiDomainPatchDrawer :job-id="jobId" />
    </div>

    <StockwireCatalogDrawer
      v-model="catalogOpen"
      :job-id="jobId"
      :stockwire-job-id="job?.stockwire_job_id || null"
    />
  </q-page>
</template>

<script setup>
import { isRevisionConflict } from '@/utils/graph';
import StageVenueDialog from '@/components/StageVenueDialog.vue';
import ReportGenerationDialog from '@/components/ReportGenerationDialog.vue';
import { elementsFromGraph, legacyId } from '@/utils/graphLegacy';
import { usePlotFrame } from '@/composables/usePlotFrame';
import { OBJECT_TYPES } from '@/utils/plotObjects';
import { useStagePlotStore } from '@/stores/stageplot';
import { fitWidthZoom, stageCentre, stagePosition } from '@/utils/plotFrame';
import { computed, onMounted, ref, watch, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import { useGraphStore } from '@/stores/graph';
import { useJobSocket } from '@/composables/useJobSocket';
import {
  PRODUCT_MIME,
  deviceFromProduct,
  devicesShownAsElements,
  isPlotElement,
  isVirtual,
  linkRoleFor,
  phaseStatus,
  suggestPorts,
  visibleOnLayers,
} from '@/utils/workspace';
import ConflictDialog from '@/components/ConflictDialog.vue';
import DeviceInspector from '@/components/DeviceInspector.vue';
import MultiDomainPatchDrawer from '@/components/MultiDomainPatchDrawer.vue';
import StockwireCatalogDrawer from '@/components/StockwireCatalogDrawer.vue';
import ChannelListEditor from '@/components/ChannelListEditor.vue';
import DeviceEditor from '@/components/DeviceEditor.vue';
import LightsEditor from '@/components/LightsEditor.vue';
import VideoEditor from '@/components/VideoEditor.vue';
import RiggingEditor from '@/components/RiggingEditor.vue';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import WorkspaceTable from '@/components/WorkspaceTable.vue';

const LAYERS = [
  { key: 'audio', label: 'workspace.layerAudio' },
  { key: 'lighting', label: 'workspace.layerLighting' },
  { key: 'video', label: 'workspace.layerVideo' },
  { key: 'power', label: 'workspace.layerPower' },
];
const SIGNAL_LAYER = { audio: 'audio', dmx: 'lighting', video: 'video', power: 'power' };
const LEVEL_COLOR = { ok: 'positive', warn: 'warning', over: 'negative' };

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const jobId = String(route.params.jobId);

const job = ref(null);
const catalogOpen = ref(false);
const importing = ref(false);
const modeTabs = computed(() => [
  { label: t('workspace.modeCanvas'), value: 'canvas', icon: 'map' },
  { label: t('workspace.modeList'), value: 'list', icon: 'table_rows' },
  { label: t('workspace.modeLists'), value: 'lists', icon: 'queue_music' },
  { label: t('workspace.modeDevices'), value: 'devices', icon: 'developer_board' },
  { label: t('workspace.modeLights'), value: 'lights', icon: 'lightbulb' },
  { label: t('workspace.modeVideo'), value: 'video', icon: 'videocam' },
  { label: t('workspace.modePower'), value: 'power', icon: 'bolt' },
]);
const zoom = ref(0.3);
const deviceScale = ref(1);
const plotFrame = usePlotFrame(jobId);
const connectMode = ref(false);
const plugins = ref([]);
const layers = reactive({ audio: true, lighting: true, video: true, power: true });

const phases = computed(() => phaseStatus(graph.loads));
const listDevices = computed(() =>
  graph.devices
    .filter((d) => d.kind !== 'channel_list' && !isPlotElement(d) && visibleOnLayers(d, layers))
    .sort((a, b) => (a.domain === b.domain ? a.position - b.position : a.domain.localeCompare(b.domain))),
);
const shownAsElements = computed(() => devicesShownAsElements(graph.edges));
const canvasDevices = computed(() =>
  graph.devices.filter(
    (d) =>
      visibleOnLayers(d, layers) &&
      !isVirtual(d) &&
      !shownAsElements.value.has(d.id) &&
      d.canvas_x_cm != null &&
      d.canvas_y_cm != null,
  ),
);
// Gear is on the stage plot once it has a position. Anything else is offered as a chip to place,
// so the canvas never shows gear that is not part of the plot.
const unplacedGear = computed(() =>
  graph.devices.filter(
    (d) =>
      visibleOnLayers(d, layers) &&
      !isVirtual(d) &&
      !isPlotElement(d) &&
      !shownAsElements.value.has(d.id) &&
      (d.canvas_x_cm == null || d.canvas_y_cm == null),
  ),
);
// Camera and projector views of the placed plot elements (see utils/plotViews.js).
const viewShapes = computed(() => {
  const elements = elementsFromGraph(graph.devices, graph.edges);
  const byLegacy = new Map(graph.devices.map((d) => [legacyId(d), d]));
  return plotFrame.viewShapes(elements, (el) => byLegacy.get(el.linked_device_id)?.attributes || null);
});
const canvasEdges = computed(() =>
  graph.edges.filter((e) => e.signal !== 'link' && layers[SIGNAL_LAYER[e.signal]] !== false),
);
const inspectorOpen = computed(() => Boolean(graph.selectedDevice));

const modeKey = `sw_ws_mode_${jobId}`;
const errorText = (err) => err.response?.data?.detail?.message || err.response?.data?.detail || err.message;

let checkTimer = null;
function scheduleChecks() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(() => graph.refreshChecks(jobId).catch(() => {}), 400);
}

const socket = useJobSocket(jobId, (event) => {
  if (event.type?.startsWith('graph.')) {
    graph.applyRealtimeEvent(event);
    scheduleChecks();
  }
});

function select(id) {
  graph.selectedDeviceId = id;
}

async function switchMode(mode) {
  graph.setMode(mode);
  try {
    localStorage.setItem(modeKey, graph.mode);
  } catch {
    /* storage unavailable */
  }
}

async function move({ id, x, y }) {
  try {
    await graph.updateDevice(jobId, id, { canvas_x_cm: x, canvas_y_cm: y });
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: errorText(err) });
  }
}

async function connectDevices({ srcId, dstId }) {
  const src = graph.devices.find((d) => d.id === srcId);
  const dst = graph.devices.find((d) => d.id === dstId);
  if (isPlotElement(src)) {
    try {
      await graph.createEdge(jobId, {
        signal: 'link',
        src_device_id: srcId,
        src_port: 'link',
        dst_device_id: dstId,
        dst_port: linkRoleFor(dst),
      });
    } catch (err) {
      $q.notify({ type: 'negative', message: errorText(err) });
    }
    return;
  }
  const fit = suggestPorts(src, dst);
  if (!fit) {
    $q.notify({ type: 'negative', message: t('workspace.noFreePorts', { from: src.name, to: dst.name }) });
    return;
  }
  const payload = {
    signal: fit.signal,
    src_device_id: srcId,
    src_port: fit.srcPort,
    dst_device_id: dstId,
    dst_port: fit.dstPort,
    channels: 1,
  };
  try {
    await graph.createEdge(jobId, payload);
  } catch (err) {
    const detail = err.response?.data?.detail;
    if (detail?.code === 'invalid_connection') {
      $q.notify({
        type: 'negative',
        message: `${t('workspace.connectFailed')}: ${detail.issues.map((i) => i.message).join('; ')}`,
        actions: [
          {
            label: t('workspace.connectForce'),
            color: 'white',
            handler: () => graph.createEdge(jobId, payload, { force: true }).catch(() => {}),
          },
        ],
      });
    } else {
      $q.notify({ type: 'negative', message: typeof detail === 'string' ? detail : err.message });
    }
  }
}

async function onProductDrop(event) {
  const raw = event.dataTransfer?.getData(PRODUCT_MIME);
  if (!raw) return;
  const products = JSON.parse(raw);
  const canvas = event.target.closest?.('[data-testid="workspace-canvas"]');
  const rect = canvas?.getBoundingClientRect();
  try {
    const payloads = products.map((product, index) => {
      const device = deviceFromProduct(product);
      if (rect && graph.mode === 'canvas') {
        const at = stagePosition(
          event.clientX + index * 20 - rect.left,
          event.clientY + index * 20 - rect.top,
          zoom.value,
          plotFrame.frame.value,
        );
        device.canvas_x_cm = at.x;
        device.canvas_y_cm = at.y;
      }
      return device;
    });
    const created = await graph.createDevices(jobId, payloads);
    $q.notify({ type: 'positive', message: t('workspace.added', { n: created.length }) });
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

function fitCanvas() {
  const width = document.querySelector('[data-testid="workspace-canvas"]')?.clientWidth || 800;
  zoom.value = fitWidthZoom(plotFrame.frame.value, width);
}

async function placeGear(device) {
  const centre = stageCentre(plotFrame.frame.value);
  const offset = (graph.devices.filter((d) => d.canvas_x_cm != null).length % 5) * 20;
  try {
    await graph.updateDevice(jobId, device.id, {
      canvas_x_cm: centre.x + offset,
      canvas_y_cm: centre.y + offset,
    });
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: errorText(err) });
  }
}

async function loadPlugins() {
  if (plugins.value.length) return;
  plugins.value = await graph.exportPlugins(jobId).catch(() => []);
}

async function exportList(list, plugin) {
  try {
    const { blob, filename } = await graph.exportList(jobId, list.id, plugin.key);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    $q.notify({ type: 'negative', message: t('workspace.exportFailed') });
  }
}

const importInput = ref(null);
const reportDialog = ref(false);
const stageVenueOpen = ref(false);
const stagePlot = useStagePlotStore();
const objectLabel = (object) => (object.labelKey ? t(object.labelKey, object.label || object.type) : object.label);

async function stageVenueSaved() {
  await plotFrame.load();
  fitCanvas();
}

// A plot object (performer, table, riser, ...) is a plot element: it has a position and size and
// can be linked to a channel or device, but it is not gear. It is placed in the middle of the stage.
async function addObject(object) {
  const centre = stageCentre(plotFrame.frame.value, Math.max(object.w, object.h));
  try {
    const created = await stagePlot.createElement(jobId, {
      element_type: object.type,
      label: objectLabel(object),
      position_x: centre.x,
      position_y: centre.y,
      width_cm: object.w,
      height_cm: object.h,
    });
    graph.selectedDeviceId = stagePlot.nodeOf(created.id)?.id || null;
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

// Import brings in what was made elsewhere: today a fixture patch (CSV, or an MVR export from
// Capture, MA, Vectorworks or WYSIWYG). Fixtures land in the lights editor like added ones.
async function importFixturesFile(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  importing.value = true;
  try {
    const result = await graph.importFixtures(jobId, file);
    $q.notify({
      type: result.errors?.length ? 'warning' : 'positive',
      message: t('workspace.imported', { n: result.created }),
    });
    scheduleChecks();
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  } finally {
    importing.value = false;
  }
}

async function requestBooking(device) {
  try {
    await graph.requestStockwireBooking(jobId, device.id);
  } catch (err) {
    const message =
      err.response?.status === 409 ? t('workspace.requestNoJob') : t('workspace.requestFailed');
    $q.notify({ type: 'negative', message });
  }
}

function removeDevice(device) {
  $q.dialog({
    title: t('workspace.remove'),
    message: device.name,
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await graph.deleteDevice(jobId, device.id);
      graph.selectedDeviceId = null;
      scheduleChecks();
    } catch (err) {
      if (!isRevisionConflict(err)) {
        $q.notify({ type: 'negative', message: t('workspace.removeFail') });
      }
    }
  });
}

watch(
  () => graph.edges.length,
  () => scheduleChecks(),
);

// Coverage comes from the placed speakers and cameras, so it is recomputed when they change.
let coverageTimer = null;
watch(
  () =>
    graph.devices
      .filter((d) => d.canvas_x_cm != null)
      .map((d) => [d.id, d.canvas_x_cm, d.canvas_y_cm, d.canvas_rotation, d.revision].join(':'))
      .join('|'),
  () => {
    clearTimeout(coverageTimer);
    coverageTimer = setTimeout(() => {
      plotFrame.loadCoverage();
      plotFrame.loadCameraSpecs();
    }, 400);
  },
);

onMounted(async () => {
  try {
    const { data } = await api.get(`/jobs/${jobId}`);
    job.value = data;
  } catch {
    /* the page still works without the job header */
  }
  try {
    graph.setMode(localStorage.getItem(modeKey) || 'canvas');
  } catch {
    graph.setMode('canvas');
  }
  graph.selectedDeviceId = null;
  await Promise.all([graph.fetchGraph(jobId), plotFrame.load()]);
  fitCanvas();
  scheduleChecks();
  socket.connect();
});
</script>
