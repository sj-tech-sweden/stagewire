<template>
  <q-card
    flat
    bordered
    class="q-mb-md"
    data-testid="network-patch-panel"
  >
    <q-card-section class="q-pb-xs">
      <div class="row items-center q-gutter-sm">
        <q-icon
          name="hub"
          color="primary"
          size="sm"
        />
        <div class="text-subtitle1">
          {{ t("networkPatch.title") }}
        </div>
      </div>
      <div class="text-caption text-grey-6 q-mt-xs">
        {{ t("networkPatch.help") }}
      </div>
    </q-card-section>

    <q-card-section v-if="!netDevices.length">
      <div class="text-grey-6">
        {{ t("networkPatch.empty") }}
      </div>
    </q-card-section>

    <template v-else>
      <q-card-section class="q-gutter-sm">
        <div class="row q-col-gutter-sm">
          <div class="col-12 col-sm-5">
            <q-select
              v-model="transmitterId"
              :options="deviceOptions"
              option-value="id"
              option-label="name"
              emit-value
              map-options
              dense
              outlined
              :label="t('networkPatch.transmitter')"
              data-testid="network-transmitter"
            />
          </div>
          <div class="col-12 col-sm-5">
            <q-select
              v-model="receiverId"
              :options="deviceOptions"
              option-value="id"
              option-label="name"
              emit-value
              map-options
              dense
              outlined
              :label="t('networkPatch.receiver')"
              data-testid="network-receiver"
            />
          </div>
          <div class="col-12 col-sm-2 column justify-center">
            <q-btn
              color="primary"
              no-caps
              dense
              icon="add_link"
              :label="t('networkPatch.addToNetwork')"
              :disable="!canConnect"
              data-testid="network-add-to-network"
              @click="addToNetwork"
            />
          </div>
        </div>

        <div class="text-caption text-grey-6">
          {{ t("networkPatch.addToNetworkHint") }}
        </div>

        <div class="row q-col-gutter-sm items-end">
          <div class="col-12 col-sm-7">
            <q-input
              v-model="switchName"
              dense
              outlined
              :label="t('networkPatch.switchName')"
              data-testid="network-switch-name"
            />
          </div>
          <div class="col-12 col-sm-5">
            <q-btn
              outline
              no-caps
              dense
              icon="cable"
              :label="t('networkPatch.connectDirect')"
              :disable="!canConnect"
              data-testid="network-connect-direct"
              @click="connectDirect"
            />
          </div>
        </div>
        <div class="text-caption text-grey-6">
          {{ t("networkPatch.connectDirectHint") }}
        </div>

        <div
          v-if="!canConnect && transmitterId && receiverId && transmitterId === receiverId"
          class="text-negative text-caption"
        >
          {{ t("networkPatch.sameDevice") }}
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <div class="text-subtitle2 q-mb-sm">
          {{ t("networkPatch.existing") }}
        </div>
        <div
          v-if="!networkEdges.length"
          class="text-grey-6"
        >
          {{ t("networkPatch.noLinks") }}
        </div>
        <q-list
          v-else
          dense
          separator
        >
          <q-item
            v-for="edge in networkEdges"
            :key="edge.id"
            data-testid="network-link"
          >
            <q-item-section avatar>
              <q-icon
                name="cable"
                color="primary"
                size="sm"
              />
            </q-item-section>
            <q-item-section>
              <q-item-label>
                {{ deviceName(edge.src_device_id) }}
                <span class="text-grey-6">→</span>
                {{ deviceName(edge.dst_device_id) }}
              </q-item-label>
              <q-item-label
                caption
                lines="1"
              >
                {{ portLabel(edge) }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                round
                dense
                icon="delete"
                color="negative"
                :aria-label="t('networkPatch.deleteLink')"
                data-testid="network-link-delete"
                @click="removeLink(edge.id)"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
    </template>
  </q-card>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useGraphStore } from '@/stores/graph';
import { networkDevices, networkPorts } from '@/utils/workspace';

const props = defineProps({
  jobId: { type: String, required: true },
});

const { t } = useI18n();
const graph = useGraphStore();

// The Dante/network peer mesh: every device with a Dante/network connector, independent of any
// mixer (Phase E — not mixer-anchored).
const netDevices = computed(() => networkDevices(graph.devices));
const deviceOptions = computed(() =>
  netDevices.value.map((d) => ({ id: d.id, name: d.name || d.kind })),
);

const transmitterId = ref(null);
const receiverId = ref(null);
const switchName = ref('');

const canConnect = computed(
  () =>
    !!transmitterId.value &&
    !!receiverId.value &&
    transmitterId.value !== receiverId.value,
);

// The data edges that belong to the network surface: signal 'data' between two devices that both
// carry a network connector. These are the network-flow routes (kept separate from the console soft
// patch, which owns 'audio' console-input links).
const networkEdges = computed(() => {
  const ids = new Set(netDevices.value.map((d) => d.id));
  return graph.edges.filter(
    (e) => e.signal === 'data' && ids.has(e.src_device_id) && ids.has(e.dst_device_id),
  );
});

function deviceName(id) {
  return netDevices.value.find((d) => d.id === id)?.name || id;
}

function portLabel(edge) {
  const src = graph.devices.find((d) => d.id === edge.src_device_id);
  const dst = graph.devices.find((d) => d.id === edge.dst_device_id);
  const sp = networkPorts(src).find((p) => p.id === edge.src_port);
  const dp = networkPorts(dst).find((p) => p.id === edge.dst_port);
  const name = (p) => (p ? (p.connector || '').toUpperCase() : '');
  return `${name(sp)} → ${name(dp)}`;
}

function pickPorts(a, b) {
  const aPort = networkPorts(a).find((p) => p.direction === 'out') || networkPorts(a)[0];
  const bPort = networkPorts(b).find((p) => p.direction === 'in') || networkPorts(b)[0];
  return [aPort, bPort];
}

// Phase D convenience: insert a Dante switch and link both ends through it.
async function addToNetwork() {
  if (!canConnect.value) return;
  await graph.joinDanteNetwork(props.jobId, {
    aDeviceId: transmitterId.value,
    bDeviceId: receiverId.value,
    name: switchName.value || null,
  });
}

// Phase E device-to-device direct data link (point-to-point), reusing the generic edge create.
async function connectDirect() {
  if (!canConnect.value) return;
  const a = graph.devices.find((d) => d.id === transmitterId.value);
  const b = graph.devices.find((d) => d.id === receiverId.value);
  const [aPort, bPort] = pickPorts(a, b);
  if (!aPort || !bPort) return;
  await graph.createEdge(
    props.jobId,
    {
      signal: 'data',
      src_device_id: a.id,
      src_port: aPort.id,
      dst_device_id: b.id,
      dst_port: bPort.id,
      channels: 1,
    },
    // "Connect anyway": tolerate a legacy `audio`-signal network port (pre-normalisation) without
    // weakening the real shape checks (wrong direction, missing port, incompatible connector).
    { force: true },
  );
}

async function removeLink(id) {
  await graph.deleteEdge(props.jobId, id);
}
</script>
