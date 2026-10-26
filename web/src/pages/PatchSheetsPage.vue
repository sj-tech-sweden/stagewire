<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('channels.backToJobs')"
        class="q-mr-sm"
        @click="router.push(`/jobs/${jobId}`)"
      />
      <div class="col">
        <div class="text-h5">
          {{ t('channels.patchSheets') }}
        </div>
        <div
          v-if="job"
          class="text-subtitle2 text-grey-7"
        >
          <span v-if="job.title">{{ job.title }}</span>
          <span v-if="job.venue_name"> · {{ job.venue_name }}</span>
        </div>
      </div>
      <q-btn
        flat
        icon="picture_as_pdf"
        :label="t('reports.generatePatchSheet')"
        :disable="!current"
        @click="showPatchpointReport = true"
      />
      <q-btn
        flat
        icon="print"
        :label="t('app.actions.print')"
        :disable="!selected"
        @click="printSheet"
      />
      <q-btn
        flat
        icon="map"
        :label="t('stagePlot.viewOnStagePlot')"
        :disable="!current"
        class="q-ml-sm"
        @click="openStagePlot"
      />
    </div>

    <div
      v-if="error"
      class="text-negative q-mb-md"
    >
      {{ error }}
    </div>

    <div
      v-if="!error"
      class="row q-mb-md items-center"
    >
      <q-select
        v-model="selected"
        :options="sheetOptions"
        :label="t('channels.patchSheetsSelect')"
        emit-value
        map-options
        style="min-width: 280px"
      />
      <span
        v-if="current"
        class="q-ml-md text-subtitle2 text-grey-7"
      >{{ pointTypeLabel(current.point_type) }}</span>
    </div>

    <div
      v-if="!error && !sheets.length"
      class="text-grey q-pa-md text-center"
    >
      {{ t('channels.noPatchSheets') }}
    </div>

    <div
      v-else-if="current"
      id="print-area"
      class="patch-sheet"
    >
      <q-card
        flat
        bordered
        class="q-mb-md no-print"
      >
        <q-card-section>
          <div class="text-subtitle2 q-mb-xs">
            {{ t('stagePlot.title') }} ·
            <span class="text-primary">{{ current.name }}</span>
          </div>
          <div class="text-caption text-grey-7 q-mb-sm">
            {{ t('stagePlot.highlightActive', { name: current.name }) }}
          </div>
          <StagePlotMini
            :elements="plotElements"
            :stage-width="job?.stage_width_cm || 1200"
            :stage-height="job?.stage_height_cm || 700"
            :highlight-ids="currentHighlightIds"
            :channel-colors="channelColors"
            :max-width="560"
          />
        </q-card-section>
      </q-card>

      <div class="text-h6 q-mb-xs">
        {{ current.name }}
      </div>
      <div class="text-subtitle2 text-grey-7 q-mb-sm">
        {{ job?.title }}<span v-if="job?.venue_name"> · {{ job.venue_name }}</span>
      </div>
      <div class="text-caption text-grey-7 q-mb-sm">
        {{ t('channels.flowDirectionHint') }}
      </div>
      <div class="flow-diagram q-mb-md">
        <div class="text-subtitle2 q-mb-xs">
          {{ t('channels.flowTitle') }}
        </div>
        <div
          v-if="!flowChains.length"
          class="text-grey-6 text-caption"
        >
          {{ t('channels.flowEmpty') }}
        </div>
        <div
          v-for="(chain, ci) in flowChains"
          :key="ci"
          class="flow-chain column q-mb-sm"
        >
          <div class="row items-center q-mb-xs">
            <q-badge
              :color="chain.kind === 'output' ? 'secondary' : 'primary'"
              :label="chain.kind === 'output' ? t('channels.outputs') : t('channels.inputs')"
              class="q-mr-sm"
            />
            <span class="text-subtitle2">{{ chain.label }}</span>
            <q-btn
              dense
              flat
              round
              size="sm"
              icon="map"
              class="q-ml-sm"
              :aria-label="t('stagePlot.highlightChannel')"
              @click="highlightChannelOnStage(chain.channelId)"
            />
          </div>
          <div class="flow-tree-wrap q-mt-xs">
            <div
              v-if="chain.kind === 'input'"
              class="row items-center flow-linear-row wrap"
            >
              <template
                v-for="(n, i) in chain.nodes"
                :key="n.id || i"
              >
                <q-card
                  flat
                  bordered
                  :class="[
                    'flow-node q-pa-xs text-center',
                    n.name === current.name ? 'flow-node-active' : '',
                  ]"
                >
                  <div class="text-caption">
                    {{ n.name || '—' }}
                  </div>
                  <div class="text-caption text-grey-7">
                    {{ [n.connector, n.patch_label].filter(Boolean).join(' · ') || '—' }}
                  </div>
                  <div
                    v-if="n.device"
                    class="text-caption text-primary"
                  >
                    ⬡ {{ n.device }}
                  </div>
                </q-card>
                <q-icon
                  v-if="i < chain.nodes.length - 1"
                  name="arrow_forward"
                  class="q-mx-xs flow-linear-arrow"
                />
              </template>
            </div>
            <FlowTree
              v-else
              :node="chain.tree"
              :highlight="current.name"
              compact
            />
          </div>
        </div>
      </div>
      <q-list
        v-if="$q.screen.lt.sm"
        separator
        class="q-mt-sm"
      >
        <q-card
          v-for="ch in current.channels"
          :key="ch.channel_id"
          flat
          bordered
          class="q-ma-xs q-pa-xs"
        >
          <q-card-section class="q-gutter-xs">
            <div class="row items-center justify-between">
              <div class="text-subtitle2">
                <span v-if="ch.kind === 'output'">OUT</span>
                <span v-else>{{ ch.channel_number }}</span>
              </div>
              <q-badge :color="ch.kind === 'output' ? 'secondary' : 'primary'">
                {{ ch.kind === 'output' ? t('channels.outputs') : t('channels.inputs') }}
              </q-badge>
            </div>
            <div class="row q-gutter-sm items-center">
              <div class="text-caption text-grey-7 col-4">
                {{ t('channels.fieldSource') }}
              </div>
              <div class="col">
                {{ ch.output_name || ch.source_label || '—' }}
              </div>
            </div>
            <div
              v-if="ch.device"
              class="row q-gutter-sm items-center"
            >
              <div class="text-caption text-grey-7 col-4">
                {{ t('channels.fieldDevice') }}
              </div>
              <div class="col">
                {{ ch.device }}
              </div>
            </div>
            <div
              v-if="ch.input_type"
              class="row q-gutter-sm items-center"
            >
              <div class="text-caption text-grey-7 col-4">
                {{ t('channels.type.label') }}
              </div>
              <div class="col">
                {{ t(`channels.type.${ch.input_type}`) }}
              </div>
            </div>
            <div class="row q-gutter-sm items-center">
              <div class="text-caption text-grey-7 col-4">
                48V
              </div>
              <div class="col">
                {{ ch.phantom_power ? '✓' : '' }}
              </div>
            </div>
            <div
              v-if="ch.direction"
              class="row q-gutter-sm items-center"
            >
              <div class="text-caption text-grey-7 col-4">
                {{ t('channels.patchPoint.direction') }}
              </div>
              <div class="col">
                {{ ch.direction === 'out' ? t('channels.patchPoint.directionOut') : ch.direction === 'in' ? t('channels.patchPoint.directionIn') : '' }}
              </div>
            </div>
            <div
              v-if="ch.connector"
              class="row q-gutter-sm items-center"
            >
              <div class="text-caption text-grey-7 col-4">
                {{ t('channels.patchPoint.connector') }}
              </div>
              <div class="col">
                {{ ch.connector }}
              </div>
            </div>
            <div
              v-if="ch.patch_label"
              class="row q-gutter-sm items-center"
            >
              <div class="text-caption text-grey-7 col-4">
                {{ t('channels.patchPoint.label') }}
              </div>
              <div class="col">
                {{ ch.patch_label }}
              </div>
            </div>
            <div
              v-if="stageByChannel.get(ch.channel_id)?.length"
              class="row q-gutter-sm items-center"
            >
              <div class="text-caption text-grey-7 col-4">
                {{ t('stagePlot.onStage') }}
              </div>
              <div class="col">
                {{ (stageByChannel.get(ch.channel_id) || []).join(', ') }}
              </div>
            </div>
            <div
              v-if="ch.notes"
              class="text-caption"
            >
              <MarkdownText :source="ch.notes" />
            </div>
            <div
              v-if="ch.point_notes"
              class="text-caption"
            >
              <MarkdownText :source="ch.point_notes" />
            </div>
          </q-card-section>
        </q-card>
      </q-list>
      <q-table
        v-else
        :rows="tableRows"
        :columns="columns"
        row-key="channel_id"
        dense
        flat
        bordered
        :pagination="{ rowsPerPage: 100 }"
        @row-click="(_, row) => openChannel(row)"
      >
        <template #body-cell-notes="cell">
          <q-td :props="cell">
            <TruncateText
              v-if="cell.value"
              :lines="2"
            >
              <MarkdownText :source="cell.value" />
            </TruncateText>
            <span
              v-else
              class="text-grey-6"
            >—</span>
          </q-td>
        </template>
        <template #body-cell-point_notes="cell">
          <q-td :props="cell">
            <TruncateText
              v-if="cell.value"
              :lines="2"
            >
              <MarkdownText :source="cell.value" />
            </TruncateText>
            <span
              v-else
              class="text-grey-6"
            >—</span>
          </q-td>
        </template>
        <template #body-cell-channel_number="cell">
          <q-td
            :props="cell"
            style="width: 50px"
          >
            <span v-if="cell.row.kind === 'output'">OUT</span>
            <span v-else>{{ cell.value }}</span>
          </q-td>
        </template>
        <template #body-cell-source_label="cell">
          <q-td :props="cell">
            <span v-if="cell.row.output_name">{{ cell.row.output_name }}</span>
            <span v-else>{{ cell.value }}</span>
          </q-td>
        </template>
      </q-table>
    </div>

    <q-dialog v-model="channelDialog">
      <q-card style="min-width: 320px; max-width: 520px">
        <q-card-section class="row items-center">
          <div class="col text-h6">
            <span v-if="activeChannel?.kind === 'output'">OUT</span>
            <span v-else>{{ activeChannel?.channel_number }}</span>
          </div>
          <q-btn
            v-close-popup
            flat
            round
            dense
            icon="close"
          />
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="row items-center">
            <div class="text-caption text-grey-7 col-4">
              {{ t('channels.fieldSource') }}
            </div>
            <div class="col">
              {{ activeChannel?.output_name || activeChannel?.source_label || '—' }}
            </div>
          </div>
          <div
            v-if="activeChannel?.device"
            class="row items-center"
          >
            <div class="text-caption text-grey-7 col-4">
              {{ t('channels.fieldDevice') }}
            </div>
            <div class="col">
              {{ activeChannel.device }}
            </div>
          </div>
          <div
            v-if="activeChannel?.input_type"
            class="row items-center"
          >
            <div class="text-caption text-grey-7 col-4">
              {{ t('channels.type.label') }}
            </div>
            <div class="col">
              {{ t(`channels.type.${activeChannel.input_type}`) }}
            </div>
          </div>
          <div class="row items-center">
            <div class="text-caption text-grey-7 col-4">
              48V
            </div>
            <div class="col">
              {{ activeChannel?.phantom_power ? '✓' : '' }}
            </div>
          </div>
          <div
            v-if="activeChannel?.connector || activeChannel?.point?.connector"
            class="row items-center"
          >
            <div class="text-caption text-grey-7 col-4">
              {{ t('channels.patchPoint.connector') }}
            </div>
            <div class="col">
              {{ activeChannel?.connector || activeChannel?.point?.connector }}
            </div>
          </div>
          <div
            v-if="activeChannel?.patch_label || activeChannel?.point?.patch_label"
            class="row items-center"
          >
            <div class="text-caption text-grey-7 col-4">
              {{ t('channels.patchPoint.label') }}
            </div>
            <div class="col">
              {{ activeChannel?.patch_label || activeChannel?.point?.patch_label }}
            </div>
          </div>
          <q-separator class="q-my-sm" />
          <div class="row items-center justify-between">
            <div class="text-subtitle2">
              {{ t('devices.title') }}
            </div>
            <q-btn
              v-close-popup
              flat
              dense
              icon="add"
              :label="t('devices.add')"
              @click="showCreateDevice = !showCreateDevice"
            />
          </div>
          <q-card
            v-if="showCreateDevice"
            flat
            bordered
            class="q-pa-xs q-mt-xs"
          >
            <div class="row q-gutter-sm items-end">
              <q-input
                v-model="newDevName"
                :label="t('devices.name')"
                dense
                class="col"
              />
              <q-select
                v-model="newDevType"
                :options="deviceTypeOptions"
                :label="t('devices.type')"
                emit-value
                map-options
                dense
                class="col"
              />
              <q-btn
                color="primary"
                dense
                :label="t('devices.createDevice')"
                :disable="!newDevName.trim()"
                @click="createDeviceInline"
              />
            </div>
          </q-card>
          <div
            v-for="p in activeChannelFull?.patch_points || []"
            :key="p.id"
            class="row q-gutter-xs items-center q-mt-xs"
          >
            <div class="col-5 text-caption ellipsis">
              {{ devicesStore.byId(p.device_id)?.name || t('devices.none') }}
            </div>
            <q-select
              :model-value="p.device_id"
              :options="deviceOptions"
              emit-value
              map-options
              dense
              class="col"
              @update:model-value="(v) => assignPoint(p, v)"
            />
          </div>
          <q-separator class="q-my-sm" />
          <div class="text-subtitle2">
            {{ t('stagePlot.onStage') }}
          </div>
          <div
            v-if="activeChannelStage"
            class="text-body2"
          >
            {{ activeChannelStage }}
          </div>
          <div
            v-else
            class="text-caption text-grey-7"
          >
            {{ t('devices.none') }}
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>
    <ReportGenerationDialog
      v-model="showPatchpointReport"
      :job-id="jobId"
      initial-type-key="audio.patch-sheet"
      :initial-patchpoint-id="current?.device_id || ''"
      patchpoint-locked
    />
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/boot/api'
import MarkdownText from '@/components/MarkdownText.vue'
import TruncateText from '@/components/TruncateText.vue'
import FlowTree from '@/components/FlowTree.vue'
import StagePlotMini from '@/components/StagePlotMini.vue'
import ReportGenerationDialog from '@/components/ReportGenerationDialog.vue'
import { useDevicesStore } from '@/stores/devices'
import { chainNodes } from '@/utils/patchFlow'
import { channelColor } from '@/utils/instrumentGroups'

