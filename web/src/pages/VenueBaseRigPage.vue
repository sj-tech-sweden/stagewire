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
    </div>

    <q-tabs
      :model-value="view"
      dense
      no-caps
      align="left"
      mobile-arrows
      active-color="primary"
      indicator-color="primary"
      class="q-mb-md workspace-tabs"
      @update:model-value="view = $event"
    >
      <q-tab
        name="stage"
        icon="map"
        :label="t('venues.baseRig.stage')"
      />
      <q-tab
        name="lists"
        icon="queue_music"
        :label="t('channels.lists')"
      />
    </q-tabs>

    <div
      v-if="view === 'stage'"
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
          :audience-drawing="audienceDrawing"
          :audience-draft="audienceDraft"
          @select="onSelect"
          @move="onMove"
          @connect="onConnect"
          @audience-point="onAudiencePoint"
        />
        <div
          v-if="connectMode"
          class="text-caption q-mt-xs text-grey-7"
        >
          {{ t('venues.baseRig.connecting') }}
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

        <FixtureLibraryDialog
          v-model="libraryOpen"
          :venue-id="venueId"
        />
      </div>
    </div>

    <ChannelListEditor
      v-else-if="view === 'lists'"
      :venue-id="venueId"
      class="col-grow"
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
import { useQuasar, Notify } from 'quasar';
import { api } from '@/boot/api';
import { frameFromVenue, stageCentre } from '@/utils/plotFrame';
import { GEAR_ELEMENTS, OBJECT_TYPES } from '@/utils/plotObjects';
import { useGraphStore } from '@/stores/graph';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import ChannelListEditor from '@/components/ChannelListEditor.vue';
import MultiDomainPatchDrawer from '@/components/MultiDomainPatchDrawer.vue';
import RiggingEditor from '@/components/RiggingEditor.vue';
import FixtureLibraryDialog from '@/components/FixtureLibraryDialog.vue';
import ReportGenerationDialog from '@/components/ReportGenerationDialog.vue';
const $q = useQuasar();
const route = useRoute();
const router = useRouter();
// The venue Standard Base Rig reuses the job graph editing store, scoped to the venue: the same
// components (canvas, rigging editor, power panel, patch drawer) serve both, so a venue gets the
// identical rigging/power treatment a job does. Edits commit immediately through the incremental
// graph routes — there is no separate "save" step.
const graph = useGraphStore();

const venueId = computed(() => route.params.venueId);
// Scope the graph store to this venue synchronously, in setup and therefore before child components
// mount. Child components (e.g. RiggingEditor) fire venue-scoped API calls on mount; without this the
// store's default job/null scope would send those requests to /jobs/null/... and fail UUID validation.
// This mirrors how the job workspace owns the store scope while it is mounted.
graph.setScope('venue', venueId.value);
const view = ref('stage');
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
// Drawing an audience area: clicks on the canvas (in venue cm) accumulate in audienceDraft until
// the area is finished and saved onto the venue's audience_polygon.
const audienceDrawing = ref(false);
const audienceDraft = ref([]);

// The signal an edge gets so the patch table groups it under the right tab (as the job canvas does).
const DOMAIN_SIGNAL = { audio: 'audio', lighting: 'dmx', video: 'video', power: 'power' };

const frame = computed(() => (venue.value ? frameFromVenue(venue.value) : null));

const gearGroups = ['audio', 'video', 'lighting'];

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
function goBack() {
  router.push({ path: '/venues' });
}

onMounted(load);
</script>
