<template>
  <q-page
    padding
    class="column"
  >
    <div class="row items-center q-col-gutter-sm q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('venues.baseRig.back')"
        @click="goBack"
      />
      <div class="col">
        <div class="text-h6">
          {{ venue ? venue.name : '' }}
        </div>
        <div class="text-caption">
          {{ t('venues.baseRig.title') }}
        </div>
      </div>
      <HistoryControls
        kind="venue"
        :scope-id="venueId"
        @restored="load"
      />
      <q-btn
        flat
        no-caps
        icon="auto_awesome_motion"
        :label="t('workspace.library')"
        @click="libraryOpen = true"
      />
      <q-btn
        flat
        no-caps
        icon="summarize"
        :label="t('reports.openReports')"
        @click="reportsOpen = true"
      />
      <q-btn
        v-if="netbox.isEnabled"
        flat
        no-caps
        icon="sync"
        :label="t('netbox.syncVenue')"
        data-testid="venue-sync-netbox"
        :loading="pushingNetbox"
        @click="syncNetbox"
      />
    </div>

    <div
      v-if="netboxMessage"
      class="q-mb-md"
      :class="netboxError ? 'text-negative' : 'text-positive'"
    >
      {{ netboxMessage }}
    </div>

    <!-- The venue Standard Base Rig mirrors the job workspace's discipline tabs so a venue is set up
         exactly like a job: canvas (stage plot + cable raceways), channel lists, lights, video, power
         (rigging), devices and the flat table. The store scope is owned by this page (set in setup),
         so every editor drives the venue's graph. -->
    <q-tabs
      :model-value="graph.mode"
      dense
      no-caps
      align="left"
      mobile-arrows
      active-color="primary"
      indicator-color="primary"
      class="q-mb-md workspace-tabs"
      @update:model-value="graph.setMode"
    >
      <q-tab
        name="canvas"
        icon="map"
        :label="t('venues.baseRig.stage')"
      />
      <q-tab
        name="lists"
        icon="queue_music"
        :label="t('channels.lists')"
      />
      <q-tab
        name="lights"
        icon="lightbulb"
        :label="t('workspace.modeLights')"
      />
      <q-tab
        name="video"
        icon="videocam"
        :label="t('workspace.modeVideo')"
      />
      <q-tab
        name="power"
        icon="bolt"
        :label="t('workspace.modePower')"
      />
      <q-tab
        name="devices"
        icon="developer_board"
        :label="t('workspace.modeDevices')"
      />
      <q-tab
        name="list"
        icon="table_rows"
        :label="t('workspace.modeList')"
      />
    </q-tabs>

    <div
      v-if="graph.mode === 'canvas'"
      class="row q-col-gutter-md col-grow"
      :class="$q.screen.lt.sm ? 'column' : ''"
    >
      <div
        class="col-12"
        :class="$q.screen.lt.sm ? '' : 'col-9'"
      >
        <div
          class="row q-gutter-sm q-mb-sm items-center wrap canvas-toolbar"
        >
          <q-btn
            dense
            no-caps
            icon="cable"
            :color="connectMode ? 'primary' : undefined"
            :label="t('workspace.connectTool')"
            @click="connectMode = !connectMode"
          />
          <q-btn
            dense
            icon="remove"
            aria-label="zoom out"
            @click="zoomOut"
          />
          <q-btn
            dense
            icon="add"
            aria-label="zoom in"
            @click="zoomIn"
          />
          <q-btn
            dense
            icon="fit_screen"
            aria-label="fit"
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
                />
              </div>
            </q-menu>
          </q-btn>
          <q-separator
            vertical
            class="q-mx-xs"
          />
          <q-btn-dropdown
            dense
            no-caps
            icon="speaker"
            :label="t('workspace.addGearElement')"
          >
            <q-list>
              <template
                v-for="group in gearGroups"
                :key="group"
              >
                <q-item-label header>
                  {{ t(`workspace.gearGroup.${group}`) }}
                </q-item-label>
                <q-item
                  v-for="gear in GEAR_ELEMENTS.filter((g) => g.group === group)"
                  :key="gear.type"
                  v-close-popup
                  clickable
                  :data-testid="`add-gear-${gear.type}`"
                  @click="venueAddCatalog(gear)"
                >
                  <q-item-section avatar>
                    <q-icon
                      :name="gear.icon"
                      :style="{ color: gear.color }"
                    />
                  </q-item-section>
                  <q-item-section>{{ objectLabel(gear) }}</q-item-section>
                </q-item>
              </template>
            </q-list>
          </q-btn-dropdown>
          <q-btn-dropdown
            dense
            no-caps
            icon="category"
            :label="t('workspace.addObject')"
          >
            <q-list>
              <q-item
                v-for="object in OBJECT_TYPES"
                :key="object.type"
                v-close-popup
                clickable
                :data-testid="`add-object-${object.type}`"
                @click="venueAddCatalog(object)"
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
          <q-separator
            vertical
            class="q-mx-xs"
          />
          <q-btn
            dense
            no-caps
            icon="power"
            :color="showOutlets ? 'primary' : undefined"
            :label="t('workspace.layerOutlets')"
            @click="showOutlets = !showOutlets"
          />
          <q-btn
            dense
            no-caps
            icon="groups"
            :color="showAudience ? 'primary' : undefined"
            :label="t('workspace.layerAudience')"
            @click="showAudience = !showAudience"
          />
          <q-btn
            dense
            no-caps
            icon="cable"
            :color="showCables ? 'primary' : undefined"
            :label="t('workspace.layerCables')"
            @click="showCables = !showCables"
          />
          <q-btn
            dense
            no-caps
            icon="timeline"
            :color="drawingWay ? 'primary' : undefined"
            :label="t('cables.drawWay')"
            @click="drawingWay ? cancelDrawWay() : startDrawWay()"
          />
          <q-btn
            dense
            no-caps
            icon="edit"
            :color="audienceDrawing ? 'primary' : undefined"
            :label="t('stagePlot.audienceDraw')"
            @click="startAudience"
          />
          <template v-if="audienceDrawing">
            <q-btn
              dense
              no-caps
              icon="check"
              color="positive"
              :label="t('stagePlot.audienceFinish')"
              :disable="audienceDraft.length < 3"
              @click="finishAudience"
            />
            <q-btn
              dense
              no-caps
              icon="clear"
              color="negative"
              :label="t('stagePlot.audienceClear')"
              @click="clearAudienceDraft"
            />
          </template>
          <q-btn
            dense
            outline
            color="negative"
            icon="delete"
            :disable="!graph.selectedDeviceId"
            :label="t('venues.baseRig.deleteSelected')"
            @click="deleteSelected"
          />
        </div>

        <WorkspaceCanvas
          :frame="frame"
          :devices="graph.devices"
          :edges="graph.edges"
          :outlets="outlets"
          :selected-id="graph.selectedDeviceId"
          :zoom="zoom"
          :device-scale="deviceScale"
          :connect-mode="connectMode"
          :show-outlets="showOutlets"
          :show-audience="showAudience"
          :cables="showCables ? cableRows : []"
          :cableways="cablePlan.cableways"
          :draw-points="drawPoints"
          :drawing="drawingWay"
          :rerouting="!!rerouteKey"
          :reroute-waypoints="rerouteWaypoints"
          :active-cable-key="rerouteKey"
          :audience-draft="audienceDraft"
          :audience-drawing="audienceDrawing"
          @select="onSelect"
          @move="onMove"
          @connect="onConnect"
          @audience-point="onAudiencePoint"
          @draw-point="(p) => drawPoints.push(p)"
          @reroute-point="addWaypoint"
        />
        <div
          v-if="connectMode"
          class="text-caption q-mt-xs text-grey-7"
        >
          {{ t('venues.baseRig.connecting') }}
        </div>
        <div
          v-else-if="drawingWay"
          class="text-caption q-mt-xs text-grey-7"
        >
          {{ t('cables.drawHint') }}
        </div>
        <div
          v-else-if="audienceDrawing"
          class="text-caption q-mt-xs text-grey-7"
        >
          {{ t('stagePlot.audienceHint') }}
        </div>
      </div>

      <div
        class="col-12"
        :class="$q.screen.lt.sm ? '' : 'col-3'"
      >
        <q-card
          flat
          bordered
        >
          <q-card-section v-if="graph.selectedDevice">
            <div class="text-subtitle2">
              {{ t('venues.baseRig.name') }}
            </div>
            <q-input
              dense
              :model-value="graph.selectedDevice.name"
              @update:model-value="(v) => graph.updateDevice(venueId, graph.selectedDeviceId, { name: v })"
            />
            <div class="text-caption q-mt-sm text-grey-7">
              {{ graph.selectedDevice.domain }} / {{ graph.selectedDevice.kind || '—' }}
            </div>
            <div class="row q-gutter-xs q-mt-sm">
              <q-input
                dense
                type="number"
                class="col"
                :label="t('venues.geometry.xCm')"
                :model-value="graph.selectedDevice.attributes?.width_cm"
                @update:model-value="(v) => updateDeviceSize('width_cm', v)"
              />
              <q-input
                dense
                type="number"
                class="col"
                :label="t('venues.geometry.yCm')"
                :model-value="graph.selectedDevice.attributes?.height_cm"
                @update:model-value="(v) => updateDeviceSize('height_cm', v)"
              />
            </div>
            <q-input
              dense
              type="number"
              class="q-mt-sm"
              :label="t('workspace.powerWatts')"
              :model-value="graph.selectedDevice.attributes?.power_w"
              @update:model-value="(v) => updateDeviceAttr('power_w', v === '' ? null : Number(v))"
            />
            <q-select
              dense
              clearable
              emit-value
              map-options
              class="q-mt-sm"
              :label="t('workspace.devicePowerConnection')"
              :options="powerTargets"
              :model-value="powerTarget"
              @update:model-value="setPowerTarget"
            />
            <!-- NetBox panel: status chip, link-out, conflict banner and the VLAN →
                 subnet → IP picker, mirroring the job inspector's NetBox block. A venue
                 base-rig device is edited through graph.updateDevice, so persistence goes
                 through netboxSave rather than the job inspector's save(). -->
            <template v-if="netbox.isEnabled">
              <q-separator class="q-my-sm" />
              <div class="text-caption text-grey-7 q-mb-xs">
                {{ t('workspace.network.netboxTitle') }}
              </div>
              <div class="row q-gutter-xs items-center q-mb-xs">
                <q-chip
                  v-if="selectedDeviceAttrs.netbox_sync_status"
                  :color="netboxStatusColor"
                  text-color="white"
                  dense
                >
                  {{ t(`workspace.network.netboxStatus.${selectedDeviceAttrs.netbox_sync_status}`) }}
                </q-chip>
                <q-btn
                  v-if="selectedDeviceAttrs.netbox_url"
                  dense
                  flat
                  no-caps
                  icon="open_in_new"
                  color="primary"
                  :label="t('workspace.network.netboxOpen')"
                  :href="selectedDeviceAttrs.netbox_url"
                  target="_blank"
                  rel="noopener"
                />
              </div>
              <q-banner
                v-if="selectedDeviceAttrs.netbox_sync_status === 'conflict'"
                dense
                rounded
                class="bg-negative text-white q-mb-sm"
              >
                <template #avatar>
                  <q-icon name="warning" />
                </template>
                {{ t('workspace.network.netboxConflict') }}
              </q-banner>
              <q-select
                v-if="!readonly"
                :model-value="selectedVlanId"
                dense
                outlined
                emit-value
                map-options
                clearable
                :options="netboxVlanOptions"
                :label="t('workspace.network.netboxVlan')"
                data-testid="network-netbox-vlan"
                :loading="netboxVlansLoading"
                @focus="loadNetboxVlans"
                @update:model-value="onNetboxVlanChange"
              />
              <q-select
                v-if="!readonly && selectedVlanId"
                :model-value="selectedPrefixId"
                dense
                outlined
                emit-value
                map-options
                clearable
                :options="netboxPrefixOptions"
                :label="t('workspace.network.netboxSubnet')"
                data-testid="network-netbox-subnet"
                :loading="netboxPrefixesLoading"
                @update:model-value="onNetboxPrefixChange"
              />
              <q-input
                v-if="!readonly"
                :model-value="selectedDeviceAttrs.network_prefix || ''"
                dense
                outlined
                placeholder="10.0.0.0/24"
                :label="t('workspace.network.netboxPrefix')"
                data-testid="network-netbox-prefix"
                @change="(v) => netboxSave({ network_prefix: v || null })"
              />
              <div
                v-if="!readonly"
                class="row q-gutter-xs items-center"
              >
                <q-btn
                  dense
                  outline
                  no-caps
                  icon="search"
                  :label="t('workspace.network.netboxQuery')"
                  :loading="netboxQuerying"
                  @click="queryNetboxIps()"
                />
                <q-select
                  v-if="netbox.availableIps.length"
                  v-model="netboxSelectedIp"
                  class="col"
                  dense
                  outlined
                  emit-value
                  map-options
                  :options="netboxIpOptions"
                  :label="t('workspace.network.netboxAvailable')"
                  data-testid="network-netbox-ip"
                />
                <q-btn
                  dense
                  flat
                  no-caps
                  color="primary"
                  icon="check"
                  :label="t('workspace.network.netboxAssign')"
                  :disable="!netboxSelectedIp"
                  :loading="netboxAssigning"
                  @click="assignNetboxIp"
                />
              </div>
            </template>
            <q-btn
              class="q-mt-sm"
              dense
              flat
              color="negative"
              icon="delete"
              :label="t('venues.baseRig.deleteSelected')"
              @click="deleteSelected"
            />
          </q-card-section>
          <q-card-section v-else>
            <div class="text-grey-7">
              {{ t('venues.baseRig.noDevices') }}
            </div>
          </q-card-section>
        </q-card>

        <MultiDomainPatchDrawer
          class="q-mt-md"
          :graph="graph"
          :update-edge="(id, changes) => graph.updateEdge(venueId, id, changes)"
          :delete-edge="(id) => graph.deleteEdge(venueId, id)"
        />

        <RiggingEditor
          class="q-mt-md"
          :venue-id="venueId"
          @changed="reloadOutlets"
        />

        <CableRoutingPanel
          class="q-mt-md"
          :rows="cableRows"
          :settings="cablePlan.settings"
          :cableways="cablePlan.cableways"
          :drawing="drawingWay"
          :draw-points="drawPoints"
          :reroute-key="rerouteKey"
          @toggle-hidden="toggleCableHidden"
          @reroute="startReroute"
          @reset-route="resetRoute"
          @settings="saveCableSettings"
          @draw-start="startDrawWay"
          @draw-finish="finishDrawWay"
          @draw-undo="drawPoints.pop()"
          @draw-cancel="cancelDrawWay"
          @delete-way="removeCableway"
        />
      </div>
    </div>

    <ChannelListEditor
      v-else-if="graph.mode === 'lists'"
      :venue-id="venueId"
      class="col-grow"
    />
    <LightsEditor
      v-else-if="graph.mode === 'lights'"
      :venue-id="venueId"
    />
    <VideoEditor
      v-else-if="graph.mode === 'video'"
      :venue-id="venueId"
    />
    <RiggingEditor
      v-else-if="graph.mode === 'power'"
      :venue-id="venueId"
      @changed="reloadOutlets"
    />
    <DeviceEditor
      v-else-if="graph.mode === 'devices'"
      :venue-id="venueId"
    />
    <WorkspaceTable
      v-else
      :venue-id="venueId"
      :devices="listDevices"
      :selected-id="graph.selectedDeviceId"
      @select="onSelect"
      @request-booking="requestBooking"
    />

    <FixtureLibraryDialog
      v-model="libraryOpen"
      :venue-id="venueId"
    />
    <ReportGenerationDialog
      v-model="reportsOpen"
      :venue-id="venueId"
    />
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import { apiErrorText } from '@/utils/errors';
import { frameFromVenue, stageCentre } from '@/utils/plotFrame';
import { GEAR_ELEMENTS, OBJECT_TYPES } from '@/utils/plotObjects';
import { buildCableRowsFromGraph } from '@/utils/graphLegacy';
import { emptyCablePlan } from '@/utils/cables';
import { useGraphStore } from '@/stores/graph';
import { useHistoryStore } from '@/stores/history';
import { useNetboxStore } from '@/stores/netbox';
import { useVenueSocket } from '@/composables/useVenueSocket';
import HistoryControls from '@/components/HistoryControls.vue';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import ChannelListEditor from '@/components/ChannelListEditor.vue';
import MultiDomainPatchDrawer from '@/components/MultiDomainPatchDrawer.vue';
import RiggingEditor from '@/components/RiggingEditor.vue';
import FixtureLibraryDialog from '@/components/FixtureLibraryDialog.vue';
import ReportGenerationDialog from '@/components/ReportGenerationDialog.vue';
import LightsEditor from '@/components/LightsEditor.vue';
import VideoEditor from '@/components/VideoEditor.vue';
import DeviceEditor from '@/components/DeviceEditor.vue';
import WorkspaceTable from '@/components/WorkspaceTable.vue';
import CableRoutingPanel from '@/components/CableRoutingPanel.vue';
const $q = useQuasar();
const route = useRoute();
const router = useRouter();
const { t } = useI18n();
// The venue Standard Base Rig reuses the job graph editing store, scoped to the venue: the same
// components (canvas, editors, power panel, patch drawer, cable routing) serve both, so a venue gets
// the identical rigging/power/lighting/video treatment a job does. Edits commit immediately through
// the incremental graph routes — there is no separate "save" step.
const graph = useGraphStore();
const history = useHistoryStore();
// NetBox integration config (gates the "Sync base rig to NetBox" button and tells
// us whether the venue base rig can be mirrored into NetBox IPAM/DCIM).
const netbox = useNetboxStore();
const pushingNetbox = ref(false);
const netboxMessage = ref('');
const netboxError = ref(false);

