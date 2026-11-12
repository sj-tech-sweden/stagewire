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
      <q-select
        v-if="device.kind === 'channel'"
        :model-value="device.attributes?.mixer_input || null"
        dense
        outlined
        emit-value
        map-options
        clearable
        :options="mixerInputOptions"
        :label="t('workspace.colMixerInput')"
        :hint="t('workspace.colMixerInputHint')"
        class="q-mb-sm"
        data-testid="inspector-channel-mixer-input"
        @update:model-value="(v) => save({ attributes: { mixer_input: v || null } })"
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
        v-if="canShowAssetPanel"
        class="q-mb-md"
        data-testid="stockwire-asset-panel"
      >
        <div class="text-caption text-grey-5 text-uppercase q-mb-xs">
          {{ t('workspace.bind.title') }}
        </div>
        <StockwireAssetSummary :asset="boundAsset" />
        <div class="row q-gutter-sm">
          <q-btn
            v-if="canManageAssetLink"
            color="primary"
            no-caps
            icon="link"
            :label="boundAsset.isBound ? t('workspace.bind.change') : t('workspace.bind.bind')"
            data-testid="bind-open"
            data-readonly-allowed
            @click="bindOpen = true"
          />
          <q-btn
            v-if="boundAsset.isBound && canManageAssetLink"
            flat
            color="negative"
            no-caps
            icon="link_off"
            :label="t('workspace.bind.unbind')"
            data-testid="bind-unbind"
            data-readonly-allowed
            @click="unbind"
          />
        </div>
      </div>

      <q-expansion-item
        dense
        default-opened
        icon="cable"
        :label="t('workspace.connect')"
        data-testid="inspector-connect-section"
      >
        <div class="q-gutter-sm q-pa-sm">
          <q-select
            v-model="form.srcPort"
            dense
            outlined
            emit-value
            map-options
            :options="sourcePortOptions"
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
            :options="dstPortOptions"
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
          <div
            v-if="deviceConnections.length"
            class="q-mt-sm"
            data-testid="inspector-connections"
          >
            <div class="text-caption text-grey-6 q-mb-xs">
              {{ t('workspace.existingConnections') }}
            </div>
            <q-list
              dense
              bordered
              separator
            >
              <q-item
                v-for="c in deviceConnections"
                :key="c.id"
              >
                <q-item-section>
                  <div class="text-caption">
                    {{ c.fromName }}
                    <span class="text-grey-6">{{ c.fromPort }}</span>
                    → {{ c.toName }}
                    <span class="text-grey-6">{{ c.toPort }}</span>
                  </div>
                  <div
                    v-if="c.patchLabel || c.connector"
                    class="text-caption text-grey-5"
                  >
                    {{ [c.patchLabel, c.connector].filter(Boolean).join(' · ') }}
                  </div>
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    v-if="!readonly"
                    flat
                    dense
                    round
                    icon="link_off"
                    color="negative"
                    :aria-label="t('workspace.removeConnection')"
                    data-testid="remove-connection"
                    @click="removeConnection(c.id)"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </div>
        </div>
      </q-expansion-item>

      <q-expansion-item
        v-if="readonly && graphData"
        dense
        default-opened
        icon="timeline"
        :label="t('workspace.signalFlow')"
        data-testid="inspector-signal-flow"
      >
        <div class="q-pa-sm">
          <SignalFlowDiagram
            :devices="graphDevices"
            :edges="graphEdges"
            :focus-id="device.id"
          />
        </div>
      </q-expansion-item>
      <template v-else>
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
      </template>

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
        <template v-if="netbox.isEnabled">
          <q-separator class="q-my-sm" />
          <div class="text-caption text-grey-7 q-mb-xs">
            {{ t('workspace.network.netboxTitle') }}
          </div>
          <div class="row q-gutter-xs items-center q-mb-xs">
            <q-chip
              v-if="attrs.netbox_sync_status"
              :color="netboxStatusColor"
              text-color="white"
              dense
            >
              {{ t(`workspace.network.netboxStatus.${attrs.netbox_sync_status}`) }}
            </q-chip>
            <q-btn
              v-if="attrs.netbox_url"
              dense
              flat
              no-caps
              icon="open_in_new"
              color="primary"
              :label="t('workspace.network.netboxOpen')"
              :href="attrs.netbox_url"
              target="_blank"
              rel="noopener"
            />
          </div>
          <q-banner
            v-if="attrs.netbox_sync_status === 'conflict'"
            dense
            rounded
            class="bg-negative text-white q-mb-sm"
          >
            <template #avatar>
              <q-icon name="warning" />
            </template>
            {{ t('workspace.network.netboxConflict') }}
          </q-banner>
          <q-input
            v-if="!readonly"
            :model-value="attrs.network_prefix || ''"
            dense
            outlined
            placeholder="10.0.0.0/24"
            :label="t('workspace.network.netboxPrefix')"
            data-testid="network-netbox-prefix"
            @change="(v) => save({ attributes: { network_prefix: v || null } })"
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
              @click="queryNetboxIps"
            />
            <q-select
              v-if="netbox.availableIps.length"
              v-model="netboxSelectedIp"
              class="col"
              dense
              outlined
              :options="netboxIpOptions"
              :label="t('workspace.network.netboxAvailable')"
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
    :share-token="shareToken"
    :stockwire-product-id="stockwireProductId"
    @bound="onAssetBound"
  />
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import { computed, reactive, ref, watch } from 'vue';
import axios from 'axios';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { useStagePlotStore } from '@/stores/stageplot';
import { useStockwireStore } from '@/stores/stockwire';
import { useNetboxStore } from '@/stores/netbox';
import { getApiBaseUrl } from '@/utils/runtime-config';
import { legacyId } from '@/utils/graphLegacy';
import {
  isPlotElement,
  isPowerNode,
  isVirtual,
  isGear,
  outputPointOptions,
  channelsOf,
  outputsOf,
  mixerInputChoices,
  socketOptions,
  splitSocket,
  portLabelOf,
} from '@/utils/workspace';
import PortUsage from '@/components/PortUsage.vue';
import DeviceEditDialog from '@/components/DeviceEditDialog.vue';
import BindStockwireDialog from '@/components/BindStockwireDialog.vue';
import StockwireAssetSummary from '@/components/StockwireAssetSummary.vue';
import SignalFlowDiagram from '@/components/SignalFlowDiagram.vue';
import { isSpeakerType } from '@/utils/plotObjects';
import {
  DEVICE_BOX_CM,
  DOMAIN_SIGNAL,
  POWER_INLETS,
  needsBookingRequest,
  stockwireAssetOf,
} from '@/utils/workspace';

