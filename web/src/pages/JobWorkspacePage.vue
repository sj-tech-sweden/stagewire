<template>
  <q-page padding>
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
      <q-btn-toggle
        :model-value="graph.mode"
        no-caps
        unelevated
        toggle-color="primary"
        :options="[
          { label: t('workspace.modeCanvas'), value: 'canvas', icon: 'map' },
          { label: t('workspace.modeList'), value: 'list', icon: 'table_rows' },
          { label: t('workspace.modeLists'), value: 'lists', icon: 'queue_music' },
          { label: t('workspace.modeDevices'), value: 'devices', icon: 'developer_board' },
          { label: t('workspace.modeLights'), value: 'lights', icon: 'lightbulb' },
          { label: t('workspace.modeVideo'), value: 'video', icon: 'videocam' },
          { label: t('workspace.modePower'), value: 'power', icon: 'bolt' },
        ]"
        style="max-width: 100%; overflow-x: auto"
        data-testid="mode-toggle"
        @update:model-value="switchMode"
      />
      <q-btn
        color="primary"
        no-caps
        icon="inventory_2"
        :label="t('workspace.catalog')"
        data-testid="open-catalog"
        @click="catalogOpen = true"
      />
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
        icon="download"
        :loading="importing"
        :label="t('workspace.importLegacy')"
        data-testid="import-legacy"
        @click="importLegacy"
      />
    </div>

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
                @click="zoom = Math.max(0.3, zoom - 0.1)"
              />
              <q-btn
                dense
                icon="add"
                aria-label="zoom in"
                @click="zoom = Math.min(2, zoom + 0.1)"
              />
            </q-btn-group>
            <WorkspaceCanvas
              class="full-width"
              :devices="canvasDevices"
              :edges="canvasEdges"
              :selected-id="graph.selectedDeviceId"
              :zoom="zoom"
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
  dropPosition,
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
const zoom = ref(0.8);
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
  if (mode === 'canvas') await graph.placeUnplacedDevices(jobId).catch(() => {});
}

async function move({ id, x, y }) {
  try {
    await graph.updateDevice(jobId, id, { canvas_x_cm: x, canvas_y_cm: y });
  } catch (err) {
    if (err.response?.status !== 409) $q.notify({ type: 'negative', message: errorText(err) });
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
        const at = dropPosition(event.clientX + index * 20, event.clientY + index * 20, rect, zoom.value);
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

async function importLegacy() {
  importing.value = true;
  try {
    const result = await graph.backfill(jobId);
    $q.notify({
      type: 'positive',
      message: t('workspace.importDone', { devices: result.devices, edges: result.edges }),
    });
    if (graph.mode === 'canvas') await graph.placeUnplacedDevices(jobId);
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
      if (err.response?.status !== 409) {
        $q.notify({ type: 'negative', message: t('workspace.removeFail') });
      }
    }
  });
}

watch(
  () => graph.edges.length,
  () => scheduleChecks(),
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
  await graph.fetchGraph(jobId);
  if (graph.mode === 'canvas') await graph.placeUnplacedDevices(jobId).catch(() => {});
  scheduleChecks();
  socket.connect();
});
</script>