const { t } = useI18n({ useScope: 'global' })
const route = useRoute()
const router = useRouter()
const jobId = route.params.jobId
const devicesStore = useDevicesStore()

const job = ref(null)
const sheets = ref([])
const lists = ref([])
const selected = ref(null)
const error = ref(null)
const plotElements = ref([])
const channelDialog = ref(false)
const showPatchpointReport = ref(false)
const activeChannel = ref(null)
const activeChannelId = ref(null)
const showCreateDevice = ref(false)
const newDevName = ref('')
const newDevType = ref('digital_stagebox')

const DEVICE_TYPES = [
  'digital_stagebox',
  'analog_stagebox',
  'mixer',
  'split',
  'network',
  'direct',
  'switcher',
  'router',
  'multiviewer',
  'other',
]
const deviceTypeOptions = DEVICE_TYPES.map((v) => ({
  value: v,
  label: t(`devices.types.${v}`),
}))
const deviceOptions = computed(() => devicesStore.options)
const channelColors = computed(() =>
  Object.fromEntries(
    lists.value.flatMap((list) =>
      (list.channels || []).map((channel) => [channel.id, channelColor(channel)]),
    ),
  ),
)

const typeKey = {
  mixer: 'typeMixer',
  analog_stagebox: 'typeAnalog',
  digital_stagebox: 'typeDigital',
  split: 'typeSplit',
  network: 'typeNetwork',
  direct: 'typeDirect',
  speaker: 'typeSpeaker',
  monitor: 'typeMonitor',
  recorder: 'typeRecorder',
  amp: 'typeAmp',
  stage: 'typeStage',
  other: 'typeOther',
}

