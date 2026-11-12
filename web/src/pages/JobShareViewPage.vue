<template>
  <!-- Standalone page: it is routed outside MainLayout, so it must supply its own QLayout
       (Quasar requires q-page to be a deep child of q-layout). -->
  <q-layout view="lHh Lpr lff">
    <q-page-container>
      <q-page
      class="bg-grey-10 text-white q-pa-sm"
      :data-socket="live ? 'open' : 'closed'"
    >
    <!-- The crew view is deliberately stripped of chrome: no nav, no edit tools. -->
    <div
      v-if="error"
      class="q-pa-lg text-center"
      data-testid="share-error"
    >
      <q-icon
        name="link_off"
        size="3rem"
        color="grey-6"
      />
      <div class="text-h6 q-mt-sm">
        {{ t('workspace.share.invalidOrExpired') }}
      </div>
    </div>

    <template v-else-if="loaded">
      <div class="row items-center q-px-sm q-py-xs">
        <div class="col">
          <div class="text-subtitle1 text-weight-medium ellipsis">
            {{ job.title }}
          </div>
          <div class="text-caption text-grey-5">
            <q-icon
              name="visibility"
              size="1rem"
              class="q-mr-xs"
            />
            {{
              canBindAssets
                ? t('workspace.share.assetAssignmentEnabled')
                : t('workspace.share.readOnly')
            }}
          </div>
        </div>
        <q-chip
          dense
          size="sm"
          :color="live ? 'positive' : 'grey-7'"
          :icon="live ? 'wifi' : 'wifi_off'"
          :label="live ? t('workspace.share.live') : t('workspace.share.offline')"
          data-testid="share-live"
        />
      </div>

      <q-tabs
        v-model="tab"
        dense
        align="center"
        class="text-grey-4 bg-grey-9 rounded-borders q-mb-sm"
      >
        <q-tab
          name="list"
          icon="list"
          :label="t('workspace.share.list')"
        />
        <q-tab
          name="map"
          icon="map"
          :label="t('workspace.share.map')"
          data-testid="share-tab-map"
        />
        <q-tab
          name="scan"
          icon="qr_code_scanner"
          :label="t('workspace.scan.openScan')"
          data-testid="share-tab-scan"
        />
        <q-tab
          name="patch"
          icon="cable"
          :label="t('workspace.share.patch')"
          data-testid="share-tab-patch"
        />
      </q-tabs>

      <q-tab-panels
        v-model="tab"
        animated
      >
        <!-- List / search view: browse devices and expand one for its day-of-show detail. -->
        <q-tab-panel
          name="list"
          class="q-pa-none"
        >
          <q-input
            v-model="search"
            dense
            outlined
            dark
            color="primary"
            :placeholder="t('workspace.share.searchDevices')"
            class="q-mx-sm q-mb-sm"
            data-testid="share-search"
          >
            <template #prepend>
              <q-icon name="search" />
            </template>
          </q-input>

          <q-list
            separator
            data-testid="share-device-list"
          >
            <q-expansion-item
              v-for="device in filteredDevices"
              :key="device.id"
              group="devices"
              dense
              :label="device.name"
              :data-testid="`share-device-${device.id}`"
            >
              <template #header>
                <q-item-section avatar>
                  <q-chip
                    dense
                    size="sm"
                    color="primary"
                    text-color="white"
                    class="text-capitalize"
                  >
                    {{ device.domain }}
                  </q-chip>
                </q-item-section>
                <q-item-section>{{ device.name }}</q-item-section>
                <q-item-section side>
                  <q-btn
                    flat
                    round
                    dense
                    icon="open_in_new"
                    :aria-label="t('workspace.openDevice')"
                    :data-testid="`share-device-inspect-${device.id}`"
                    @click.stop="inspectId = device.id"
                  />
                </q-item-section>
              </template>

              <div class="q-pa-sm bg-grey-9">
                <DeviceShareDetail
                  :device="device"
                  :devices="devices"
                  :edges="edges"
                  @inspect="inspectId = device.id"
                />
              </div>
            </q-expansion-item>
            <div
              v-if="!filteredDevices.length"
              class="text-grey-5 q-pa-md text-center"
            >
              {{ t('workspace.share.noDevices') }}
            </div>
          </q-list>
        </q-tab-panel>

        <!-- Stage-map view: tap a placed device to inspect it. -->
        <q-tab-panel
          name="map"
          class="q-pa-none"
        >
          <div
            v-if="placedDevices.length"
            class="q-pa-sm"
          >
            <div
              ref="mapHost"
              data-testid="share-stage-map"
              class="full-width"
            >
              <WorkspaceCanvas
                :devices="placedDevices"
                :edges="edges"
                :frame="frame"
                :selected-id="selectedId"
                :zoom="zoom"
                :device-scale="1"
                readonly
                @select="(id) => (selectedId = id)"
              />
            </div>

            <div
              v-if="selectedPlaced"
              class="bg-grey-9 text-white q-mt-sm rounded-borders"
              data-testid="share-map-detail"
            >
              <DeviceInspector
                readonly
                :job-id="jobId"
                :device="selectedPlaced"
                :graph-data="shareGraph"
                :share-token="token"
                :can-bind-assets="canBindAssets"
                @asset-bound="updateSharedDevice"
                @select="(id) => { selectedId = id; tab = 'patch'; }"
              />
            </div>
          </div>
          <div
            v-else
            class="text-grey-5 q-pa-md text-center"
          >
            {{ t('workspace.share.noDevices') }}
          </div>
        </q-tab-panel>

        <!-- Scan view: multi-input capture (camera QR/barcode, NFC, keyboard wedge). A match
             opens its read-only inspector instead of changing any device data. -->
        <q-tab-panel
          name="scan"
          class="q-pa-sm"
        >
          <ScanCapture
            :active="tab === 'scan' && !inspectId"
            data-testid="share-scan"
            @captured="onScanned"
          />
          <q-banner
            v-if="lastScan"
            class="rounded-borders q-mt-md"
            :class="
              matchedDevice
                ? 'bg-positive text-white'
                : matchedDevices.length > 1
                  ? 'bg-info text-white'
                  : 'bg-warning text-dark'
            "
            data-testid="share-scan-result"
          >
            <template #avatar>
              <q-icon
                :name="
                  matchedDevice
                    ? 'check_circle'
                    : matchedDevices.length > 1
                      ? 'groups'
                      : 'warning'
                "
              />
            </template>
            <div class="text-caption text-grey-5">
              {{ t('workspace.scan.scanned') }}
            </div>
            <div class="text-body2">
              {{ lastScan }}
            </div>
            <div
              v-if="matchedDevice"
              class="text-caption"
            >
              {{ t('workspace.scan.matched', { name: matchedDevice.name }) }}
            </div>
            <div
              v-else-if="matchedDevices.length > 1"
              class="text-caption"
            >
              {{ t('workspace.scan.multipleMatches', { count: matchedDevices.length }) }}
            </div>
            <div
              v-else
              class="text-caption"
            >
              {{ t('workspace.scan.noMatch') }}
            </div>
          </q-banner>
          <q-list
            v-if="!matchedDevice && matchedDevices.length > 1"
            separator
            class="q-mt-sm"
            data-testid="share-scan-candidates"
          >
            <q-item
              v-for="device in matchedDevices"
              :key="device.id"
              clickable
              v-ripple
              :data-testid="`scan-match-${device.id}`"
              @click="selectScannedDevice(device)"
            >
              <q-item-section>
                <q-item-label>{{ device.name }}</q-item-label>
                <q-item-label caption>{{ scanCandidateDetails(device) }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-icon name="chevron_right" />
              </q-item-section>
            </q-item>
          </q-list>
        </q-tab-panel>
        <!-- Patch-list view: the full multi-domain patch table, read-only. Tapping a
             device name selects it (and opens its inspector below) so a crew member can
             trace a channel's cable flow without editing anything. -->
        <q-tab-panel
          name="patch"
          class="q-pa-sm"
        >
          <MultiDomainPatchDrawer
            readonly
            :graph="patchGraph"
            :update-edge="noopEdge"
            :delete-edge="noopEdge"
          />
          <div
            v-if="selected"
            class="bg-grey-9 text-white q-mt-sm rounded-borders"
            data-testid="share-patch-detail"
          >
            <DeviceInspector
              readonly
              :job-id="jobId"
              :device="selected"
              :graph-data="shareGraph"
              :share-token="token"
              :can-bind-assets="canBindAssets"
              @asset-bound="updateSharedDevice"
              @select="(id) => { selectedId = id; tab = 'patch'; }"
            />
          </div>
        </q-tab-panel>
      </q-tab-panels>

      <!-- Opening a device from the list shows its full read-only inspector (trace, source, ports),
           the same one the map and patch tabs use. Selecting a related device (e.g. a channel in a
           mixer) swaps the dialog to that device. -->
      <q-dialog
        :model-value="Boolean(inspectId)"
        position="right"
        @update:model-value="(v) => !v && (inspectId = null)"
      >
        <q-card style="width: 380px; max-width: 92vw; max-height: 90vh; overflow: auto">
          <DeviceInspector
            v-if="inspectDevice"
            readonly
            :job-id="jobId"
            :device="inspectDevice"
            :graph-data="shareGraph"
            :share-token="token"
            :can-bind-assets="canBindAssets"
            @asset-bound="updateSharedDevice"
            @select="(id) => (inspectId = id)"
          />
        </q-card>
      </q-dialog>
    </template>

    <div
      v-else
      class="q-pa-lg text-center"
    >
      <q-spinner
        color="primary"
        size="2rem"
      />
    </div>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import axios from 'axios';
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { getApiBaseUrl } from '@/utils/runtime-config';
import { isGear } from '@/utils/workspace';
import { frameFromJob, fitWidthZoom } from '@/utils/plotFrame';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import DeviceInspector from '@/components/DeviceInspector.vue';
import DeviceShareDetail from '@/components/DeviceShareDetail.vue';
import ScanCapture from '@/components/ScanCapture.vue';
import MultiDomainPatchDrawer from '@/components/MultiDomainPatchDrawer.vue';
import { useJobSocket } from '@/composables/useJobSocket';
import { applyLocale } from '@/i18n';

const { t } = useI18n();
const route = useRoute();

// A separate client (no auth interceptors) so a bad/expired token shows a friendly
// message here instead of the app's global "redirect to login" 401 handler.
const shareApi = axios.create({ baseURL: `${getApiBaseUrl()}/api/v1` });

const jobId = route.params.jobId;
const token = route.query.token;

// Live updates: the crew view only holds a view-scoped share token (no user session), so it opens
// the job websocket with that token. The backend admits a `view`-scoped token read-only.
const live = ref(false);
const { connect: connectSocket } = useJobSocket(
  jobId,
  handleSocketEvent,
  token,
  (status) => {
    live.value = status === 'open';
  },
);

function handleSocketEvent(event) {
  if (!event || !event.type) return;
  if (event.type === 'graph.device.upsert' || event.type === 'device.upsert') {
    const payload = event.payload;
    const idx = devices.value.findIndex((d) => d.id === payload.id);
    if (idx === -1) devices.value.push(payload);
    else devices.value[idx] = payload;
  } else if (event.type === 'graph.device.delete' || event.type === 'device.delete') {
    const id = typeof event.payload === 'object' && event.payload ? event.payload.id : event.payload;
    devices.value = devices.value.filter((d) => d.id !== id);
  } else if (event.type === 'graph.edge.upsert') {
    const payload = event.payload;
    const idx = edges.value.findIndex((edge) => edge.id === payload.id);
    if (idx === -1) edges.value.push(payload);
    else edges.value[idx] = payload;
  } else if (event.type === 'graph.edge.delete') {
    const id = typeof event.payload === 'object' && event.payload ? event.payload.id : event.payload;
    edges.value = edges.value.filter((edge) => edge.id !== id);
  }
}

function updateSharedDevice(device) {
  const idx = devices.value.findIndex((item) => item.id === device.id);
  if (idx !== -1) devices.value[idx] = device;
}

const loaded = ref(false);
const error = ref(false);
const canBindAssets = ref(false);
const job = ref({ title: '' });
const devices = ref([]);
const tab = ref('list');
const search = ref('');
const selectedId = ref(null);
const lastScan = ref('');
const matchedDevice = ref(null);
const matchedDevices = ref([]);
const edges = ref([]);
const shareGraph = computed(() => ({ devices: devices.value, edges: edges.value }));
// The device list offers a quick day-of-show summary (DeviceShareDetail) on expand; a crew member
// can also open the full read-only inspector for any listed device from the list itself.
const inspectId = ref(null);
const inspectDevice = computed(() => devices.value.find((d) => d.id === inspectId.value) || null);

// Only real gear (not channels, buses, channel lists) belongs in the crew list and on the map.
const gear = computed(() => devices.value.filter(isGear));

const filteredDevices = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return gear.value;
  return gear.value.filter((d) =>
    [d.name, d.domain, d.kind].join(' ').toLowerCase().includes(q),
  );
});

