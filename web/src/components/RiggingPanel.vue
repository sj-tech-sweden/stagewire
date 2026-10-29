<template>
  <div class="q-pa-md">
    <div class="text-h6 q-mb-md">
      {{ t('rigging.title') }}
    </div>

    <div
      v-if="error"
      class="text-negative q-mb-md"
    >
      {{ error }}
    </div>
    <div
      v-if="loading"
      class="q-my-md"
    >
      <q-spinner color="primary" />
    </div>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-6">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('rigging.trusses') }}
            </div>
            <div
              v-if="!summary?.points?.length"
              class="text-grey-7 q-mb-sm"
            >
              {{ t('rigging.noTrusses') }}
            </div>
            <div
              v-for="point in summary?.points || []"
              :key="point.id"
              class="q-mb-md"
            >
              <div class="row items-center">
                <div class="col text-body2">
                  {{ point.name || '—' }}
                  <span class="text-caption text-grey-7">
                    · {{ point.load_kg }} / {{ point.weight_capacity_kg ?? '—' }} kg
                  </span>
                </div>
                <q-badge
                  v-if="point.over"
                  color="negative"
                >
                  {{ t('rigging.over') }}
                </q-badge>
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('app.actions.delete')"
                  @click="removePoint(point)"
                />
              </div>
              <q-linear-progress
                v-if="point.percent !== null"
                :value="Math.min(point.percent / 100, 1)"
                :color="point.over ? 'negative' : 'positive'"
                size="8px"
                class="q-mt-xs"
              />
            </div>
            <div class="row q-gutter-sm items-end">
              <q-input
                v-model="newPoint.name"
                :label="t('rigging.trussName')"
                dense
                class="col"
              />
              <q-input
                v-model.number="newPoint.weight_capacity_kg"
                type="number"
                min="0"
                :label="t('rigging.capacity')"
                dense
                style="max-width: 120px"
              />
              <q-btn
                color="primary"
                icon="add"
                :label="t('rigging.addTruss')"
                :disable="!newPoint.name.trim()"
                @click="addPoint"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-6">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-xs">
              {{ t('rigging.tree') }}
            </div>
            <div class="text-caption text-grey-7 q-mb-sm">
              {{ t('rigging.treeHint') }}
            </div>
            <div
              v-if="!nodes.length"
              class="text-grey-7 q-mb-sm"
            >
              {{ t('rigging.noNodes') }}
            </div>
            <div
              v-for="node in nodeRows"
              :key="node.id"
              :style="{ paddingLeft: `${node.depth * 18}px` }"
              class="q-mb-sm"
            >
              <div class="row items-center">
                <div class="col text-body2">
                  {{ node.name }}
                  <span class="text-caption text-grey-7">
                    · {{ kindLabel(node.kind) }} · {{ connectorLabel(node.feed_connector) }}
                    <span v-if="node.phase"> · {{ node.phase }}</span>
                  </span>
                </div>
                <q-badge
                  :color="statusColor(nodeStatus(node.id))"
                  class="q-mr-xs"
                >
                  {{ statusLabel(nodeStatus(node.id)) }}
                </q-badge>
                <q-btn
                  flat
                  dense
                  round
                  icon="edit"
                  :aria-label="t('app.actions.edit')"
                  @click="openEditNode(node)"
                />
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('app.actions.delete')"
                  @click="removeNode(node)"
                />
              </div>
              <div class="text-caption text-grey-7">
                <template v-if="nodeEval(node.id)">
                  {{ nodeEval(node.id).amps.L1 }} / {{ nodeEval(node.id).amps.L2 }} /
                  {{ nodeEval(node.id).amps.L3 }} A
                  <span v-if="nodeEval(node.id).percent !== null">
                    · {{ nodeEval(node.id).percent }}% of {{ nodeEval(node.id).rating_amps }} A
                  </span>
                </template>
                <span v-if="node.outputs.length">
                  · {{ t('rigging.outputs') }}:
                  {{ node.outputs.map((o) => `${o.count}× ${connectorLabel(o.connector)}${o.phase ? ' ' + o.phase : ''}`).join(', ') }}
                </span>
              </div>
            </div>

            <q-separator class="q-my-sm" />
            <div class="text-subtitle2 q-mb-xs">
              {{ t('rigging.addNode') }}
            </div>
            <div class="row q-gutter-xs items-end">
              <q-input
                v-model="newNode.name"
                :label="t('rigging.nodeName')"
                dense
                class="col"
              />
              <q-select
                v-model="newNode.kind"
                :options="kindOptions"
                emit-value
                map-options
                dense
                style="min-width: 110px"
                :label="t('rigging.nodeKind')"
                :hint="kindHint(newNode.kind)"
              />
            </div>
            <div class="row q-gutter-xs items-end q-mt-xs">
              <q-select
                v-model="newNode.parent_id"
                :options="parentOptions"
                emit-value
                map-options
                clearable
                dense
                class="col"
                :label="t('rigging.fedFrom')"
                :disable="newNode.kind === 'source'"
              />
              <q-select
                v-model="newNode.feed_connector"
                :options="connectorOptions"
                emit-value
                map-options
                dense
                class="col"
                :label="t('rigging.feedConnector')"
              />
            </div>
            <div class="row q-gutter-xs items-end q-mt-xs">
              <q-select
                v-if="newNode.kind === 'source'"
                v-model="newNode.venue_outlet_id"
                :options="outletOptions"
                emit-value
                map-options
                clearable
                dense
                class="col"
                :label="t('rigging.venueOutlet')"
                :hint="t('rigging.venueOutletHint')"
              />
              <q-input
                v-model.number="newNode.rating_amps"
                type="number"
                min="0"
                dense
                style="max-width: 110px"
                :label="t('rigging.rating')"
              />
            </div>
            <div class="row q-gutter-xs items-end q-mt-xs">
              <q-select
                v-model="newNode.device_id"
                :options="deviceOptions"
                emit-value
                map-options
                clearable
                dense
                class="col"
                :label="t('rigging.standsFor')"
                :hint="t('rigging.standsForHint')"
              />
            </div>
            <div class="row q-gutter-xs items-end q-mt-xs">
              <q-select
                v-model="newOutput.connector"
                :options="connectorOptions"
                emit-value
                map-options
                dense
                class="col"
                :label="t('rigging.outputConnector')"
              />
              <q-input
                v-model.number="newOutput.count"
                type="number"
                min="1"
                dense
                style="max-width: 90px"
                :label="t('rigging.count')"
              />
              <q-select
                v-model="newOutput.phase"
                :options="phaseChoices"
                emit-value
                map-options
                dense
                style="min-width: 110px"
                :label="t('rigging.phase')"
              />
              <q-btn
                flat
                dense
                icon="add"
                :label="t('rigging.addOutput')"
                :disable="!newOutput.connector"
                @click="addOutput"
              />
            </div>
            <div
              v-if="newNode.outputs.length"
              class="text-caption q-mt-xs"
            >
              {{ newNode.outputs.map((o) => `${o.count}× ${connectorLabel(o.connector)}${o.phase ? ' ' + o.phase : ''}`).join(', ') }}
              <q-btn
                flat
                dense
                size="sm"
                icon="clear"
                @click="newNode.outputs = []"
              />
            </div>
            <q-btn
              class="q-mt-sm"
              color="primary"
              icon="add"
              :label="t('rigging.addNodeButton')"
              :disable="!newNode.name.trim() || !newNode.feed_connector"
              @click="addNode"
            />

            <div
              v-if="summary?.errors?.length"
              class="q-mt-md text-negative text-caption"
            >
              <div
                v-for="(e, i) in summary.errors"
                :key="i"
              >
                {{ e }}
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-xs">
              {{ t('rigging.loads') }}
            </div>
            <div class="text-caption text-grey-7 q-mb-sm">
              {{ t('rigging.loadsHint') }}
            </div>
            <div
              v-if="!loads.length"
              class="text-grey-7"
            >
              {{ t('rigging.noLoads') }}
            </div>
            <q-list
              v-else-if="$q.screen.lt.sm"
              separator
            >
              <q-item
                v-for="load in loads"
                :key="load.kind + load.id"
                class="q-px-none"
              >
                <q-item-section>
                  <div class="text-body2">
                    {{ load.label }}
                  </div>
                  <div class="text-caption text-grey-7">
                    {{ load.weight_kg ?? '—' }} kg · {{ load.power_w ?? '—' }} W
                  </div>
                  <q-select
                    :model-value="load.rigging_point_id"
                    :options="pointOptions"
                    :label="t('rigging.truss')"
                    emit-value
                    map-options
                    clearable
                    dense
                    @update:model-value="(v) => assign(load, { rigging_point_id: v })"
                  />
                  <q-select
                    :model-value="load.power_node_id"
                    :options="nodeOptions"
                    :label="t('rigging.node')"
                    emit-value
                    map-options
                    clearable
                    dense
                    @update:model-value="(v) => assign(load, { power_node_id: v, power_connector: null })"
                  />
                  <q-select
                    :model-value="load.power_connector || null"
                    :options="outputOptionsFor(load.power_node_id)"
                    :label="t('rigging.connector')"
                    emit-value
                    map-options
                    clearable
                    dense
                    :disable="!load.power_node_id"
                    @update:model-value="(v) => assign(load, { power_connector: v || '' })"
                  />
                </q-item-section>
              </q-item>
            </q-list>
            <q-markup-table
              v-else
              flat
              dense
            >
              <thead>
                <tr>
                  <th class="text-left">
                    {{ t('rigging.colLoad') }}
                  </th>
                  <th class="text-right">
                    {{ t('rigging.colWeight') }}
                  </th>
                  <th class="text-right">
                    {{ t('rigging.colPower') }}
                  </th>
                  <th class="text-left">
                    {{ t('rigging.truss') }}
                  </th>
                  <th class="text-left">
                    {{ t('rigging.node') }}
                  </th>
                  <th class="text-left">
                    {{ t('rigging.connector') }}
                  </th>
                  <th class="text-left">
                    {{ t('rigging.colPowerStatus') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="load in loads"
                  :key="load.kind + load.id"
                >
                  <td>{{ load.label }}</td>
                  <td class="text-right">
                    {{ load.weight_kg ?? '—' }}
                  </td>
                  <td class="text-right">
                    {{ load.power_w ?? '—' }}
                  </td>
                  <td>
                    <q-select
                      :model-value="load.rigging_point_id"
                      :options="pointOptions"
                      emit-value
                      map-options
                      clearable
                      dense
                      borderless
                      style="min-width: 150px"
                      @update:model-value="(v) => assign(load, { rigging_point_id: v })"
                    />
                  </td>
                  <td>
                    <q-select
                      :model-value="load.power_node_id"
                      :options="nodeOptions"
                      emit-value
                      map-options
                      clearable
                      dense
                      borderless
                      style="min-width: 160px"
                      @update:model-value="(v) => assign(load, { power_node_id: v, power_connector: null })"
                    />
                  </td>
                  <td>
                    <q-select
                      :model-value="load.power_connector || null"
                      :options="outputOptionsFor(load.power_node_id)"
                      emit-value
                      map-options
                      clearable
                      dense
                      borderless
                      :disable="!load.power_node_id"
                      style="min-width: 150px"
                      @update:model-value="(v) => assign(load, { power_connector: v || '' })"
                    />
                  </td>
                  <td>
                    <q-badge
                      :color="statusColor(load.power_status)"
                      class="q-mr-xs"
                    >
                      {{ statusLabel(load.power_status) }}
                    </q-badge>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
            <div
              v-if="summary?.unassigned_weight?.length"
              class="text-caption q-mt-sm"
            >
              {{ t('rigging.unassignedWeight') }}: {{ summary.unassigned_weight.join(', ') }}
            </div>
            <div
              v-if="summary?.unassigned_power?.length"
              class="text-caption"
            >
              {{ t('rigging.unassignedPower') }}: {{ summary.unassigned_power.join(', ') }}
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 340px; max-width: 600px; width: 100%">
        <q-card-section class="text-h6">
          {{ t('rigging.editNode') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model="editForm.name"
            :label="t('rigging.nodeName')"
            dense
          />
          <div class="row q-gutter-sm">
            <q-select
              v-model="editForm.kind"
              :options="kindOptions"
              emit-value
              map-options
              dense
              class="col"
              :label="t('rigging.nodeKind')"
              :hint="kindHint(editForm.kind)"
            />
            <q-select
              v-model="editForm.active"
              :options="activeOptions"
              emit-value
              map-options
              dense
              class="col"
              :label="t('rigging.state')"
            />
          </div>
          <q-select
            v-model="editForm.parent_id"
            :options="editParentOptions"
            emit-value
            map-options
            clearable
            dense
            :disable="editForm.kind === 'source'"
            :label="t('rigging.fedFrom')"
          />
          <div class="text-subtitle2 q-mt-sm">
            {{ t('rigging.extraFeeds') }}
          </div>
          <div
            v-if="editingNode && editingNode.feeds && editingNode.feeds.length"
            class="q-gutter-y-xs"
          >
            <div
              v-for="f in editingNode.feeds"
              :key="f.id"
              class="row items-center q-gutter-xs"
            >
              <div class="col text-body2">
                {{ nodeName(f.parent_id) }} · {{ connectorLabel(f.feed_connector) }}
              </div>
              <q-btn
                flat
                dense
                round
                icon="delete"
                color="negative"
                :aria-label="t('app.actions.delete')"
                @click="removeFeed(f.id)"
              />
            </div>
          </div>
          <div class="text-caption text-grey-7 q-mb-xs">
            {{ t('rigging.extraFeedsHint') }}
          </div>
          <div class="row q-gutter-xs items-end">
            <q-select
              v-model="newFeed.parent_id"
              :options="feedParentOptions"
              emit-value
              map-options
              clearable
              dense
              class="col"
              :label="t('rigging.fedFrom')"
            />
            <q-select
              v-model="newFeed.feed_connector"
              :options="connectorOptions"
              emit-value
              map-options
              dense
              class="col"
              :label="t('rigging.feedConnector')"
            />
            <q-btn
              flat
              dense
              icon="add"
              :label="t('rigging.addFeed')"
              :disable="!newFeed.parent_id || !newFeed.feed_connector"
              @click="addFeed"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-select
              v-model="editForm.feed_connector"
              :options="connectorOptions"
              emit-value
              map-options
              dense
              class="col"
              :label="t('rigging.feedConnector')"
            />
            <q-input
              v-model.number="editForm.rating_amps"
              type="number"
              min="0"
              dense
              style="max-width: 120px"
              :label="t('rigging.rating')"
            />
          </div>
          <q-select
            v-model="editForm.device_id"
            :options="deviceOptions"
            emit-value
            map-options
            clearable
            dense
            :label="t('rigging.standsFor')"
          />
          <q-select
            v-if="editForm.kind === 'source'"
            v-model="editForm.venue_outlet_id"
            :options="outletOptions"
            emit-value
            map-options
            clearable
            dense
            :label="t('rigging.venueOutlet')"
          />
          <div class="text-subtitle2 q-mt-sm">
            {{ t('rigging.outputs') }}
          </div>
          <div
            v-for="(o, idx) in editForm.outputs"
            :key="idx"
            class="row items-center q-gutter-xs"
          >
            <div class="col text-body2">
              {{ o.count }}× {{ connectorLabel(o.connector) }}{{ o.phase ? ' ' + o.phase : '' }}
            </div>
            <q-btn
              flat
              dense
              round
              icon="delete"
              color="negative"
              :aria-label="t('app.actions.delete')"
              @click="editForm.outputs.splice(idx, 1)"
            />
          </div>
          <div class="row q-gutter-xs items-end">
            <q-select
              v-model="editOutput.connector"
              :options="connectorOptions"
              emit-value
              map-options
              dense
              class="col"
              :label="t('rigging.outputConnector')"
            />
            <q-input
              v-model.number="editOutput.count"
              type="number"
              min="1"
              dense
              style="max-width: 90px"
              :label="t('rigging.count')"
            />
            <q-select
              v-model="editOutput.phase"
              :options="phaseChoices"
              emit-value
              map-options
              dense
              style="min-width: 110px"
              :label="t('rigging.phase')"
            />
            <q-btn
              flat
              dense
              icon="add"
              :label="t('rigging.addOutput')"
              :disable="!editOutput.connector"
              @click="addEditOutput"
            />
          </div>
          <q-input
            v-model="editForm.notes"
            type="textarea"
            autogrow
            dense
            :label="t('lights.notes')"
          />
        </q-card-section>
        <q-card-actions align="between">
          <q-btn
            flat
            color="negative"
            icon="delete"
            :label="t('app.actions.delete')"
            @click="deleteEditingNode"
          />
          <div>
            <q-btn
              v-close-popup
              flat
              :label="t('app.actions.cancel')"
            />
            <q-btn
              color="primary"
              :label="t('app.actions.save')"
              :disable="!editForm.name.trim()"
              @click="saveEditNode"
            />
          </div>
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';

const props = defineProps({
  jobId: { type: String, required: true },
});
const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const jobId = props.jobId;

const summary = ref(null);
const loads = ref([]);
const nodes = ref([]);
const devices = ref([]);
const catalog = ref([]);
const outlets = ref([]);
const loading = ref(false);
const error = ref('');

const newPoint = reactive({ name: '', weight_capacity_kg: null });
const newNode = reactive({
  name: '',
  kind: 'distro',
  parent_id: null,
  feed_connector: null,
  device_id: null,
  venue_outlet_id: null,
  rating_amps: null,
  outputs: [],
});
const newOutput = reactive({ connector: null, count: 1, phase: null });

const editDialog = ref(false);
const editingId = ref(null);
const editForm = reactive({
  name: '',
  kind: 'distro',
  parent_id: null,
  feed_connector: null,
  phase: null,
  outputs: [],
  rating_amps: null,
  active: true,
  device_id: null,
  venue_outlet_id: null,
  notes: '',
});
const editOutput = reactive({ connector: null, count: 1, phase: null });
const activeOptions = [
  { value: true, label: t('rigging.stateOn') },
  { value: false, label: t('rigging.stateOff') },
];
// A node cannot hang from itself or from anything below it. A node is "below" another when it is
// fed by it through the primary parent or through any merged feed.
const editParentOptions = computed(() => {
  const blocked = new Set([editingId.value]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const n of nodes.value) {
      const parents = [n.parent_id, ...((n.feeds || []).map((f) => f.parent_id))];
      if (parents.some((p) => p && blocked.has(p)) && !blocked.has(n.id)) {
        blocked.add(n.id);
        grew = true;
      }
    }
  }
  return nodes.value
    .filter((n) => !blocked.has(n.id))
    .map((n) => ({ value: n.id, label: n.name || '—' }));
});

// The node currently being edited (reactive to reloads after a feed change).
const editingNode = computed(() => nodes.value.find((n) => n.id === editingId.value) || null);

// Extra (merged) feeds: parents the node is already fed by are not offered again.
const feedParentOptions = computed(() => {
  const excluded = new Set([editingId.value]);
  if (editingNode.value?.parent_id) excluded.add(editingNode.value.parent_id);
  for (const f of editingNode.value?.feeds || []) excluded.add(f.parent_id);
  return editParentOptions.value.filter((o) => !excluded.has(o.value));
});

const newFeed = reactive({ parent_id: null, feed_connector: null });

function nodeName(id) {
  return nodes.value.find((n) => n.id === id)?.name || '—';
}

async function addFeed() {
  if (!editingId.value || !newFeed.parent_id || !newFeed.feed_connector) return;
  await run(async () => {
    await api.post(`/jobs/${jobId}/power-nodes/${editingId.value}/feeds`, {
      parent_id: newFeed.parent_id,
      feed_connector: newFeed.feed_connector,
    });
    newFeed.parent_id = null;
    newFeed.feed_connector = null;
  });
}

async function removeFeed(feedId) {
  if (!editingId.value) return;
  await run(async () => {
    await api.delete(`/jobs/${jobId}/power-nodes/${editingId.value}/feeds/${feedId}`);
  });
}

const kindOptions = [
  { value: 'source', label: t('rigging.kindSource') },
  { value: 'distro', label: t('rigging.kindDistro') },
  { value: 'breakout', label: t('rigging.kindBreakout') },
];
const phaseChoices = [
  { value: null, label: t('rigging.phaseShared') },
  { value: 'L1', label: 'L1' },
  { value: 'L2', label: 'L2' },
  { value: 'L3', label: 'L3' },
];
const deviceOptions = computed(() =>
  devices.value.map((d) => ({ value: d.id, label: d.name || '—' })),
);
const connectorOptions = computed(() =>
  catalog.value.map((c) => ({ value: c.key, label: c.label })),
);
const outletOptions = computed(() =>
  outlets.value.map((o) => ({ value: o.id, label: `${o.name || '—'} · ${connectorLabel(o.connector)}` })),
);
const pointOptions = computed(() =>
  (summary.value?.points || []).map((p) => ({ value: p.id, label: p.name || '—' })),
);
const nodeOptions = computed(() => nodes.value.map((n) => ({ value: n.id, label: n.name || '—' })));
const parentOptions = computed(() =>
  nodes.value.map((n) => ({ value: n.id, label: n.name || '—' })),
);

// Nodes in tree order, with their depth, so the tree reads top to bottom.
const nodeRows = computed(() => {
  const byParent = new Map();
  for (const n of nodes.value) {
    const key = n.parent_id || null;
    if (!byParent.has(key)) byParent.set(key, []);
    byParent.get(key).push(n);
  }
  const rows = [];
  const walk = (parent, depth) => {
    for (const n of byParent.get(parent) || []) {
      rows.push({ ...n, depth });
      walk(n.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
});

function outputOptionsFor(nodeId) {
  const node = nodes.value.find((n) => n.id === nodeId);
  return (node?.outputs || []).map((o) => ({
    value: o.connector,
    label: `${connectorLabel(o.connector)} · ${o.count}×${o.phase ? ' ' + o.phase : ''}`,
  }));
}

function connectorLabel(key) {
  return catalog.value.find((c) => c.key === key)?.label || key || '—';
}

function kindLabel(kind) {
  return t(`rigging.kind${kind.charAt(0).toUpperCase()}${kind.slice(1)}`);
}

function nodeEval(id) {
  return (summary.value?.nodes || []).find((n) => n.id === id) || null;
}

function nodeStatus(id) {
  return nodeEval(id)?.status || 'ok';
}

function statusLabel(status) {
  return t(`rigging.status.${status}`);
}

function statusColor(status) {
  return { ok: 'positive', warn: 'warning', over: 'negative', unpowered: 'grey-7', unrated: 'warning' }[status] || 'grey-7';
}

async function fetchAll() {
  loading.value = true;
  error.value = '';
  try {
    const [summaryRes, nodesRes, catalogRes, outletsRes, devicesRes] = await Promise.all([
      api.get(`/jobs/${jobId}/rigging/summary`),
      api.get(`/jobs/${jobId}/power-nodes`),
      api.get('/power-connectors'),
      api.get(`/jobs/${jobId}/power-outlets`),
      api.get(`/jobs/${jobId}/devices`),
    ]);
    devices.value = devicesRes.data;
    summary.value = summaryRes.data;
    loads.value = summaryRes.data.loads;
    nodes.value = nodesRes.data;
    catalog.value = catalogRes.data;
    outlets.value = outletsRes.data;
  } catch (err) {
    error.value = err.response?.data?.detail || t('common.errorOccurred');
  } finally {
    loading.value = false;
  }
}

async function run(request, message) {
  try {
    await request();
    await fetchAll();
    if (message) $q.notify({ type: 'positive', message });
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('common.errorOccurred') });
  }
}

function addPoint() {
  const body = {
    name: newPoint.name.trim(),
    weight_capacity_kg: newPoint.weight_capacity_kg || null,
  };
  run(async () => {
    await api.post(`/jobs/${jobId}/rigging-points`, body);
    newPoint.name = '';
    newPoint.weight_capacity_kg = null;
  });
}

function removePoint(point) {
  run(() => api.delete(`/jobs/${jobId}/rigging-points/${point.id}`));
}

function addOutput() {
  newNode.outputs.push({
    connector: newOutput.connector,
    count: newOutput.count || 1,
    phase: newOutput.phase || null,
  });
  newOutput.connector = null;
  newOutput.count = 1;
  newOutput.phase = null;
}

function addNode() {
  const body = {
    name: newNode.name.trim(),
    kind: newNode.kind,
    parent_id: newNode.kind === 'source' ? null : newNode.parent_id,
    feed_connector: newNode.feed_connector,
    venue_outlet_id: newNode.venue_outlet_id || null,
    device_id: newNode.device_id || null,
    rating_amps: newNode.rating_amps || null,
    outputs: newNode.outputs,
  };
  run(async () => {
    await api.post(`/jobs/${jobId}/power-nodes`, body);
    newNode.name = '';
    newNode.parent_id = null;
    newNode.feed_connector = null;
    newNode.venue_outlet_id = null;
    newNode.device_id = null;
    newNode.rating_amps = null;
    newNode.outputs = [];
  });
}

function kindHint(kind) {
  const key = { source: 'kindHintSource', distro: 'kindHintDistro', breakout: 'kindHintBreakout' }[kind];
  return key ? `${t(`rigging.${key}`)} ${t('rigging.kindHintNote')}` : '';
}

function openEditNode(node) {
  editingId.value = node.id;
  Object.assign(editForm, {
    name: node.name || '',
    kind: node.kind,
    parent_id: node.parent_id || null,
    feed_connector: node.feed_connector || null,
    phase: node.phase || null,
    outputs: (node.outputs || []).map((o) => ({ connector: o.connector, count: o.count, phase: o.phase || null })),
    rating_amps: node.rating_amps ?? null,
    active: node.active !== false,
    device_id: node.device_id || null,
    venue_outlet_id: node.venue_outlet_id || null,
    notes: node.notes || '',
  });
  editOutput.connector = null;
  editOutput.count = 1;
  editOutput.phase = null;
  editDialog.value = true;
}

function addEditOutput() {
  editForm.outputs.push({
    connector: editOutput.connector,
    count: editOutput.count || 1,
    phase: editOutput.phase || null,
  });
  editOutput.connector = null;
  editOutput.count = 1;
  editOutput.phase = null;
}

function saveEditNode() {
  const id = editingId.value;
  const body = {
    name: editForm.name.trim(),
    kind: editForm.kind,
    parent_id: editForm.kind === 'source' ? null : editForm.parent_id,
    feed_connector: editForm.feed_connector || '',
    phase: editForm.phase || null,
    outputs: editForm.outputs,
    rating_amps: editForm.rating_amps || null,
    active: editForm.active,
    device_id: editForm.device_id || null,
    venue_outlet_id: editForm.venue_outlet_id || null,
    notes: editForm.notes,
  };
  run(async () => {
    await api.patch(`/jobs/${jobId}/power-nodes/${id}`, body);
    editDialog.value = false;
  }, t('rigging.nodeSaved'));
}

function deleteEditingNode() {
  const node = nodes.value.find((n) => n.id === editingId.value);
  if (!node) return;
  editDialog.value = false;
  removeNode(node);
}

function removeNode(node) {
  run(() => api.delete(`/jobs/${jobId}/power-nodes/${node.id}`));
}

function assign(load, change) {
  run(() => api.patch(`/jobs/${jobId}/rigging/loads/${load.kind}/${load.id}`, change));
}

onMounted(fetchAll);
</script>
