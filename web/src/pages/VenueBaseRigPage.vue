<template>
  <q-page class="column">
    <q-bar class="bg-primary text-white q-px-md">
      <q-btn
        dense
        flat
        icon="arrow_back"
        :label="t('venues.baseRig.back')"
        @click="goBack"
      />
      <div class="q-ml-md text-subtitle1">
        {{ venue ? venue.name : '' }}
        <span class="text-caption">· {{ t('venues.baseRig.title') }}</span>
      </div>
      <q-space />
      <q-badge
        v-if="venueGraph.dirty"
        color="amber"
        text-color="black"
      >
        {{ t('venues.baseRig.unsaved') }}
      </q-badge>
      <q-btn
        dense
        flat
        icon="save"
        :label="t('venues.baseRig.save')"
        :disable="!venueGraph.dirty || venueGraph.loading"
        @click="save"
      />
    </q-bar>

    <div
      class="row q-col-gutter-md q-pa-md col-grow"
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
            outline
            color="negative"
            icon="delete"
            :disable="!venueGraph.selectedId"
            :label="t('venues.baseRig.deleteSelected')"
            @click="deleteSelected"
          />
        </div>

        <WorkspaceCanvas
          :frame="frame"
          :devices="venueGraph.devices"
          :edges="venueGraph.edges"
          :outlets="outlets"
          :selected-id="venueGraph.selectedId"
          :zoom="zoom"
          :device-scale="deviceScale"
          :connect-mode="connectMode"
          :show-outlets="showOutlets"
          :show-audience="showAudience"
          @select="onSelect"
          @move="onMove"
          @connect="onConnect"
        />
        <div
          v-if="connectMode"
          class="text-caption q-mt-xs text-grey-7"
        >
          {{ t('venues.baseRig.connecting') }}
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
          <q-card-section v-if="venueGraph.selectedDevice">
            <div class="text-subtitle2">
              {{ t('venues.baseRig.name') }}
            </div>
            <q-input
              dense
              :model-value="venueGraph.selectedDevice.name"
              @update:model-value="(v) => venueGraph.updateDevice(venueGraph.selectedDevice.id, { name: v })"
            />
            <div class="text-caption q-mt-sm text-grey-7">
              {{ venueGraph.selectedDevice.domain }} / {{ venueGraph.selectedDevice.kind || '—' }}
            </div>
            <div class="row q-gutter-xs q-mt-sm">
              <q-input
                dense
                type="number"
                class="col"
                :label="t('venues.geometry.xCm')"
                :model-value="venueGraph.selectedDevice.attributes?.width_cm"
                @update:model-value="(v) => updateDeviceSize('width_cm', v)"
              />
              <q-input
                dense
                type="number"
                class="col"
                :label="t('venues.geometry.yCm')"
                :model-value="venueGraph.selectedDevice.attributes?.height_cm"
                @update:model-value="(v) => updateDeviceSize('height_cm', v)"
              />
            </div>
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
          :graph="venueGraph"
          :update-edge="(id, changes) => venueGraph.updateEdge(id, changes)"
          :delete-edge="(id) => venueGraph.removeEdge(id)"
        />

        <VenuePowerPanel
          class="q-mt-md"
          :venue-id="venueId"
          @changed="reloadOutlets"
        />
      </div>
    </div>
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
import { useVenueGraphStore } from '@/stores/venueGraph';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import MultiDomainPatchDrawer from '@/components/MultiDomainPatchDrawer.vue';
import VenuePowerPanel from '@/components/VenuePowerPanel.vue';

const { t } = useI18n();
const $q = useQuasar();
const route = useRoute();
const router = useRouter();
const venueGraph = useVenueGraphStore();

const venueId = computed(() => route.params.venueId);
const venue = ref(null);
const outlets = ref([]);
const zoom = ref(0.5);
const deviceScale = ref(1);
const connectMode = ref(false);
const showOutlets = ref(true);
const showAudience = ref(true);

const frame = computed(() => (venue.value ? frameFromVenue(venue.value) : null));

const gearGroups = ['audio', 'video', 'lighting'];

const objectLabel = (object) =>
  object.labelKey ? t(object.labelKey, object.label || object.type) : object.label;

async function load() {
  const [venueRes, outletRes] = await Promise.all([
    api.get(`/venues/${venueId.value}`),
    api.get(`/venues/${venueId.value}/power-outlets`),
  ]);
  venue.value = venueRes.data;
  outlets.value = (outletRes.data || []).filter((o) => o.x_cm != null && o.y_cm != null);
  await venueGraph.fetchGraph(venueId.value);
}

// The power panel mutates the venue's circuits/outlets; refresh the canvas layer to match.
async function reloadOutlets() {
  try {
    const { data } = await api.get(`/venues/${venueId.value}/power-outlets`);
    outlets.value = (data || []).filter((o) => o.x_cm != null && o.y_cm != null);
  } catch {
    /* leave the previous outlets in place */
  }
}

// Add a real piece of equipment from the shared catalog rather than a generic 60x30 box.
// The catalog carries the domain, an icon/colour and true dimensions, so the rig shows
// correctly-sized, colour-coded gear just like the job workspace plot.
function venueAddCatalog(item) {
  const centre = frame.value ? stageCentre(frame.value) : { x: 0, y: 0 };
  const device = venueGraph.addDevice({
    domain: item.group || 'other',
    kind: item.type,
    name: objectLabel(item),
    x: Math.round(centre.x + (Math.random() - 0.5) * 80),
    y: Math.round(centre.y + (Math.random() - 0.5) * 80),
  });
  device.attributes = {
    ...(device.attributes || {}),
    element_type: item.type,
    width_cm: item.w,
    height_cm: item.h,
  };
  venueGraph.dirty = true;
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

// Per-device dimensions can be overridden precisely (e.g. an unusual box) without
// losing the catalog colour/type carried in the rest of the attributes object.
function updateDeviceSize(key, value) {
  const device = venueGraph.selectedDevice;
  if (!device) return;
  device.attributes = { ...(device.attributes || {}), [key]: Number(value) || 0 };
  venueGraph.dirty = true;
}

function onSelect(id) {
  venueGraph.selectedId = id;
}
function onMove({ id, x, y }) {
  venueGraph.moveDevice(id, x, y);
}
function onConnect({ srcId, dstId }) {
  venueGraph.connect(srcId, dstId);
  connectMode.value = false;
}
function deleteSelected() {
  if (venueGraph.selectedId) venueGraph.removeDevice(venueGraph.selectedId);
}
async function save() {
  try {
    await venueGraph.save();
    Notify.create({ type: 'positive', message: t('venues.baseRig.saved') });
  } catch (err) {
    Notify.create({
      type: 'negative',
      message: `${t('venues.baseRig.save')}: ${err?.response?.data?.detail || err.message}`,
    });
  }
}
function goBack() {
  router.push({ path: '/venues' });
}

onMounted(load);
</script>