// Only real gear that has been placed on the plot is drawn on the map.
const placedDevices = computed(() =>
  gear.value.filter(
    (d) => typeof d.canvas_x_cm === 'number' && typeof d.canvas_y_cm === 'number',
  ),
);

const selected = computed(() => devices.value.find((d) => d.id === selectedId.value) || null);
// Only a device that is actually drawn on the map may open the map-tab inspector, so a
// channel selected from the patch tab never shows an inspector over an empty canvas.
const selectedPlaced = computed(() => placedDevices.value.find((d) => d.id === selectedId.value) || null);

// Read-only bridge to the multi-domain patch drawer. The drawer expects a graph store
// (edges/devices/issues + selectedId/selectedDeviceId it can mutate on device-link taps),
// but the crew view keeps its graph in plain refs, not the store. This reactive object
// projects those refs into the shape the drawer wants; its selectedId/selectedDeviceId
// setters write back to the crew's selectedId so a tap in the patch table selects the
// device here. Edge edits are rejected by the drawer's readonly guards, but we pass
// no-ops anyway.
const patchGraph = reactive({
  issues: [],
  get edges() {
    return edges.value;
  },
  get devices() {
    return devices.value;
  },
  get selectedId() {
    return selectedId.value;
  },
  set selectedId(v) {
    selectedId.value = v;
  },
  get selectedDeviceId() {
    return selectedId.value;
  },
  set selectedDeviceId(v) {
    selectedId.value = v;
  },
});
const noopEdge = async () => {};