// Mirror the venue's Standard Base Rig into NetBox, the venue counterpart to a
// job's "Sync to NetBox". The button is hidden unless NetBox is configured.
async function syncNetbox() {
  pushingNetbox.value = true;
  netboxMessage.value = '';
  netboxError.value = false;
  try {
    const { data } = await netbox.syncVenue(venueId.value);
    if (data?.ok) {
      netboxMessage.value = t('netbox.syncOk', {
        created: data.devices_created,
        updated: data.devices_updated,
      });
    } else {
      netboxError.value = true;
      netboxMessage.value = data?.message || t('netbox.syncFailed');
    }
  } catch (err) {
    netboxError.value = true;
    netboxMessage.value = apiErrorText(err) || t('netbox.syncFailed');
  } finally {
    pushingNetbox.value = false;
  }
}

// --- Per-device NetBox panel (venue parity with the job inspector) ----------------------------
// Mirrors DeviceInspector's NetBox block: status chip, link-out, conflict banner and the
// VLAN → subnet → IP picker. A venue base-rig device is edited through graph.updateDevice
// (scope-aware) instead of the job inspector's save(), so the persistence call differs only
// in which store action commits the attribute patch.
const readonly = false;
const selectedDeviceAttrs = computed(() => graph.selectedDevice?.attributes || {});
const netboxQuerying = ref(false);
const netboxAssigning = ref(false);
const netboxSelectedIp = ref(null);
const selectedVlanId = ref(null);
const selectedPrefixId = ref(null);
const netboxVlansLoading = ref(false);
const netboxPrefixesLoading = ref(false);