const props = defineProps({
  jobId: { type: String, required: true },
  device: { type: Object, default: null },
  // Read-only views disable editors; a share token may separately authorize asset binding.
  readonly: { type: Boolean, default: false },
  shareToken: { type: String, default: '' },
  canBindAssets: { type: Boolean, default: false },
  graphData: { type: Object, default: null },
});
const emit = defineEmits(['request-booking', 'remove', 'select', 'asset-bound']);

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const stagePlot = useStagePlotStore();
const stockwire = useStockwireStore();
const shareApi = axios.create({ baseURL: `${getApiBaseUrl()}/api/v1` });
const graphDevices = computed(() => props.graphData?.devices || graph.devices);
const graphEdges = computed(() => props.graphData?.edges || graph.edges);

// A plot object links to a channel (a performer's name goes onto it) and to a device (the
// microphone or other gear they use). Links are set by legacy id, through the plot store.
const elementLinks = computed(() => {
  if (props.device?.kind !== 'plot_element') return {};
  return stagePlot.elements.find((e) => e.id === legacyId(props.device)) || {};
});
const channelOptions = computed(() =>
  graphDevices.value
    .filter((d) => d.kind === 'channel')
    .sort((a, b) => (a.attributes.channel_number || 0) - (b.attributes.channel_number || 0))
    .map((d) => ({ value: legacyId(d), label: `${d.attributes.channel_number || ''} ${d.name}`.trim() })),
);
const gearOptions = computed(() =>
  graphDevices.value
    .filter((d) => !isVirtual(d) && !isPlotElement(d))
    .map((d) => ({ value: legacyId(d), label: d.name })),
);
// Elements that can draw power (an active speaker, a screen, a rack ...) take their power inlet
// from the device they are linked to; people, tables and risers do not.
const isSpeaker = computed(() => isSpeakerType(props.device?.attributes?.element_type));
const isCameraOrProjector = computed(() =>
  ['camera', 'projector'].includes(props.device?.attributes?.element_type),
);
const outputPoints = computed(() => outputPointOptions(graphDevices.value, graphEdges.value));
// A mixer owns a channel list: its channels are their own entities (subdevices of the mixer), not
// buried ports. List them so the crew/editor can open a channel's own inspector from the mixer.
const mixerChannels = computed(() =>
  props.device?.sound_list_id
    ? channelsOf(graphDevices.value, props.device.sound_list_id)
    : [],
);
const videoInputOptions = computed(() =>
  graphDevices.value
    .filter((d) => d.kind === 'video_input')
    .map((d) => ({ value: legacyId(d), label: `${d.attributes.input_number || ''} ${d.name}`.trim() })),
);
const lensOptions = computed(() =>
  graphDevices.value
    .filter((d) => d.kind === 'lens')
    .map((d) => ({ value: legacyId(d), label: d.name })),
);
const NO_POWER_ELEMENTS = new Set(['performer', 'instrument', 'table', 'chair', 'riser', 'dais', 'custom', 'microphone']);
const isPowerable = computed(
  () => props.device?.kind === 'plot_element' && !NO_POWER_ELEMENTS.has(props.device.attributes?.element_type),
);
const linkedGear = computed(() =>
  elementLinks.value.linked_device_id
    ? graphDevices.value.find((d) => d.legacy_ref === `device:${elementLinks.value.linked_device_id}`) || null
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
    ? graphDevices.value.find((d) => d.id === props.device.attributes.power_node_id) || null
    : null,
);
async function unplug() {
  try {
    await graph.assignLoad(props.jobId, props.device.id, { power_node_id: null });
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}

// Unbinding clears both the bound asset and its mirrored Stockwire device ID; no rental allocation is released.
async function unbind() {
  try {
    const updated = props.shareToken
      ? (
          await shareApi.delete(
            `/jobs/${props.jobId}/devices/${props.device.id}/asset-binding`,
            {
              params: {
                token: props.shareToken,
                expected_revision: props.device.revision,
              },
            },
          )
        ).data
      : await graph.unbindStockwireAsset(props.jobId, props.device.id);
    emit('asset-bound', updated);
  } catch (err) {
    if (props.shareToken || !isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: apiErrorText(err) });
    }
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
// The device's own connections, so the connect section shows what is already patched to it
// (a freshly made connection appears here immediately, without opening the trace).
const deviceConnections = computed(() => {
  const id = props.device?.id;
  if (!id) return [];
  return graphEdges.value
    .filter((e) => e.src_device_id === id || e.dst_device_id === id)
    .map((e) => {
      const isSrc = e.src_device_id === id;
      const otherId = isSrc ? e.dst_device_id : e.src_device_id;
      const other = devicesById.value.get(otherId);
      const otherName = other?.name || otherId;
      const socket = e.attributes?.dst_socket || null;
      const srcName = isSrc ? props.device.name : otherName;
      const dstName = isSrc ? otherName : props.device.name;
      return {
        id: e.id,
        signal: e.signal,
        fromName: srcName,
        fromPort: portLabelOf(isSrc ? props.device : other, e.src_port),
        toName: dstName,
        toPort: portLabelOf(isSrc ? other : props.device, e.dst_port, socket),
        patchLabel: e.attributes?.patch_label || '',
        connector: e.attributes?.connector || '',
      };
    });
});

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
// Strict dropdown of the physical inputs a channel can be fed from: the mixer's inputs plus any
// stagebox patched into that mixer (see mixerInputChoices in workspace.js).
const mixerInputOptions = computed(() =>
  mixerInputChoices(props.device, graphDevices.value, graphEdges.value),
);
const deviceIpWebUi = computed(() => {
  const ip = props.device?.attributes?.network_ip;
  return ip ? `http://${ip}` : null;
});

// --- NetBox integration (IPAM/DCIM) -------------------------------------
// When enabled, technicians can pull available IPs from NetBox and assign them
// directly to this device, and conflicts pushed from NetBox surface here. The
// whole block is hidden unless the integration is enabled (see netbox store).
const netbox = useNetboxStore();
const netboxQuerying = ref(false);
const netboxAssigning = ref(false);
const netboxSelectedIp = ref(null);

const netboxIpOptions = computed(() =>
  (netbox.availableIps || []).map((ip) => ({ label: ip.address, value: ip.address })),
);
const netboxStatusColor = computed(() => {
  const s = props.device?.attributes?.netbox_sync_status;
  return { ok: 'positive', conflict: 'negative', error: 'negative', pending: 'warning' }[s] || 'grey';
});

async function queryNetboxIps() {
  const prefix = props.device?.attributes?.network_prefix;
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
  if (!netboxSelectedIp.value) return;
  netboxAssigning.value = true;
  try {
    const res = await netbox.assignIp({
      device_id: props.device.id,
      prefix: props.device?.attributes?.network_prefix || undefined,
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

// Gear (not plot elements, power nodes or virtual list nodes) has a full dialog: ports, weight,
// power, camera specs. It opens from here so any device reached through the inspector can use it.
const detailsOpen = ref(false);
const bindOpen = ref(false);
const stockwireProductId = computed(
  () => props.device?.stockwire_product_id || props.device?.attributes?.stockwire_product_id || null,
);
// The bound Stockwire inventory asset, if any, surfaced from the device's attribute bag.
const boundAsset = computed(() => {
  // Show the scanned/typed code (stockwire_asset_code) to the user, not the resolved
  // Stockwire DB id — that's what a crew member will scan to locate this device.
  return stockwireAssetOf(props.device);
});
const canEditDetails = computed(
  () =>
    props.device &&
    !props.readonly &&
    !isPlotElement(props.device) &&
    !isPowerNode(props.device) &&
    !isVirtual(props.device),
);
const canShowAssetPanel = computed(() => Boolean(props.device && isGear(props.device)));
const canManageAssetLink = computed(
  () => canEditDetails.value || (props.readonly && props.canBindAssets && canShowAssetPanel.value),
);
function onAssetBound(device) {
  emit('asset-bound', device);
}
const devicesById = computed(() => new Map(graphDevices.value.map((d) => [d.id, d])));
const isMixer = (d) => d && (d.kind === 'mixer' || d.device_type === 'mixer');
// Connection targets are real gear only: channels, buses (channel lists), outputs, DMX/video
// virtual nodes, plot elements and power nodes are not endpoints you patch *into*, so offering
// them in the "to device" picker would let a user wire a cable to a non-device (a channel appears
// as its own entity elsewhere, but it is never a connection target).
const otherDevices = computed(() =>
  graphDevices.value
    .filter((d) => d.id !== props.device?.id && isGear(d))
    .map((d) => ({ label: d.name, value: d.id })),
);
// Source ("from") ports: the device's own out-ports, plus — when this device is a mixer — each of
// its channels and output buses as a selectable source. A `node:<id>` value means the edge leaves
// that sub-node's `out` port (so you can send from a specific channel, not just the mixer's jack).
const sourcePortOptions = computed(() => {
  const base = portOptions(props.device, 'out');
  if (!isMixer(props.device)) return base;
  const listId = props.device.sound_list_id;
  const subs = [
    ...channelsOf(graphDevices.value, listId).map((ch) => ({
      // the physical mixer input a channel is fed from is part of the signal flow, so surface it
      label: `${ch.name}${ch.attributes?.mixer_input ? ` (${ch.attributes.mixer_input})` : ""} · channel out`,
      value: `node:${ch.id}`,
    })),
    ...outputsOf(graphDevices.value, listId).map((o) => ({
      label: `${o.name} · bus out`,
      value: `node:${o.id}`,
    })),
  ];
  return [...base, ...subs];
});
// Destination ("to") ports: when the chosen gear is a mixer, offer its channels as the targets —
// each ends on the channel's `in` port, which is the *true end of the signal chain* (a mic or a
// digital stagebox terminates on the channel, not on the mixer's physical jack). Generic in-ports
// of the mixer are still offered for the rare direct-to-jack case.
const dstDevice = computed(() => devicesById.value.get(form.dstId));
const dstPortOptions = computed(() => {
  const d = dstDevice.value;
  if (!d) return [];
  if (!isMixer(d)) return socketOptions(d, 'in');
  const listId = d.sound_list_id;
  const subs = channelsOf(graphDevices.value, listId).map((ch) => ({
    // the physical mixer input a channel is fed from is part of the signal flow, so surface it
    label: `${ch.name}${ch.attributes?.mixer_input ? ` (${ch.attributes.mixer_input})` : ""} · channel in`,
    value: `node:${ch.id}`,
  }));
  return [...subs, ...socketOptions(d, 'in')];
});
function resolveNodeRef(ref) {
  // `node:<id>` selects a sub-node (channel/bus) of a mixer; plain ids stay as the device/port.
  if (typeof ref === 'string' && ref.startsWith('node:')) return { id: ref.slice(5), port: null };
  return { id: null, port: ref };
}
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
  if (props.graphData) {
    const visited = new Set([props.device.id]);
    const queue = [{ id: props.device.id, depth: 0 }];
    const hops = [];
    while (queue.length) {
      const current = queue.shift();
      const adjacent = graphEdges.value.filter((edge) =>
        direction === 'upstream'
          ? edge.dst_device_id === current.id
          : edge.src_device_id === current.id,
      );
      for (const edge of adjacent) {
        const deviceId =
          direction === 'upstream' ? edge.src_device_id : edge.dst_device_id;
        if (visited.has(deviceId)) continue;
        visited.add(deviceId);
        const depth = current.depth + 1;
        hops.push({ edge, depth, device_id: deviceId });
        queue.push({ id: deviceId, depth });
      }
    }
    traces[direction] = { hops, issues: [] };
    return;
  }
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
  // A `node:<id>` source/destination means the edge terminates on a mixer sub-node (a channel or
  // output bus) rather than the mixer itself — the channel being the true endpoint of the chain.
  const srcRef = resolveNodeRef(form.srcPort);
  const dstRef = resolveNodeRef(form.dstPort);
  // A socket ("in-xlr3#5") lands on one physical input of a multi-channel port: the port is the
  // id before the `#`, and the socket travels on the edge so validation can check it.
  const dstSplit = dstRef.port ? splitSocket(dstRef.port) : { port: null, socket: null };
  const srcDeviceId = srcRef.id ?? src.id;
  const srcPortId = srcRef.port ?? 'out';
  const dstDeviceId = dstRef.id ?? form.dstId;
  const dstPortId = dstSplit.port ?? 'in';
  const port =
    (devicesById.value.get(srcDeviceId)?.ports || []).find((p) => p.id === srcPortId) ||
    (src.ports || []).find((p) => p.id === srcPortId);
  try {
    await graph.createEdge(
      props.jobId,
      {
        signal: port?.signal || DOMAIN_SIGNAL[src.domain] || 'audio',
        src_device_id: srcDeviceId,
        src_port: srcPortId,
        dst_device_id: dstDeviceId,
        dst_port: dstPortId,
        channels: form.channels || 1,
        attributes: dstSplit.socket ? { dst_socket: dstSplit.socket } : {},
      },
      { force },
    );
    rejected.value = [];
    // reset the form so the new edge shows in the connection list below rather than lingering
    Object.assign(form, { srcPort: null, dstId: null, dstPort: null, channels: 1 });
  } catch (err) {
    const detail = err.response?.data?.detail;
    if (detail?.code === 'invalid_connection') rejected.value = detail.issues;
    else $q.notify({ type: 'negative', message: typeof detail === 'string' ? detail : err.message });
  }
}

async function removeConnection(edgeId) {
  if (props.readonly) return;
  try {
    await graph.deleteEdge(props.jobId, edgeId);
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}
</script>

<style scoped>
/* Read-only crew view keeps editors inert and hides actions except those explicitly authorized
   by the share token, such as Stockwire asset binding. */
.inspector-readonly :deep(.q-field) {
  pointer-events: none;
}
.inspector-readonly :deep(.q-btn:not([data-readonly-allowed])) {
  display: none !important;
}
</style>