// The same stage frame the editor draws, derived from the job's geometry, so the read-only
// map looks and feels identical to the workspace canvas.
const frame = computed(() => frameFromJob(job.value));

// Fit the stage frame to the panel width; fall back to a readable default until measured.
const mapHost = ref(null);
const mapWidth = ref(0);
const zoom = ref(0.8);
function fitMap() {
  const w = mapWidth.value || mapHost.value?.clientWidth || 0;
  if (w && frame.value?.width) zoom.value = fitWidthZoom(frame.value, w);
}

async function load() {
  if (!token) {
    error.value = true;
    return;
  }
  try {
    const { data } = await shareApi.get(`/jobs/${jobId}/mobile-view`, { params: { token } });
    job.value = data.job;
    devices.value = data.graph.devices;
    edges.value = data.graph.edges || [];
    canBindAssets.value = data.can_bind_assets === true;
    // Apply the link's locale before the view renders so the crew member sees the UI in the
    // language the creator shared it in, not their own browser default.
    if (data.locale) applyLocale(data.locale);
    loaded.value = true;
    // Now that we have a baseline, follow live graph updates (mixer channels/buses, map moves, …).
    connectSocket();
  } catch {
    error.value = true;
  }
}

load();

// Fit the stage frame to the panel once the map is shown or the job (and thus frame) arrives.
watch([tab, frame], () => {
  if (tab.value === 'map') nextTick(fitMap);
});
onMounted(() => {
  if (tab.value === 'map') nextTick(fitMap);
});