// A venue rig is edited by admins, so the panel is always interactive here (no read-only mode).
const netboxStatusColor = computed(() => {
  const s = selectedDeviceAttrs.value.netbox_sync_status;
  return { ok: 'positive', conflict: 'negative', error: 'negative', pending: 'warning' }[s] || 'grey';
});

const netboxIpOptions = computed(() =>
  (netbox.availableIps || []).map((ip) => ({ label: ip.address, value: ip.address })),
);
const netboxVlanOptions = computed(() =>
  (netbox.vlans || []).map((v) => ({
    label: v.vid != null ? `${v.vid} — ${v.name || v.slug}` : (v.name || v.slug),
    value: v.id,
  })),
);
const netboxPrefixOptions = computed(() =>
  (netbox.prefixes || []).map((p) => ({
    label: p.prefix + (p.description ? ` (${p.description})` : ''),
    value: p.id,
    prefix: p.prefix,
  })),
);

async function netboxSave(attrPatch) {
  if (!graph.selectedDeviceId) return;
  await graph.updateDevice(venueId.value, graph.selectedDeviceId, {
    attributes: { ...(graph.selectedDevice?.attributes || {}), ...attrPatch },
  });
}

async function loadNetboxVlans() {
  if (netbox.vlans.length) return;
  netboxVlansLoading.value = true;
  try {
    await netbox.loadVlans();
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  } finally {
    netboxVlansLoading.value = false;
  }
}