const pointTypeLabel = (pt) => t(`channels.patchPoint.${typeKey[pt] || 'typeDirect'}`)

const sheetOptions = computed(() =>
  sheets.value.map((s) => ({
    label: `${s.name} · ${pointTypeLabel(s.point_type)}`,
    value: s.device_id,
  })),
)

const current = computed(
  () => sheets.value.find((s) => s.device_id === selected.value) || null,
)

const pointChannelMap = computed(() => {
  const m = {}
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) m[p.id] = ch.id
    }
  }
  return m
})
const pointNameMap = computed(() => {
  const m = {}
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) m[p.id] = devicesStore.byId(p.device_id)?.name || ''
    }
  }
  return m
})
const deviceChannelMap = computed(() => {
  const m = {}
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        if (p.device_id) (m[p.device_id] = m[p.device_id] || new Set()).add(ch.id)
      }
    }
  }
  return m
})

const currentHighlightIds = computed(() => {
  if (!current.value) return []
  const deviceSet = new Set()
  const channelSet = new Set()
  const pointSet = new Set()
  // Drive everything off the device assignments on the sheet's patch points —
  // no name matching.
  for (const row of current.value.channels || []) {
    const pid = row.point?.device_id
    if (pid) deviceSet.add(pid)
    if (row.channel_id) channelSet.add(row.channel_id)
    if (row.point?.id) pointSet.add(row.point.id)
  }
  const ids = []
  for (const el of plotElements.value) {
    if (
      (el.linked_device_id && deviceSet.has(el.linked_device_id)) ||
      (el.linked_channel_id && channelSet.has(el.linked_channel_id)) ||
      (el.linked_patch_point_id && pointSet.has(el.linked_patch_point_id))
    ) {
      ids.push(el.id)
    }
  }
  return ids
})

