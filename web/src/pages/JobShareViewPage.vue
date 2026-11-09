<template>
  <q-page class="bg-grey-10 text-white q-pa-sm">
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
            <svg
              :viewBox="mapViewBox"
              class="full-width bg-grey-11 rounded-borders"
              style="aspect-ratio: 16 / 10"
              data-testid="share-stage-map"
              @click.self="selectedId = null"
            >
              <rect
                v-for="device in placedDevices"
                :key="device.id"
                :x="mapX(device.canvas_x_cm)"
                :y="mapY(device.canvas_y_cm)"
                width="14"
                height="10"
                rx="2"
                :fill="selectedId === device.id ? '#35A853' : '#3F873F'"
                class="cursor-pointer"
                @click="selectedId = device.id"
              >
                <title>{{ device.name }}</title>
              </rect>
            </svg>

            <q-card
              v-if="selected"
              flat
              class="bg-grey-9 text-white q-mt-sm"
              data-testid="share-map-detail"
            >
              <q-card-section>
                <div class="text-subtitle2">
                  {{ selected.name }}
                </div>
                <div class="text-caption text-grey-5 text-capitalize">
                  {{ selected.domain }} · {{ selected.kind }}
                </div>
                <DeviceShareDetail
                  :device="selected"
                  class="q-mt-sm"
                />
              </q-card-section>
            </q-card>
          </div>
          <div
            v-else
            class="text-grey-5 q-pa-md text-center"
          >
            {{ t('workspace.share.noDevices') }}
          </div>
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
</template>

<script setup>
import axios from 'axios';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { getApiBaseUrl } from '@/utils/runtime-config';
import DeviceShareDetail from '@/components/DeviceShareDetail.vue';

const { t } = useI18n();
const route = useRoute();

// A separate client (no auth interceptors) so a bad/expired token shows a friendly
// message here instead of the app's global "redirect to login" 401 handler.
const shareApi = axios.create({ baseURL: `${getApiBaseUrl()}/api/v1` });

const jobId = route.params.jobId;
const token = route.query.token;

const loaded = ref(false);
const error = ref(false);
const job = ref({ title: '' });
const devices = ref([]);
const tab = ref('list');
const search = ref('');
const selectedId = ref(null);

const filteredDevices = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return devices.value;
  return devices.value.filter((d) =>
    [d.name, d.domain, d.kind].join(' ').toLowerCase().includes(q),
  );
});

const placedDevices = computed(() =>
  devices.value.filter(
    (d) => typeof d.canvas_x_cm === 'number' && typeof d.canvas_y_cm === 'number',
  ),
);

const selected = computed(() => placedDevices.value.find((d) => d.id === selectedId.value) || null);

// The map fits itself to wherever devices are placed (no stage dimensions needed).
const mapBounds = computed(() => {
  const xs = placedDevices.value.map((d) => d.canvas_x_cm);
  const ys = placedDevices.value.map((d) => d.canvas_y_cm);
  const minX = Math.min(...xs, 0);
  const minY = Math.min(...ys, 0);
  const maxX = Math.max(...xs, 100);
  const maxY = Math.max(...ys, 100);
  return { minX, minY, w: maxX - minX + 20, h: maxY - minY + 20 };
});

const mapViewBox = computed(
  () => `${mapBounds.value.minX - 10} ${mapBounds.value.minY - 10} ${mapBounds.value.w} ${mapBounds.value.h}`,
);

function mapX(cm) {
  return cm - mapBounds.value.minX - 7;
}
function mapY(cm) {
  return cm - mapBounds.value.minY - 5;
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
    loaded.value = true;
  } catch {
    error.value = true;
  }
}

load();
</script>