async function onNetboxVlanChange(vlanId) {
  selectedVlanId.value = vlanId;
  selectedPrefixId.value = null;
  netbox.prefixes = [];
  if (!vlanId) return;
  netboxPrefixesLoading.value = true;
  try {
    await netbox.loadPrefixes(vlanId);
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  } finally {
    netboxPrefixesLoading.value = false;
  }
}

async function onNetboxPrefixChange(prefixId) {
  selectedPrefixId.value = prefixId;
  const opt = netboxPrefixOptions.value.find((o) => o.value === prefixId);
  if (!opt) return;
  // Persist the chosen subnet as the device's NetBox prefix, then draw available IPs from it.
  await netboxSave({ network_prefix: opt.prefix });
  await queryNetboxIps(opt.prefix);
}

async function queryNetboxIps(prefixOverride) {
  const prefix = prefixOverride || selectedDeviceAttrs.value.network_prefix;
  if (!prefix) {
    $q.notify({ type: 'warning', message: t('workspace.network.netboxNeedsSubnet') });
    return;
  }
  netboxQuerying.value = true;
  try {
    await netbox.queryIps(prefix);
    netboxSelectedIp.value = null;
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  } finally {
    netboxQuerying.value = false;
  }
}

async function assignNetboxIp() {
  if (!netboxSelectedIp.value || !graph.selectedDevice) return;
  netboxAssigning.value = true;
  try {
    const res = await netbox.assignIp({
      device_id: graph.selectedDevice.id,
      prefix: selectedDeviceAttrs.value.network_prefix || undefined,
      address: netboxSelectedIp.value,
    });
    if (res?.ok) {
      $q.notify({
        type: 'positive',
        message: t('workspace.network.netboxAssigned', { ip: res.ip }),
      });
    } else {
      $q.notify({ type: 'warning', message: res?.message || 'NetBox assignment failed' });
    }
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  } finally {
    netboxAssigning.value = false;
  }
}

