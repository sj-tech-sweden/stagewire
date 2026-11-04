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
        <div class="row q-gutter-sm q-mb-sm items-center wrap">
          <q-btn
            v-for="kind in addKinds"
            :key="kind.domain"
            dense
            outline
            :icon="kind.icon"
            :label="t(`venues.baseRig.${kind.labelKey}`)"
            @click="addDevice(kind)"
          />
          <q-separator vertical />
          <q-btn
            dense
            :color="connectMode ? 'secondary' : 'grey'"
            :label="t('venues.baseRig.connect')"
            @click="connectMode = !connectMode"
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
          :connect-mode="connectMode"
          :show-outlets="true"
          :show-audience="true"
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

        <q-card
          v-if="venueGraph.edges.length"
          flat
          bordered
          class="q-mt-md"
        >
          <q-card-section>
            <div class="text-subtitle2 q-mb-xs">
              {{ t('venues.baseRig.deleteEdge') }}
            </div>
            <q-list
              dense
              separator
            >
              <q-item
                v-for="edge in venueGraph.edges"
                :key="edge.id"
              >
                <q-item-section>
                  {{ labelFor(edge.src_device_id) }} → {{ labelFor(edge.dst_device_id) }}
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="close"
                    @click="venueGraph.removeEdge(edge.id)"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>
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
import { useVenueGraphStore } from '@/stores/venueGraph';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';

const { t } = useI18n();
const $q = useQuasar();
const route = useRoute();
const router = useRouter();
const venueGraph = useVenueGraphStore();

const venueId = computed(() => route.params.venueId);
const venue = ref(null);
const outlets = ref([]);
const zoom = ref(0.5);
const connectMode = ref(false);

const frame = computed(() => (venue.value ? frameFromVenue(venue.value) : null));

// The device kinds the rig editor can seed a venue with. Positions are relative to the stage.
const addKinds = [
  { domain: 'audio', kind: 'speaker', labelKey: 'audio', icon: 'volume_up' },
  { domain: 'lighting', kind: 'fixture', labelKey: 'lighting', icon: 'lightbulb' },
  { domain: 'video', kind: 'source', labelKey: 'video', icon: 'videocam' },
  { domain: 'rigging', kind: 'rigging_point', labelKey: 'rigging', icon: 'anchor' },
  { domain: 'power', kind: 'power_node', labelKey: 'power', icon: 'power' },
];

async function load() {
  const [venueRes, outletRes] = await Promise.all([
    api.get(`/venues/${venueId.value}`),
    api.get(`/venues/${venueId.value}/power-outlets`),
  ]);
  venue.value = venueRes.data;
  outlets.value = (outletRes.data || []).filter((o) => o.x_cm != null && o.y_cm != null);
  await venueGraph.fetchGraph(venueId.value);
}

function addDevice(kind) {
  const centre = frame.value ? stageCentre(frame.value) : { x: 0, y: 0 };
  venueGraph.addDevice({
    domain: kind.domain,
    kind: kind.kind,
    name: t(`venues.baseRig.${kind.labelKey}`),
    x: centre.x + Math.round((Math.random() - 0.5) * 80),
    y: centre.y + Math.round((Math.random() - 0.5) * 80),
  });
  connectMode.value = false;
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
function labelFor(id) {
  const device = venueGraph.devices.find((d) => d.id === id);
  return device ? device.name : id;
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
