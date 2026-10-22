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
        icon="print"
        :label="t('app.actions.print')"
        :disable="!selected"
        @click="printSheet"
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
          </div>
          <div class="flow-tree-wrap q-mt-xs">
            <div
              v-if="chain.kind === 'input'"
              class="row items-center flow-linear-row wrap"
            >
              <template
                v-for="(n, i) in [chain.tree, ...(chain.tree.children || [])]"
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
                </q-card>
                <q-icon
                  v-if="i < [chain.tree, ...(chain.tree.children || [])].length - 1"
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
      <q-table
        :rows="current.channels"
        :columns="columns"
        row-key="channel_id"
        dense
        flat
        bordered
        :pagination="{ rowsPerPage: 100 }"
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
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api } from 'boot/api'
import MarkdownText from 'components/MarkdownText.vue'
import TruncateText from 'components/TruncateText.vue'
import FlowTree from 'components/FlowTree.vue'

const { t } = useI18n({ useScope: 'global' })
const route = useRoute()
const router = useRouter()
const jobId = route.params.jobId

const job = ref(null)
const sheets = ref([])
const lists = ref([])
const selected = ref(null)
const error = ref(null)

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
    value: s.name,
  })),
)

const current = computed(
  () => sheets.value.find((s) => s.name === selected.value) || null,
)

const modeLabel = (mode) =>
  mode === 'stereo'
    ? t('channels.outputModeStereo')
    : mode === 'other'
      ? t('channels.outputModeOther')
      : t('channels.outputModeMono')

const flowChains = computed(() => {
  if (!current.value) return []
  const name = current.value.name
  const chains = []
  const buildInputTree = (ch) => {
    const srcLabel = ch.source_label || `${t('channels.fieldChannelNumber')} ${ch.channel_number}`
    const srcMeta = [ch.device, ch.input_type ? t(`channels.type.${ch.input_type}`) : ''].filter(Boolean).join(' · ')
    const root = { id: 'src', name: srcLabel, connector: ch.connector, patch_label: '', notes: ch.notes || '', meta: srcMeta, children: [] }
    let prev = root
    for (const p of ch.patch_points || []) {
      if (!p.name) continue
      const node = { id: p.id, name: p.name, connector: p.connector, patch_label: p.patch_label, notes: p.notes, ptype: pointTypeLabel(p.point_type), children: [] }
      prev.children.push(node)
      prev = node
    }
    return root
  }
  const buildOutputTree = (out) => {
    const root = { id: 'bus', name: out.name, connector: out.connector, patch_label: '', notes: out.notes || '', meta: out.mode && out.mode !== 'mono' ? modeLabel(out.mode) : '', children: [] }
    const pts = (out.points || []).filter((p) => p.name).slice().sort((a, b) => a.position - b.position)
    const byId = new Map()
    for (const p of pts) {
      byId.set(p.id, { id: p.id, name: p.name, connector: p.connector, patch_label: p.patch_label, notes: p.notes, ptype: pointTypeLabel(p.point_type), connectorTag: p.bus_connector || '', children: [] })
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
  for (const list of lists.value) {
    for (const ch of list.channels || []) {
      if ((ch.source_label && ch.source_label === name) || (ch.patch_points || []).some((p) => p.name === name)) {
        chains.push({ label: ch.source_label || `${t('channels.fieldChannelNumber')} ${ch.channel_number}`, kind: 'input', tree: buildInputTree(ch) })
      }
    }
    for (const out of list.outputs || []) {
      if (out.name === name || (out.points || []).some((p) => p.name === name)) {
        chains.push({ label: out.name, kind: 'output', tree: buildOutputTree(out) })
      }
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
]

function printSheet() {
  window.print()
}

onMounted(async () => {
  try {
    const jobReq = api.get(`/jobs/${jobId}`)
    const sheetsReq = api.get(`/jobs/${jobId}/patch-sheets`)
    const listsReq = api.get(`/jobs/${jobId}/channel-lists`)
    const [jobRes, sheetsRes, listsRes] = await Promise.all([jobReq, sheetsReq, listsReq])
    job.value = jobRes.data
    sheets.value = sheetsRes.data
    lists.value = listsRes.data
    if (sheets.value.length) selected.value = sheets.value[0].name
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
</style>