const venueId = computed(() => route.params.venueId);
// Realtime NetBox events (IP assigned / conflict resolved) for this venue's base rig. Declared here
// (after `venueId`) because useVenueSocket reads venueId.value during setup and `const` is in the
// temporal dead zone until this line — calling it earlier would throw and abort the whole component.
// connect() is invoked further down once the venue graph has loaded.
const venueSocket = useVenueSocket(venueId.value, (event) => {
  if (event.type === 'history.restore') load(); // an undo / restore changed many rows: reload
  else graph.applyRealtimeEvent(event);
  // other people's writes change what can be undone: keep the undo / redo state current
  if (/^(graph\.|venue\.|history\.)/.test(event.type || '')) history.scheduleRefresh(800);
});
// Scope the graph store to this venue synchronously, in setup and therefore before child components
// mount. Child components (e.g. RiggingEditor) fire venue-scoped API calls on mount; without this the
// store's default job/null scope would send those requests to /jobs/null/... and fail UUID validation.
// This mirrors how the job workspace owns the store scope while it is mounted.
graph.setScope('venue', venueId.value);
const libraryOpen = ref(false);
const reportsOpen = ref(false);
const venue = ref(null);
const outlets = ref([]);
const powerOutlets = ref([]);
const powerGroups = ref([]);
const zoom = ref(0.5);
const deviceScale = ref(1);
const connectMode = ref(false);
const showOutlets = ref(true);
const showAudience = ref(true);
const showCables = ref(false);
// Drawing an audience area: clicks on the canvas (in venue cm) accumulate in audienceDraft until
// the area is finished and saved onto the venue's audience_polygon.
const audienceDrawing = ref(false);
const audienceDraft = ref([]);