const stageByChannel = computed(() => {
  const m = new Map()
  const add = (channelId, text) => {
    const arr = m.get(channelId) || []
    arr.push(text)
    m.set(channelId, arr)
  }
  for (const el of plotElements.value) {
    const channelIds = new Set()
    if (el.linked_channel_id) channelIds.add(el.linked_channel_id)
    if (el.linked_patch_point_id && pointChannelMap.value[el.linked_patch_point_id]) {
      channelIds.add(pointChannelMap.value[el.linked_patch_point_id])
    }
    if (el.linked_device_id) {
      for (const c of deviceChannelMap.value[el.linked_device_id] || []) channelIds.add(c)
    }
    if (!channelIds.size) continue
    const ppName = el.linked_patch_point_id ? pointNameMap.value[el.linked_patch_point_id] : ''
    const text =
      ppName && el.linked_patch_point_id
        ? `${el.label || el.element_type} (${ppName})`
        : el.label || el.element_type
    for (const cid of channelIds) add(cid, text)
  }
  return m
})

const tableRows = computed(() =>
  (current.value?.channels || []).map((ch) => ({
    ...ch,
    stageLabel: (stageByChannel.value.get(ch.channel_id) || []).join(', '),
  })),
)

const modeLabel = (mode) =>
  mode === 'stereo'
    ? t('channels.outputModeStereo')
    : mode === 'other'
      ? t('channels.outputModeOther')
      : t('channels.outputModeMono')

