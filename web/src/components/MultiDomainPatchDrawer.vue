<template>
  <q-card
    flat
    bordered
    class="patch-drawer"
  >
    <q-tabs
      v-model="tab"
      dense
      align="left"
      active-color="primary"
      indicator-color="primary"
      narrow-indicator
    >
      <q-tab
        v-for="t_ in TABS"
        :key="t_.name"
        :name="t_.name"
        :label="`${t_.icon} ${t(t_.label)}`"
        no-caps
        :data-testid="`patch-tab-${t_.name}`"
      >
        <q-badge
          v-if="issueCount(t_.signal)"
          color="negative"
          floating
          :label="issueCount(t_.signal)"
        />
      </q-tab>
      <q-space />
      <q-btn
        flat
        dense
        round
        :icon="expanded ? 'expand_more' : 'expand_less'"
        :aria-label="t('workspace.patch')"
        @click="expanded = !expanded"
      />
    </q-tabs>
    <q-separator />

    <div v-show="expanded">
      <div
        v-if="!rows.length"
        class="q-pa-md text-grey-6"
      >
        {{ t('workspace.noConnections') }}
      </div>

      <q-virtual-scroll
        v-else-if="$q.screen.lt.sm"
        class="patch-scroll"
        :items="rows"
        :virtual-scroll-item-size="96"
      >
        <template #default="{ item }">
          <q-card
            :key="item.id"
            flat
            bordered
            class="q-ma-sm"
          >
            <q-card-section class="q-pa-sm">
              <div class="text-weight-medium">
                <a
                  class="device-link"
                  @click="graph.selectedDeviceId = item.srcId"
                >{{ item.from }}</a>
                <span class="text-grey-6">{{ item.fromPort }}</span> →
                <a
                  class="device-link"
                  @click="graph.selectedDeviceId = item.dstId"
                >{{ item.to }}</a>
                <span class="text-grey-6">{{ item.toPort }}</span>
              </div>
              <div class="text-caption">
                {{ item.channels }} ch
                <span v-if="item.phase"> · {{ item.phase }}</span>
                <span v-if="item.cableLabel"> · {{ item.cableLabel }}</span>
              </div>
              <div
                v-for="issue in issuesFor(item.id)"
                :key="issue.message"
                class="text-negative text-caption"
              >
                {{ issue.message }}
              </div>
            </q-card-section>
            <q-card-actions>
              <q-btn
                flat
                dense
                color="negative"
                icon="link_off"
                @click="remove(item)"
              />
            </q-card-actions>
          </q-card>
        </template>
      </q-virtual-scroll>

      <q-table
        v-else
        flat
        dense
        class="patch-scroll"
        virtual-scroll
        :virtual-scroll-item-size="40"
        :rows="rows"
        :columns="columns"
        row-key="id"
        :rows-per-page-options="[0]"
        hide-bottom
        data-testid="patch-table"
      >
        <template #body-cell-from="slot">
          <q-td :props="slot">
            <q-btn
              flat
              dense
              no-caps
              class="device-link"
              :label="slot.row.from"
              :data-testid="'patch-edit-from'"
              @click="graph.selectedDeviceId = slot.row.srcId"
            >
              <q-tooltip>{{ t('workspace.editDevice') }}</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #body-cell-to="slot">
          <q-td :props="slot">
            <q-btn
              flat
              dense
              no-caps
              class="device-link"
              :label="slot.row.to"
              :data-testid="'patch-edit-to'"
              @click="graph.selectedDeviceId = slot.row.dstId"
            >
              <q-tooltip>{{ t('workspace.editDevice') }}</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #body-cell-cableLabel="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.cableLabel"
              dense
              borderless
              @change="(v) => update(slot.row, { cable_label: v })"
            />
          </q-td>
        </template>
        <template #body-cell-phase="slot">
          <q-td :props="slot">
            <q-select
              v-if="slot.row.signal === 'power'"
              :model-value="slot.row.phase"
              dense
              borderless
              clearable
              :options="['L1', 'L2', 'L3']"
              @update:model-value="(v) => update(slot.row, { phase: v })"
            />
          </q-td>
        </template>
        <template #body-cell-issues="slot">
          <q-td :props="slot">
            <q-icon
              v-if="issuesFor(slot.row.id).length"
              name="warning"
              color="negative"
            >
              <q-tooltip>{{ issuesFor(slot.row.id).map((i) => i.message).join('; ') }}</q-tooltip>
            </q-icon>
            <q-icon
              v-else
              name="check"
              color="positive"
            />
          </q-td>
        </template>
        <template #body-cell-actions="slot">
          <q-td :props="slot">
            <q-btn
              flat
              dense
              round
              color="negative"
              icon="link_off"
              :aria-label="t('workspace.remove')"
              @click="remove(slot.row)"
            />
          </q-td>
        </template>
      </q-table>
    </div>
  </q-card>
</template>

<script setup>
import { isRevisionConflict } from '@/utils/graph';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { edgeRows } from '@/utils/workspace';

const props = defineProps({ jobId: { type: String, required: true } });

const TABS = [
  { name: 'audio', signal: 'audio', icon: '🎤', label: 'workspace.tabAudio' },
  { name: 'dmx', signal: 'dmx', icon: '💡', label: 'workspace.tabDmx' },
  { name: 'power', signal: 'power', icon: '🔌', label: 'workspace.tabPower' },
  { name: 'video', signal: 'video', icon: '📹', label: 'workspace.tabVideo' },
];

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const tab = ref('audio');
const expanded = ref(true);

const rows = computed(() =>
  edgeRows(
    graph.edges.filter((e) => e.signal === tab.value),
    graph.devices,
  ),
);

const columns = computed(() => [
  { name: 'from', label: t('workspace.colFrom'), field: 'from', align: 'left' },
  { name: 'fromPort', label: '', field: 'fromPort', align: 'left' },
  { name: 'to', label: t('workspace.colTo'), field: 'to', align: 'left' },
  { name: 'toPort', label: '', field: 'toPort', align: 'left' },
  { name: 'channels', label: t('workspace.colChannels'), field: 'channels', align: 'right' },
  ...(tab.value === 'power'
    ? [{ name: 'phase', label: t('workspace.colPhase'), field: 'phase', align: 'left' }]
    : []),
  { name: 'cableLabel', label: t('workspace.colCable'), field: 'cableLabel', align: 'left' },
  { name: 'issues', label: t('workspace.colIssues'), field: 'id', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

const issuesByEdge = computed(() => {
  const map = new Map();
  graph.issues.forEach((issue) => {
    if (!map.has(issue.edge_id)) map.set(issue.edge_id, []);
    map.get(issue.edge_id).push(issue);
  });
  return map;
});
const issuesFor = (id) => issuesByEdge.value.get(id) || [];
const issueCount = (signal) =>
  graph.edges.filter((e) => e.signal === signal && issuesFor(e.id).length).length;

async function update(row, changes) {
  try {
    await graph.updateEdge(props.jobId, row.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
    }
  }
}

async function remove(row) {
  try {
    await graph.deleteEdge(props.jobId, row.id);
  } catch (err) {
    if (!isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
    }
  }
}
</script>

<style scoped>
.device-link {
  cursor: pointer;
  text-decoration: underline dotted;
}
.patch-scroll {
  max-height: 260px;
}
</style>