// --- Cable raceways & routing ----------------------------------------------------------------
// Cableways and routing settings live on the venue (cable_plan), the same shape a job uses. A job
// clones these as its starting point and adds its own runs, so the venue owns the fixed infrastructure
// (trays, conduits). Cables are derived from the signal chains and routed along the cableways.
const drawingWay = ref(false);
const drawPoints = ref([]);
const rerouteKey = ref(null);
const cablePlan = computed(() => emptyCablePlan(venue.value?.cable_plan));
const cableRows = computed(() => {
  if (!graph.devices.length) return [];
  const f = frame.value;
  return buildCableRowsFromGraph({
    devices: graph.devices,
    edges: graph.edges,
    plan: venue.value?.cable_plan,
    audience: f.audience,
    stageOffset: [f.stageX, f.stageY],
  });
});
const rerouteWaypoints = computed(() => cablePlan.value.routes[rerouteKey.value]?.waypoints || []);
async function savePlan(next) {
  try {
    const { data } = await api.patch(`/venues/${venueId.value}`, { cable_plan: next });
    venue.value = { ...venue.value, cable_plan: data.cable_plan };
  } catch (err) {
    $q.notify({ type: 'negative', message: `${t('cables.saveFailed')}: ${apiErrorText(err)}` });
  }
}
function startDrawWay() {
  rerouteKey.value = null;
  drawPoints.value = [];
  drawingWay.value = true;
}
function cancelDrawWay() {
  drawingWay.value = false;
  drawPoints.value = [];
}
function finishDrawWay() {
  if (drawPoints.value.length < 2) return;
  const plan = cablePlan.value;
  savePlan({ ...plan, cableways: [...plan.cableways, { id: crypto.randomUUID(), points: drawPoints.value }] });
  cancelDrawWay();
}
function removeCableway(id) {
  const plan = cablePlan.value;
  savePlan({ ...plan, cableways: plan.cableways.filter((w) => w.id !== id) });
}
// A cable's route is stored per cable key in cable_plan.routes: { mode: 'auto'|'manual', waypoints,
// hidden }. The key is derived from the chain (utils/cables.js), so it survives a reload.
function updateRoute(key, patch) {
  const plan = cablePlan.value;
  const current = plan.routes[key] || { mode: 'auto', waypoints: [], hidden: false };
  savePlan({ ...plan, routes: { ...plan.routes, [key]: { ...current, ...patch } } });
}
const toggleCableHidden = (row) => updateRoute(row.key, { hidden: !row.hidden });
function startReroute(row) {
  cancelDrawWay();
  rerouteKey.value = row.key;
  updateRoute(row.key, { mode: 'manual', waypoints: row.requestedMode === 'manual' ? row.waypoints : [] });
}
function resetRoute(row) {
  updateRoute(row.key, { mode: 'auto', waypoints: [] });
  if (rerouteKey.value === row.key) rerouteKey.value = null;
}
function addWaypoint(cm) {
  if (!rerouteKey.value) return;
  updateRoute(rerouteKey.value, { mode: 'manual', waypoints: [...rerouteWaypoints.value, cm] });
}
const saveCableSettings = (patch) => {
  const plan = cablePlan.value;
  savePlan({ ...plan, settings: { ...plan.settings, ...patch } });
};

