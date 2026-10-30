<template>
  <div class="q-pa-md">
    <div class="text-subtitle1 q-mb-sm">
      {{ t('workspace.inspector') }}
    </div>
    <div
      v-if="!device"
      class="text-grey-6"
    >
      {{ t('workspace.selectHint') }}
    </div>
    <template v-else>
      <q-input
        :model-value="device.name"
        dense
        outlined
        :label="t('workspace.colName')"
        class="q-mb-sm"
        data-testid="inspector-name"
        @change="(v) => save({ name: v })"
      />
      <q-input
        :model-value="device.notes"
        dense
        outlined
        autogrow
        :label="t('workspace.colNotes')"
        class="q-mb-sm"
        @change="(v) => save({ notes: v })"
      />
      <div class="text-caption text-grey-6 q-mb-sm">
        {{ device.domain }} · {{ device.kind || '—' }}
      </div>

      <div
        v-if="needsBookingRequest(device) || device.stockwire_request_status"
        class="q-mb-md"
      >
        <q-btn
          v-if="needsBookingRequest(device)"
          color="warning"
          text-color="black"
          no-caps
          icon="add_shopping_cart"
          :label="t('workspace.requestAdd')"
          data-testid="request-add"
          @click="emit('request-booking', device)"
        />
        <q-badge
          v-else
          :color="device.stockwire_request_status === 'failed' ? 'negative' : 'positive'"
          :label="statusLabel"
        />
      </div>

      <q-expansion-item
        dense
        default-opened
        icon="cable"
        :label="t('workspace.connect')"
      >
        <div class="q-gutter-sm q-pa-sm">
          <q-select
            v-model="form.srcPort"
            dense
            outlined
            emit-value
            map-options
            :options="portOptions(device, 'out')"
            :label="t('workspace.fromPort')"
          />
          <q-select
            v-model="form.dstId"
            dense
            outlined
            emit-value
            map-options
            :options="otherDevices"
            :label="t('workspace.toDevice')"
          />
          <q-select
            v-model="form.dstPort"
            dense
            outlined
            emit-value
            map-options
            :disable="!form.dstId"
            :options="portOptions(devicesById.get(form.dstId), 'in')"
            :label="t('workspace.toPort')"
          />
          <q-input
            v-model.number="form.channels"
            dense
            outlined
            type="number"
            min="1"
            :label="t('workspace.channels')"
          />
          <q-banner
            v-if="rejected.length"
            dense
            class="bg-negative text-white"
          >
            <div>{{ t('workspace.connectFailed') }}</div>
            <div
              v-for="issue in rejected"
              :key="issue.message"
              class="text-caption"
            >
              {{ issue.message }}
            </div>
            <template #action>
              <q-btn
                flat
                no-caps
                color="white"
                :label="t('workspace.connectForce')"
                @click="connect(true)"
              />
            </template>
          </q-banner>
          <q-btn
            color="primary"
            no-caps
            :disable="!form.srcPort || !form.dstId || !form.dstPort"
            :label="t('workspace.connectAction')"
            data-testid="connect"
            @click="connect(false)"
          />
        </div>
      </q-expansion-item>

      <q-expansion-item
        v-for="dir in ['upstream', 'downstream']"
        :key="dir"
        dense
        icon="timeline"
        :label="dir === 'upstream' ? t('workspace.traceUp') : t('workspace.traceDown')"
        @show="loadTrace(dir)"
      >
        <div class="q-pa-sm">
          <div
            v-if="!traces[dir] || !traces[dir].hops.length"
            class="text-grey-6"
          >
            {{ t('workspace.traceEmpty') }}
          </div>
          <q-list
            v-else
            dense
          >
            <q-item
              v-for="hop in traces[dir].hops"
              :key="hop.edge.id"
            >
              <q-item-section>
                {{ '→ '.repeat(hop.depth) }}{{ devicesById.get(hop.device_id)?.name || '?' }}
              </q-item-section>
            </q-item>
          </q-list>
          <div
            v-if="traces[dir]?.issues.length"
            class="text-negative text-caption"
          >
            {{ t('workspace.traceIssues', { n: traces[dir].issues.length }) }}
          </div>
        </div>
      </q-expansion-item>

      <q-btn
        flat
        color="negative"
        no-caps
        icon="delete"
        class="q-mt-md"
        :label="t('workspace.remove')"
        @click="emit('remove', device)"
      />
    </template>
  </div>
</template>

<script setup>
import { isRevisionConflict } from '@/utils/graph';
import { computed, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { DOMAIN_SIGNAL, needsBookingRequest } from '@/utils/workspace';

const props = defineProps({
  jobId: { type: String, required: true },
  device: { type: Object, default: null },
});
const emit = defineEmits(['request-booking', 'remove']);

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const form = reactive({ srcPort: null, dstId: null, dstPort: null, channels: 1 });
const rejected = ref([]);
const traces = reactive({ upstream: null, downstream: null });

const devicesById = computed(() => new Map(graph.devices.map((d) => [d.id, d])));
const otherDevices = computed(() =>
  graph.devices
    .filter((d) => d.id !== props.device?.id)
    .map((d) => ({ label: d.name, value: d.id })),
);
const statusLabel = computed(() => {
  const status = props.device?.stockwire_request_status;
  if (status === 'failed') return t('workspace.requestFailed');
  if (status === 'pending') return t('workspace.pending');
  return props.device?.stockwire_booked ? t('workspace.booked') : t('workspace.requested');
});

function portOptions(device, direction) {
  return (device?.ports || [])
    .filter((p) => p.direction === direction)
    .map((p) => ({ label: `${p.id}${p.connector ? ` (${p.connector})` : ''}`, value: p.id }));
}

watch(
  () => props.device?.id,
  () => {
    Object.assign(form, { srcPort: null, dstId: null, dstPort: null, channels: 1 });
    rejected.value = [];
    traces.upstream = null;
    traces.downstream = null;
  },
);

async function loadTrace(direction) {
  traces[direction] = await graph.trace(props.jobId, props.device.id, direction);
}

async function save(changes) {
  try {
    await graph.updateDevice(props.jobId, props.device.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
    }
  }
}

async function connect(force) {
  const src = props.device;
  const port = (src.ports || []).find((p) => p.id === form.srcPort);
  try {
    await graph.createEdge(
      props.jobId,
      {
        signal: port?.signal || DOMAIN_SIGNAL[src.domain] || 'audio',
        src_device_id: src.id,
        src_port: form.srcPort,
        dst_device_id: form.dstId,
        dst_port: form.dstPort,
        channels: form.channels || 1,
      },
      { force },
    );
    rejected.value = [];
  } catch (err) {
    const detail = err.response?.data?.detail;
    if (detail?.code === 'invalid_connection') rejected.value = detail.issues;
    else $q.notify({ type: 'negative', message: typeof detail === 'string' ? detail : err.message });
  }
}
</script>