const flowChains = computed(() => {
  if (!current.value) return []
  const deviceName = (id) => (id ? devicesStore.byId(id)?.name || '' : '')
  const fullById = (cid) => {
    for (const list of lists.value) {
      const c = (list.channels || []).find((x) => x.id === cid)
      if (c) return c
      const o = (list.outputs || []).find((x) => x.id === cid)
      if (o) return o
    }
    return null
  }
  const buildInputTree = (ch) => {
    const srcLabel = ch.source_label || `${t('channels.fieldChannelNumber')} ${ch.channel_number}`
    const srcMeta = [ch.device, ch.input_type ? t(`channels.type.${ch.input_type}`) : '']
      .filter(Boolean)
      .join(' · ')
    const root = {
      id: 'src',
      name: srcLabel,
      connector: ch.connector,
      patch_label: '',
      notes: ch.notes || '',
      meta: srcMeta,
      children: [],
    }
    let prev = root
    for (const p of ch.patch_points || []) {
      if (!p.device_id) continue
      const isDevice = !!p.device_id
      const node = {
        id: p.id,
        name: isDevice ? deviceName(p.device_id) : '',
        connector: p.connector,
        patch_label: p.patch_label,
        notes: p.notes,
        ptype: pointTypeLabel(p.point_type),
        device: isDevice ? deviceName(p.device_id) : '',
        children: [],
      }
      prev.children.push(node)
      prev = node
    }
    return root
  }
  const buildOutputTree = (out) => {
    const root = {
      id: 'bus',
      name: out.name,
      connector: out.connector,
      patch_label: '',
      notes: out.notes || '',
      meta: out.mode && out.mode !== 'mono' ? modeLabel(out.mode) : '',
      children: [],
    }
    const pts = (out.points || [])
      .filter((p) => p.device_id)
      .slice()
      .sort((a, b) => a.position - b.position)
    const byId = new Map()
    for (const p of pts) {
      const isDevice = !!p.device_id
      byId.set(p.id, {
        id: p.id,
        name: isDevice ? deviceName(p.device_id) : '',
        connector: p.connector,
        patch_label: p.patch_label,
        notes: p.notes,
        ptype: pointTypeLabel(p.point_type),
        connectorTag: p.bus_connector || '',
        device: isDevice ? deviceName(p.device_id) : '',
        children: [],
      })
    }
    for (const p of pts) {
      const node = byId.get(p.id)
      let parent = p.parent_id ? byId.get(p.parent_id) : null
      if (!parent) {
        if (p.parallel) {
          const idx = pts.indexOf(p)
          parent = idx > 0 ? byId.get(pts[idx - 1].id) : root
        } else {
          parent = root
        }
      }
      parent.children.push(node)
    }
    return root
  }
  const seen = new Set()
  const chains = []
  for (const row of current.value.channels || []) {
    if (seen.has(row.channel_id)) continue
    seen.add(row.channel_id)
    const full = fullById(row.channel_id)
    if (!full) continue
    if (row.kind === 'channel') {
      const tree = buildInputTree(full)
      chains.push({
        label: row.source_label || `${t('channels.fieldChannelNumber')} ${row.channel_number}`,
        kind: 'input',
        channelId: row.channel_id,
        tree,
        nodes: chainNodes(tree),
      })
    } else {
      chains.push({
        label: row.output_name || full.name,
        kind: 'output',
        channelId: row.channel_id,
        tree: buildOutputTree(full),
      })
    }
  }
  return chains
})