const frame = computed(() => (venue.value ? frameFromVenue(venue.value) : null));

const gearGroups = ['audio', 'video', 'lighting'];

// The signal a new canvas connection carries, derived from the source device's domain (matches the
// job workspace so power/audio/lighting/video links are typed the same way).
const DOMAIN_SIGNAL = { audio: 'audio', lighting: 'dmx', video: 'video', power: 'power' };

const listDevices = computed(() => graph.devices);

const objectLabel = (object) =>
  object.labelKey ? t(object.labelKey, object.label || object.type) : object.label;

async function load() {
  const [venueRes, outletRes, powerRes] = await Promise.all([
    api.get(`/venues/${venueId.value}`),
    api.get(`/venues/${venueId.value}/power-outlets`),
    api.get(`/venues/${venueId.value}/power-groups`),
  ]);
  venue.value = venueRes.data;
  outlets.value = (outletRes.data || []).filter((o) => o.x_cm != null && o.y_cm != null);
  powerOutlets.value = outletRes.data || [];
  powerGroups.value = powerRes.data || [];
  // Scope the graph store to this venue so every incremental graph call (devices, edges, rigging,
  // power) routes to /venues/{venueId}/graph and edits commit straight to the venue's rig.
  await graph.fetchGraph(venueId.value, 'venue');
  // Refresh NetBox integration state so the "Sync base rig to NetBox" button shows
  // only when the integration is configured (mirrors how job views gate it).
  try {
    await netbox.loadIntegration();
  } catch {
    /* netbox state stays default (disabled) if the request fails */
  }
  // Open the venue realtime room so NetBox IP-assignment / conflict events update the
  // selected device live, matching the job workspace's behaviour.
  venueSocket.connect();
}

// The power panel mutates the venue's circuits/outlets; refresh the canvas layer and the
// inlet/outlet assignment pickers to match.
async function reloadOutlets() {
  try {
    const [{ data: outletData }, { data: groupData }] = await Promise.all([
      api.get(`/venues/${venueId.value}/power-outlets`),
      api.get(`/venues/${venueId.value}/power-groups`),
    ]);
    outlets.value = (outletData || []).filter((o) => o.x_cm != null && o.y_cm != null);
    powerOutlets.value = outletData || [];
    powerGroups.value = groupData || [];
  } catch {
    /* leave the previous outlets in place */
  }
}

// Add a real piece of equipment from the shared catalog rather than a generic box. The catalog
// carries the domain, an icon/colour and true dimensions, so the rig shows correctly-sized,
// colour-coded gear just like the job workspace plot.
async function venueAddCatalog(item) {
  const centre = frame.value ? stageCentre(frame.value) : { x: 0, y: 0 };
  await graph.createDevices(venueId.value, [
    {
      domain: item.group || 'other',
      kind: item.type,
      name: objectLabel(item),
      canvas_x_cm: Math.round(centre.x + (Math.random() - 0.5) * 80),
      canvas_y_cm: Math.round(centre.y + (Math.random() - 0.5) * 80),
      attributes: {
        element_type: item.type,
        width_cm: item.w,
        height_cm: item.h,
      },
    },
  ]);
  connectMode.value = false;
}

function zoomIn() {
  zoom.value = Math.min(2, zoom.value * 1.2);
}
function zoomOut() {
  zoom.value = Math.max(0.05, zoom.value / 1.2);
}
function fitCanvas() {
  if (!frame.value) return;
  zoom.value = Math.min(2, Math.max(0.05, 700 / Math.max(1, frame.value.width)));
}

