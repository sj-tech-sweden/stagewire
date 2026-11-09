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
            />{{ t('workspace.share.readOnly') }}
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
              </template>

              <div class="q-pa-sm bg-grey-9">
                <DeviceShareDetail :device="device" />
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
              v-if="selected"
              class="bg-grey-9 text-white q-mt-sm rounded-borders"
              data-testid="share-map-detail"
            >
              <DeviceInspector
                readonly
                :job-id="jobId"
                :device="selected"
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

        <!-- Scan view: multi-input capture (camera QR/barcode, NFC, keyboard wedge). The
             crew view is read-only, so a scan looks up the matched device rather than editing. -->
        <q-tab-panel
          name="scan"
          class="q-pa-sm"
        >
          <ScanCapture
            :active="tab === 'scan'"
            data-testid="share-scan"
            @captured="onScanned"
          />
          <q-banner
            v-if="lastScan"
            class="rounded-borders q-mt-md"
            :class="matchedDevice ? 'bg-positive text-white' : 'bg-warning text-dark'"
            data-testid="share-scan-result"
          >
            <template #avatar>
              <q-icon :name="matchedDevice ? 'check_circle' : 'warning'" />
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
              v-else
              class="text-caption"
            >
              {{ t('workspace.scan.noMatch') }}
            </div>
          </q-banner>
        </q-tab-panel>
      </q-tab-panels>
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
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { getApiBaseUrl } from '@/utils/runtime-config';
import { isGear } from '@/utils/workspace';
import { frameFromJob, fitWidthZoom } from '@/utils/plotFrame';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import DeviceInspector from '@/components/DeviceInspector.vue';
import DeviceShareDetail from '@/components/DeviceShareDetail.vue';
import ScanCapture from '@/components/ScanCapture.vue';
import { useJobSocket } from '@/composables/useJobSocket';

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
  }
}

const loaded = ref(false);
const error = ref(false);
const job = ref({ title: '' });
const devices = ref([]);
const tab = ref('list');
const search = ref('');
const selectedId = ref(null);
const lastScan = ref('');
const matchedDevice = ref(null);
const edges = ref([]);

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

const selected = computed(() => placedDevices.value.find((d) => d.id === selectedId.value) || null);

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

// The crew view is read-only: a scan looks up (rather than edits) the device whose bound
// Stockwire asset, product id, or name matches the captured code.
function onScanned(value) {
  lastScan.value = value;
  const q = String(value).toLowerCase();
  const match = gear.value.find((d) => {
    const a = d.attributes || {};
    return (
      a.stockwire_asset_code === value ||
      a.stockwire_asset_id === value ||
      d.stockwire_asset_id === value ||
      a.stockwire_product_id === value ||
      d.stockwire_product_id === value ||
      d.name.toLowerCase().includes(q)
    );
  });
  matchedDevice.value = match || null;
  // Keep the scan feedback visible (don't jump tabs); still select the device so the stage
  // map highlights it if the crew member switches to the map tab.
  if (match) {
    selectedId.value = match.id;
  }
}
</script>