// Scanning looks up (rather than edits) gear by bound asset, Stockwire product, or name. If a
// shared product identifier matches several pieces of gear, require an explicit crew choice.
function onScanned(value) {
  lastScan.value = value;
  const q = String(value).trim().toLowerCase();
  if (!q) {
    matchedDevice.value = null;
    matchedDevices.value = [];
    return;
  }
  const matches = gear.value.filter((d) => {
    const a = d.attributes || {};
    const identifiers = [
      d.stockwire_device_id,
      a.stockwire_asset_code,
      a.stockwire_asset_tag,
      a.stockwire_asset_serial,
      a.stockwire_asset_barcode,
      a.stockwire_asset_qr_code,
      a.stockwire_asset_rfid,
      a.stockwire_asset_id, // legacy records only; new bindings use the top-level ID
      a.stockwire_product_id,
      d.stockwire_product_id,
    ];
    return identifiers.some((identifier) => String(identifier ?? '').trim().toLowerCase() === q);
  });
  const candidates =
    matches.length > 0
      ? matches
      : gear.value.filter((device) => device.name.toLowerCase().includes(q));
  matchedDevices.value = candidates;
  matchedDevice.value = candidates.length === 1 ? candidates[0] : null;
  // Keep the scan view underneath the inspector so closing it returns the crew member to scanning.
  if (matchedDevice.value) {
    openScannedDevice(matchedDevice.value);
  }
}

function selectScannedDevice(device) {
  matchedDevice.value = device;
  openScannedDevice(device);
}

function openScannedDevice(device) {
  selectedId.value = device.id;
  inspectId.value = device.id;
}

function scanCandidateDetails(device) {
  const attributes = device.attributes || {};
  return (
    [
      attributes.stockwire_asset_tag,
      attributes.stockwire_asset_serial,
      attributes.stockwire_asset_code,
      device.stockwire_product_name,
    ]
      .filter(Boolean)
      .join(' · ') || `${device.domain} · ${device.kind}`
  );
}
</script>