// Per-device dimensions can be overridden precisely (e.g. an unusual box) without losing the
// catalog colour/type carried in the rest of the attributes object.
function updateDeviceSize(key, value) {
  if (!graph.selectedDeviceId) return;
  graph.updateDevice(venueId.value, graph.selectedDeviceId, {
    attributes: { [key]: Number(value) || 0 },
  });
}

// Assign a base-rig device the power rating (watts) it draws, into the device's attributes so it
// drives the venue's server-side over-limit check just like a job device does.
function updateDeviceAttr(key, value) {
  if (!graph.selectedDeviceId) return;
  graph.updateDevice(venueId.value, graph.selectedDeviceId, {
    attributes: { [key]: value },
  });
}

// The outlet/group a device is plugged into. Stored in attributes so the device-driven load
// (power_w) is attributed to the right supply element on the server.
const powerTarget = computed(() => {
  const device = graph.selectedDevice;
  if (!device) return null;
  return (
    device.attributes?.venue_outlet_id ||
    device.attributes?.venue_group_id ||
    null
  );
});

// Outlets and groups as a single picker so a device can hang from either a socket or a panel.
const powerTargets = computed(() => {
  const outletOpts = powerOutlets.value.map((o) => ({
    value: o.id,
    label: `${t('workspace.venueOutlet')}: ${o.name || o.connector || o.id.slice(0, 8)}`,
    type: 'outlet',
  }));
  const groupOpts = powerGroups.value.map((g) => ({
    value: g.id,
    label: `${t('workspace.venueGroup')}: ${g.name || g.id.slice(0, 8)}${g.kind === 'incoming' ? ' ⚡' : ''}`,
    type: 'group',
  }));
  return [...outletOpts, ...groupOpts];
});

// Setting the inlet clears the other side: a device is on an outlet OR a group, never both.
function setPowerTarget(targetId) {
  if (!graph.selectedDeviceId) return;
  const attributes = { ...(graph.selectedDevice.attributes || {}) };
  delete attributes.venue_outlet_id;
  delete attributes.venue_group_id;
  if (targetId) {
    const target = powerTargets.value.find((t) => t.value === targetId);
    if (target?.type === 'group') {
      attributes.venue_group_id = targetId;
    } else {
      attributes.venue_outlet_id = targetId;
    }
  }
  graph.updateDevice(venueId.value, graph.selectedDeviceId, { attributes });
}

function onSelect(id) {
  graph.selectedDeviceId = id;
}
function onMove({ id, x, y }) {
  graph.updateDevice(venueId.value, id, { canvas_x_cm: x, canvas_y_cm: y });
}
function onConnect({ srcId, dstId }) {
  if (srcId === dstId) return;
  const src = graph.devices.find((d) => d.id === srcId);
  graph.createEdge(venueId.value, {
    signal: DOMAIN_SIGNAL[src?.domain] || 'audio',
    src_device_id: srcId,
    src_port: '',
    dst_device_id: dstId,
    dst_port: '',
    channels: 1,
    phase: null,
  });
  connectMode.value = false;
}

// --- Audience area ---------------------------------------------------------------------------
function startAudience() {
  audienceDrawing.value = true;
  connectMode.value = false;
  drawingWay.value = false;
  audienceDraft.value = [];
}
function onAudiencePoint(point) {
  audienceDraft.value.push(point);
}
// Persist the drawn outline as the venue's audience polygon (venue coordinates, no stage offset).
async function saveAudience(polygon) {
  const { data } = await api.patch(`/venues/${venueId.value}`, { audience_polygon: polygon });
  venue.value = { ...venue.value, audience_polygon: data.audience_polygon ?? polygon };
}
async function finishAudience() {
  if (audienceDraft.value.length < 3) return;
  await saveAudience(audienceDraft.value);
  audienceDrawing.value = false;
  audienceDraft.value = [];
}
async function clearAudienceDraft() {
  audienceDraft.value = [];
  if (venue.value?.audience_polygon?.length) {
    await saveAudience([]);
  }
  audienceDrawing.value = false;
}
function deleteSelected() {
  if (graph.selectedDeviceId) graph.deleteDevice(venueId.value, graph.selectedDeviceId);
}
// Venues have no Stockwire integration, so requesting gear from Stockwire is unavailable here.
function requestBooking() {
  $q.notify({ type: 'info', message: t('venues.baseRig.noStockwire') });
}
function goBack() {
  router.push({ path: '/venues' });
}

onMounted(load);
</script>