const columns = [
  { name: 'channel_number', label: '#', field: 'channel_number', align: 'left', style: 'width: 50px' },
  { name: 'source_label', label: t('channels.fieldSource'), field: 'source_label', align: 'left' },
  { name: 'device', label: t('channels.fieldDevice'), field: 'device', align: 'left' },
  {
    name: 'input_type',
    label: t('channels.type.label'),
    field: 'input_type',
    align: 'left',
    format: (v) => (v ? t(`channels.type.${v}`) : ''),
  },
  { name: 'phantom_power', label: '48V', field: 'phantom_power', align: 'center', format: (v) => (v ? '✓' : '') },
  {
    name: 'direction',
    label: t('channels.patchPoint.direction'),
    field: 'direction',
    align: 'left',
    style: 'width: 60px',
    format: (v) => (v === 'out' ? t('channels.patchPoint.directionOut') : t('channels.patchPoint.directionIn')),
  },
  { name: 'connector', label: t('channels.patchPoint.connector'), field: (row) => row.point.connector, align: 'left' },
  { name: 'patch_label', label: t('channels.patchPoint.label'), field: (row) => row.point.patch_label, align: 'left' },
  { name: 'notes', label: t('channels.fieldNotes'), field: 'notes', align: 'left' },
  { name: 'point_notes', label: t('channels.patchPoint.notes'), field: (row) => row.point.notes, align: 'left' },
  { name: 'stageLabel', label: t('stagePlot.onStage'), field: 'stageLabel', align: 'left' },
]

