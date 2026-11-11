<template>
  <div
    class="q-pa-md"
    :class="{ 'inspector-readonly': readonly }"
  >
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
      <q-btn
        v-if="canEditDetails"
        flat
        dense
        no-caps
        icon="tune"
        class="q-mb-sm"
        :label="t('workspace.editDetails')"
        data-testid="inspector-edit-details"
        @click="detailsOpen = true"
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
      <div
        v-if="pluggedNode"
        class="row items-center q-mb-sm"
        data-testid="plugged-into"
      >
        <div class="col text-caption">
          {{ t('workspace.pluggedIntoLabel') }}: <strong>{{ pluggedNode.name }}</strong>
          <span v-if="device.attributes.power_connector">({{ device.attributes.power_connector }})</span>
        </div>
        <q-btn
          flat
          dense
          no-caps
          color="negative"
          icon="power_off"
          :label="t('workspace.unplug')"
          data-testid="unplug"
          @click="unplug"
        />
      </div>
      <div
        v-if="device.kind === 'plot_element'"
        class="q-mb-sm"
        data-testid="element-inspector"
      >
        <q-input
          :model-value="device.canvas_rotation"
          dense
          outlined
          type="number"
          class="q-mb-sm"
          :label="t('stagePlot.rotation')"
          @change="(v) => save({ canvas_rotation: Number(v) || 0 })"
        />
        <q-select
          :model-value="elementLinks.linked_channel_id"
          dense
          outlined
          clearable
          emit-value
          map-options
          class="q-mb-sm"
          :options="channelOptions"
          :label="t('stagePlot.linkChannel')"
          data-testid="element-channel"
          @update:model-value="(v) => linkElement({ linked_channel_id: v || null })"
        />
        <q-select
          :model-value="elementLinks.linked_device_id"
          dense
          outlined
          clearable
          emit-value
          map-options
          :options="gearOptions"
          :label="t('workspace.linkMic')"
          data-testid="element-device"
          @update:model-value="(v) => linkElement({ linked_device_id: v || null })"
        />
        <div
          v-if="isSpeaker"
          class="q-mt-sm"
          data-testid="speaker-section"
        >
          <div class="text-subtitle2">
            {{ t('stagePlot.speakerSection') }}
          </div>
          <div class="row q-col-gutter-sm q-mt-xs">
            <q-input
              :model-value="device.attributes?.coverage_angle_h ?? 0"
              class="col-6"
              dense
              outlined
              type="number"
              :label="t('stagePlot.coverageAngle')"
              data-testid="coverage-angle"
              @change="(v) => save({ attributes: { coverage_angle_h: Number(v) || 0 } })"
            />
            <q-input
              :model-value="device.attributes?.coverage_distance_m ?? 0"
              class="col-6"
              dense
              outlined
              type="number"
              :label="t('stagePlot.coverageDistance')"
              data-testid="coverage-distance"
              @change="(v) => save({ attributes: { coverage_distance_m: Number(v) || 0 } })"
            />
          </div>
          <q-select
            :model-value="elementLinks.linked_output_point_id"
            dense
            outlined
            clearable
            emit-value
            map-options
            class="q-mt-sm"
            :options="outputPoints"
            :label="t('stagePlot.linkOutput')"
            data-testid="element-output-point"
            @update:model-value="(v) => linkElement({ linked_output_point_id: v || null })"
          />
        </div>
        <div
          v-if="isCameraOrProjector"
          class="q-mt-sm"
          data-testid="camera-section"
        >
          <q-select
            :model-value="elementLinks.linked_video_input_id"
            dense
            outlined
            clearable
            emit-value
            map-options
            class="q-mb-sm"
            :options="videoInputOptions"
            :label="t('stagePlot.linkVideo')"
            data-testid="element-video-input"
            @update:model-value="(v) => linkElement({ linked_video_input_id: v || null })"
          />
          <q-select
            v-if="device.attributes?.element_type === 'camera'"
            :model-value="elementLinks.linked_lens_device_id"
            dense
            outlined
            clearable
            emit-value
            map-options
            class="q-mb-sm"
            :options="lensOptions"
            :label="t('stagePlot.linkLens')"
            data-testid="element-lens"
            @update:model-value="(v) => linkElement({ linked_lens_device_id: v || null })"
          />
          <q-input
            v-if="device.attributes?.element_type === 'camera'"
            :model-value="device.attributes?.focal_mm"
            dense
            outlined
            type="number"
            :label="t('stagePlot.focalLength')"
            data-testid="element-focal"
            @change="(v) => save({ attributes: { focal_mm: v === '' ? null : Number(v) } })"
          />
        </div>
        <div
          v-if="isPowerable"
          class="q-mt-sm"
        >
          <q-select
            v-if="linkedGear"
            :model-value="linkedGear.attributes?.power_inlet || 'iec_c13'"
            dense
            outlined
            emit-value
            map-options
            :options="POWER_INLETS"
            :label="t('workspace.powerInlet')"
            :hint="t('workspace.elementInletHint')"
            data-testid="element-inlet"
            @update:model-value="setLinkedInlet"
          />
          <q-btn
            v-else
            flat
            no-caps
            icon="add"
            :label="t('workspace.createDeviceFor')"
            data-testid="element-create-device"
            @click="createDeviceForElement"
          />
        </div>
      </div>
      <q-select
        v-if="device.kind !== 'plot_element' && !isVirtual(device) && !isPowerNode(device)"
        :model-value="device.attributes?.power_inlet || 'iec_c13'"
        dense
        outlined
        emit-value
        map-options
        class="q-mb-sm"
        :options="POWER_INLETS"
        :label="t('workspace.powerInlet')"
        data-testid="inspector-inlet"
        @update:model-value="(v) => save({ attributes: { power_inlet: v } })"
      />
      <div class="row q-col-gutter-sm q-mb-sm">
        <q-input
          :model-value="device.attributes?.width_cm"
          class="col-6"
          dense
          outlined
          type="number"
          min="5"
          :label="t('workspace.plotWidth')"
          :placeholder="String(DEVICE_BOX_CM.w)"
          data-testid="inspector-width"
          @change="(v) => save({ attributes: { width_cm: v === '' ? null : Number(v) } })"
        />
        <q-input
          :model-value="device.attributes?.height_cm"
          class="col-6"
          dense
          outlined
          type="number"
          min="5"
          :label="t('workspace.plotHeight')"
          :placeholder="String(DEVICE_BOX_CM.h)"
          data-testid="inspector-height"
          @change="(v) => save({ attributes: { height_cm: v === '' ? null : Number(v) } })"
        />
      </div>
      <div class="text-caption text-grey-6 q-mb-sm">
        {{ device.domain }} · {{ device.kind || '—' }}
      </div>

      <PortUsage
        :device="device"
        class="q-mb-md"
      />

      <!-- A mixer's channels are their own entities (subdevices), not ports on the mixer. List them so
           tapping one opens that channel's own inspector (cable flow, source, ports) — consistent with
           the crew/patch views, which already treat a channel as its own device. -->
      <div
        v-if="mixerChannels.length"
        class="q-mb-md"
        data-testid="mixer-channels"
      >
        <div class="text-caption text-grey-5 text-uppercase q-mb-xs">
          {{ t('workspace.channelsOfMixer') }}
        </div>
        <q-list
          bordered
          separator
        >
          <q-item
            v-for="ch in mixerChannels"
            :key="ch.id"
            clickable
            :data-testid="`mixer-channel-${ch.id}`"
            @click="emit('select', ch.id)"
          >
            <q-item-section>
              <q-item-label>{{ ch.name }}</q-item-label>
              <q-item-label
                v-if="ch.attributes?.source_label || ch.attributes?.device"
                caption
              >
                {{ ch.attributes.source_label || ch.attributes.device }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-icon name="open_in_new" />
            </q-item-section>
          </q-item>
        </q-list>
      </div>

      <div
        v-if="(needsBookingRequest(device) || device.stockwire_request_status) && stockwire.isEnabled"
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

      <div
        v-if="canEditDetails"
        class="q-mb-md"
        data-testid="stockwire-asset-panel"
      >
        <div class="text-caption text-grey-5 text-uppercase q-mb-xs">
          {{ t('workspace.bind.title') }}
        </div>
        <div
          v-if="boundAsset.id"
          class="q-mb-xs"
        >
          <div class="text-caption">
            <span class="text-grey-5">{{ t('workspace.bind.code') }}:</span> {{ boundAsset.id }}
          </div>
          <div
            v-if="boundAsset.tag"
            class="text-caption"
          >
            <span class="text-grey-5">{{ t('workspace.bind.tag') }}:</span> {{ boundAsset.tag }}
          </div>
          <div
            v-if="boundAsset.serial"
            class="text-caption"
          >
            <span class="text-grey-5">{{ t('workspace.bind.serial') }}:</span> {{ boundAsset.serial }}
          </div>
          <div
            v-if="boundAsset.description"
            class="text-caption"
          >
            {{ boundAsset.description }}
          </div>
        </div>
        <div class="row q-gutter-sm">
          <q-btn
            v-if="!boundAsset.id"
            color="primary"
            no-caps
            icon="link"
            :label="t('workspace.bind.bind')"
            data-testid="bind-open"
            @click="bindOpen = true"
          />
          <q-btn
            v-else
            flat
            color="negative"
            no-caps
            icon="link_off"
            :label="t('workspace.bind.unbind')"
            data-testid="bind-unbind"
            @click="unbind"
          />
        </div>
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
            data-testid="connect-to-device"
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

      <q-expansion-item
        v-if="isNetworkedDomain"
        dense
        icon="router"
        :label="t('workspace.network.title')"
        data-testid="network-panel"
      >
        <div class="q-gutter-sm q-pa-sm">
          <div class="text-caption text-grey-6">
            {{ t('workspace.network.hint') }}
          </div>
          <q-input
            :model-value="attrs.network_ip || ''"
            dense
            outlined
            placeholder="192.168.1.10"
            :label="t('workspace.network.ip')"
            data-testid="network-ip"
            @change="(v) => save({ attributes: { network_ip: v || null } })"
          />
          <q-btn
            v-if="deviceIpWebUi"
            dense
            flat
            no-caps
            icon="open_in_new"
            color="primary"
            class="q-mb-xs"
            :label="t('workspace.network.openWebUi')"
            :href="deviceIpWebUi"
            target="_blank"
            rel="noopener"
            data-testid="network-open-webui"
          >
            <q-tooltip>{{ t('workspace.network.webUiHint') }}</q-tooltip>
          </q-btn>
          <q-input
            :model-value="attrs.network_subnet || ''"
            dense
            outlined
            placeholder="255.255.255.0"
            :label="t('workspace.network.subnet')"
            data-testid="network-subnet"
            @change="(v) => save({ attributes: { network_subnet: v || null } })"
          />
          <q-input
            :model-value="attrs.network_vlan"
            dense
            outlined
            type="number"
            min="0"
            max="4095"
            :label="t('workspace.network.vlan')"
            data-testid="network-vlan"
            @change="(v) => save({ attributes: { network_vlan: v === '' || v === null ? null : Number(v) } })"
          />
          <q-select
            :model-value="attrs.network_protocols || []"
            dense
            outlined
            multiple
            use-chips
            emit-value
            map-options
            :options="networkProtocols"
            :label="t('workspace.network.protocols')"
            data-testid="network-protocols"
            @update:model-value="(v) => save({ attributes: { network_protocols: v || [] } })"
          />
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
  <DeviceEditDialog
    v-model="detailsOpen"
    :device="device"
    :job-id="jobId"
  />
  <BindStockwireDialog
    v-model="bindOpen"
    :job-id="jobId"
    :device="device"
  />
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import { computed, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { useStagePlotStore } from '@/stores/stageplot';
import { useStockwireStore } from '@/stores/stockwire';
import { legacyId } from '@/utils/graphLegacy';
import {
  isPlotElement,
  isPowerNode,
  isVirtual,
  isGear,
  outputPointOptions,
  channelsOf,
} from '@/utils/workspace';
import PortUsage from '@/components/PortUsage.vue';
import DeviceEditDialog from '@/components/DeviceEditDialog.vue';
import BindStockwireDialog from '@/components/BindStockwireDialog.vue';
import { isSpeakerType } from '@/utils/plotObjects';
import { DEVICE_BOX_CM, DOMAIN_SIGNAL, POWER_INLETS, needsBookingRequest } from '@/utils/workspace';

const props = defineProps({
  jobId: { type: String, required: true },
  device: { type: Object, default: null },
  // Read-only views (e.g. the crew share link) render the same inspector, but every editor is
  // disabled and no action button is offered, so the crew sees an exact, non-editable copy.
  readonly: { type: Boolean, default: false },
});
const emit = defineEmits(['request-booking', 'remove', 'select']);

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const stagePlot = useStagePlotStore();
const stockwire = useStockwireStore();

// A plot object links to a channel (a performer's name goes onto it) and to a device (the
// microphone or other gear they use). Links are set by legacy id, through the plot store.
const elementLinks = computed(() => {
  if (props.device?.kind !== 'plot_element') return {};
  return stagePlot.elements.find((e) => e.id === legacyId(props.device)) || {};
});
const channelOptions = computed(() =>
  graph.devices
    .filter((d) => d.kind === 'channel')
    .sort((a, b) => (a.attributes.channel_number || 0) - (b.attributes.channel_number || 0))
    .map((d) => ({ value: legacyId(d), label: `${d.attributes.channel_number || ''} ${d.name}`.trim() })),
);
const gearOptions = computed(() =>
  graph.devices
    .filter((d) => !isVirtual(d) && !isPlotElement(d))
    .map((d) => ({ value: legacyId(d), label: d.name })),
);
// Elements that can draw power (an active speaker, a screen, a rack ...) take their power inlet
// from the device they are linked to; people, tables and risers do not.
const isSpeaker = computed(() => isSpeakerType(props.device?.attributes?.element_type));
const isCameraOrProjector = computed(() =>
  ['camera', 'projector'].includes(props.device?.attributes?.element_type),
);
const outputPoints = computed(() => outputPointOptions(graph.devices, graph.edges));
// A mixer owns a channel list: its channels are their own entities (subdevices of the mixer), not
// buried ports. List them so the crew/editor can open a channel's own inspector from the mixer.
const mixerChannels = computed(() =>
  props.device?.sound_list_id
    ? channelsOf(graph.devices, props.device.sound_list_id)
    : [],
);
const videoInputOptions = computed(() =>
  graph.devices
    .filter((d) => d.kind === 'video_input')
    .map((d) => ({ value: legacyId(d), label: `${d.attributes.input_number || ''} ${d.name}`.trim() })),
);
const lensOptions = computed(() =>
  graph.devices
    .filter((d) => d.kind === 'lens')
    .map((d) => ({ value: legacyId(d), label: d.name })),
);
const NO_POWER_ELEMENTS = new Set(['performer', 'instrument', 'table', 'chair', 'riser', 'dais', 'custom', 'microphone']);
const isPowerable = computed(
  () => props.device?.kind === 'plot_element' && !NO_POWER_ELEMENTS.has(props.device.attributes?.element_type),
);
const linkedGear = computed(() =>
  elementLinks.value.linked_device_id
    ? graph.devices.find((d) => d.legacy_ref === `device:${elementLinks.value.linked_device_id}`) || null
    : null,
);
async function setLinkedInlet(value) {
  try {
    await graph.updateDevice(props.jobId, linkedGear.value.id, { attributes: { power_inlet: value } });
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}

// A speaker or screen without a device gets one (named after it) so its power can be set.
async function createDeviceForElement() {
  let created = null;
  try {
    created = await graph.createAudioDevice(props.jobId, { name: props.device.name, device_type: 'other' });
    await stagePlot.updateElement(props.jobId, legacyId(props.device), { linked_device_id: legacyId(created) });
  } catch (err) {
    // a device made but not linked would be left behind (and made again on the next try)
    if (created) await graph.deleteDevice(props.jobId, created.id).catch(() => {});
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}
// Gear plugged into a power node shows where, and can be unplugged (the node keeps its other loads).
const pluggedNode = computed(() =>
  props.device?.attributes?.power_node_id
    ? graph.devices.find((d) => d.id === props.device.attributes.power_node_id) || null
    : null,
);
async function unplug() {
  try {
    await graph.assignLoad(props.jobId, props.device.id, { power_node_id: null });
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}

// Unbinding clears the local asset link (the integration has no allocation to release — out of scope).
async function unbind() {
  try {
    await graph.updateDevice(props.jobId, props.device.id, {
      attributes: {
        stockwire_asset_id: null,
        stockwire_asset_code: null,
        stockwire_asset_tag: null,
        stockwire_asset_serial: null,
        stockwire_asset_description: null,
      },
    });
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}

async function linkElement(links) {
  try {
    await stagePlot.updateElement(props.jobId, legacyId(props.device), links);
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}
const form = reactive({ srcPort: null, dstId: null, dstPort: null, channels: 1 });
const rejected = ref([]);
const traces = reactive({ upstream: null, downstream: null });

// AVL signal domains (audio/video/lighting) carry IP-networked control gear; power and
// rigging nodes don't, so the Network & Control panel is hidden for them.
const NETWORK_PROTOCOLS = [
  { label: 'Dante', value: 'dante' },
  { label: 'NDI', value: 'ndi' },
  { label: 'ArtNet', value: 'artnet' },
  { label: 'sACN', value: 'sacn' },
];
const networkProtocols = NETWORK_PROTOCOLS;
const isNetworkedDomain = computed(() =>
  ['audio', 'video', 'lighting'].includes(props.device?.domain),
);
// Snapshot of the device's attribute bag; new keys (network_*) are merged in by the
// shallow-merge update path, so sibling keys are never clobbered by a single-field edit.
const attrs = computed(() => props.device?.attributes || {});
const deviceIpWebUi = computed(() => {
  const ip = props.device?.attributes?.network_ip;
  return ip ? `http://${ip}` : null;
});

// Gear (not plot elements, power nodes or virtual list nodes) has a full dialog: ports, weight,
// power, camera specs. It opens from here so any device reached through the inspector can use it.
const detailsOpen = ref(false);
const bindOpen = ref(false);
// The bound Stockwire inventory asset, if any, surfaced from the device's attribute bag.
const boundAsset = computed(() => {
  const a = props.device?.attributes || {};
  // Show the scanned/typed code (stockwire_asset_code) to the user, not the resolved
  // Stockwire DB id — that's what a crew member will scan to locate this device.
  const code = a.stockwire_asset_code || a.stockwire_asset_id || null;
  return {
    id: code,
    code,
    tag: a.stockwire_asset_tag || null,
    serial: a.stockwire_asset_serial || null,
    description: a.stockwire_asset_description || null,
  };
});
const canEditDetails = computed(
  () =>
    props.device &&
    !props.readonly &&
    !isPlotElement(props.device) &&
    !isPowerNode(props.device) &&
    !isVirtual(props.device),
);
const devicesById = computed(() => new Map(graph.devices.map((d) => [d.id, d])));
// Connection targets are real gear only: channels, buses (channel lists), outputs, DMX/video
// virtual nodes, plot elements and power nodes are not endpoints you patch *into*, so offering
// them in the "to device" picker would let a user wire a cable to a non-device (a channel appears
// as its own entity elsewhere, but it is never a connection target).
const otherDevices = computed(() =>
  graph.devices
    .filter((d) => d.id !== props.device?.id && isGear(d))
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
  if (props.readonly) return;
  try {
    await graph.updateDevice(props.jobId, props.device.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: apiErrorText(err) });
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

<style scoped>
/* Read-only crew view: the inspector still renders identically, but every editor is inert and no
   action button is offered, so a crew member sees an exact, non-editable copy. */
.inspector-readonly :deep(.q-field) {
  pointer-events: none;
}
.inspector-readonly :deep(.q-btn) {
  display: none !important;
}
</style>