function printSheet() {
  window.print()
}

function openStagePlot() {
  if (!current.value) return
  router.push(
    `/jobs/${jobId}/stage-plot?highlight=sheet:${encodeURIComponent(current.value.name)}`,
  )
}

function highlightChannelOnStage(channelId) {
  if (!channelId) return
  router.push(`/jobs/${jobId}/stage-plot?highlight=channel:${channelId}`)
}

const activeChannelFull = computed(() => {
  if (!activeChannelId.value) return null
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      if (ch.id === activeChannelId.value) return ch
    }
  }
  return null
})

async function reloadData() {
  const [listsRes, plotRes, sheetsRes] = await Promise.all([
    api.get(`/jobs/${jobId}/channel-lists`),
    api.get(`/jobs/${jobId}/plot-elements`),
    api.get(`/jobs/${jobId}/patch-sheets`),
  ])
  lists.value = listsRes.data
  plotElements.value = plotRes.data
  sheets.value = sheetsRes.data
  await devicesStore.fetchDevices(jobId)
  if (!selected.value && sheets.value.length) {
    selected.value = sheets.value[0].device_id
  }
}

function openChannel(row) {
  activeChannel.value = row
  activeChannelId.value = row.channel_id
  channelDialog.value = true
}

async function assignPoint(p, deviceId) {
  await devicesStore.assignPatchPoint(jobId, p, deviceId)
  await reloadData()
}

async function createDeviceInline() {
  if (!newDevName.value.trim()) return
  await devicesStore.createDevice(jobId, {
    name: newDevName.value.trim(),
    device_type: newDevType.value,
  })
  newDevName.value = ''
  showCreateDevice.value = false
  await reloadData()
}

const activeChannelStage = computed(() =>
  activeChannel.value
    ? (stageByChannel.value.get(activeChannel.value.channel_id) || []).join(', ')
    : '',
)

onMounted(async () => {
  try {
    const jobReq = api.get(`/jobs/${jobId}`)
    const sheetsReq = api.get(`/jobs/${jobId}/patch-sheets`)
    const listsReq = api.get(`/jobs/${jobId}/channel-lists`)
    const plotReq = api.get(`/jobs/${jobId}/plot-elements`)
    const [jobRes, sheetsRes, listsRes, plotRes] = await Promise.all([
      jobReq,
      sheetsReq,
      listsReq,
      plotReq,
    ])
    job.value = jobRes.data
    sheets.value = sheetsRes.data
    lists.value = listsRes.data
    plotElements.value = plotRes.data || []
    devicesStore.fetchDevices(jobId)
    if (sheets.value.length) selected.value = sheets.value[0].device_id
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred')
  }
})
</script>

<style scoped>
.flow-stage-active {
  background: rgba(63, 135, 63, 0.12);
  border-radius: 8px;
  padding: 4px;
}
.flow-node {
  min-width: 96px;
}
.flow-linear-arrow {
  color: rgba(150, 150, 150, 0.7);
}
.flow-node-active {
  background: rgba(63, 135, 63, 0.18);
  border-color: var(--ec-accent, #35a853);
}
@media print {
  .no-print {
    display: none !important;
  }
}
</style>
