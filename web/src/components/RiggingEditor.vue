<template>
  <div data-testid="rigging-editor">
    <div
      v-if="summary?.errors?.length"
      class="text-negative q-mb-md"
      data-testid="rigging-errors"
    >
      <div class="text-subtitle2">
        {{ t('workspace.errorsTitle') }}
      </div>
      <div
        v-for="e in summary.errors"
        :key="e"
      >
        {{ e }}
      </div>
    </div>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-5">
        <div class="row items-center q-mb-sm">
          <div class="text-subtitle1 col">
            {{ t('rigging.trusses') }}
          </div>
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('workspace.addTruss')"
            data-testid="add-truss"
            @click="addPoint"
          />
        </div>
        <div
          v-if="!points.length"
          class="text-grey-6"
        >
          {{ t('workspace.noTrusses2') }}
        </div>
        <q-card
          v-for="point in points"
          :key="point.id"
          flat
          bordered
          class="q-mb-sm"
          data-testid="truss-card"
        >
          <q-card-section class="q-pa-sm">
            <div class="row q-col-gutter-xs items-center">
              <q-input
                :model-value="point.name"
                class="col-12 col-sm-6"
                dense
                outlined
                :label="t('workspace.trussName')"
                data-testid="truss-name"
                @change="(v) => save(point, { name: v })"
              />
              <q-input
                :model-value="point.attributes.weight_capacity_kg"
                class="col-6 col-sm-3"
                dense
                outlined
                type="number"
                :label="t('workspace.capacity')"
                data-testid="truss-capacity"
                @change="(v) => saveAttr(point, 'weight_capacity_kg', v === '' ? null : Number(v))"
              />
              <q-input
                :model-value="point.attributes.trim_height_cm"
                class="col-6 col-sm-3"
                dense
                outlined
                type="number"
                :label="t('workspace.trimHeight')"
                @change="(v) => saveAttr(point, 'trim_height_cm', v === '' ? null : Number(v))"
              />
            </div>
            <div class="row items-center q-mt-xs">
              <q-linear-progress
                v-if="summaryPoint(point.id)?.percent != null"
                class="col"
                size="10px"
                :value="Math.min(1, summaryPoint(point.id).percent / 100)"
                :color="summaryPoint(point.id).over ? 'negative' : 'positive'"
              />
              <div
                class="text-caption q-ml-sm"
                :class="{ 'text-negative': summaryPoint(point.id)?.over }"
                data-testid="truss-load"
              >
                {{ t('workspace.loadKg') }}: {{ summaryPoint(point.id)?.load_kg ?? 0 }} kg
              </div>
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                @click="removeNode(point)"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-7">
        <div class="row items-center q-mb-sm">
          <div class="text-subtitle1 col">
            {{ t('rigging.tree') }}
          </div>
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('workspace.addPowerNode')"
            data-testid="add-power-node"
            @click="openCreate"
          />
        </div>
        <div
          v-if="!tree.length"
          class="text-grey-6"
        >
          {{ t('workspace.noPower') }}
        </div>
        <q-list
          v-else
          bordered
          separator
          data-testid="power-tree"
        >
          <q-item
            v-for="node in tree"
            :key="node.id"
            data-testid="power-node"
            :style="{ paddingLeft: `${16 + node.depth * 20}px` }"
          >
            <q-item-section>
              <q-item-label>
                <q-input
                  :model-value="node.name"
                  dense
                  borderless
                  data-testid="power-name"
                  @change="(v) => saveByNodeId(node.id, { name: v })"
                />
              </q-item-label>
              <q-item-label caption>
                {{ kindLabel(node.kind) }}
                <span v-if="node.feed_connector">· {{ connectorLabel(node.feed_connector) }}</span>
                <span v-if="graphNode(node.id)?.attributes?.outputs?.length">
                  · {{ outputsLabel(graphNode(node.id).attributes.outputs, connectorLabel) }}
                </span>
                <span v-if="node.percent != null">· {{ node.percent }}%</span>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-badge
                :color="loadStatusColor(node.status)"
                :label="node.status"
              />
            </q-item-section>
            <q-item-section side>
              <div class="row no-wrap">
                <q-btn
                  flat
                  dense
                  round
                  icon="tune"
                  :aria-label="t('workspace.editOutputs')"
                  data-testid="power-edit"
                  @click="openEdit(node)"
                />
                <q-btn
                  v-if="node.kind !== 'source'"
                  flat
                  dense
                  round
                  icon="call_merge"
                  :aria-label="t('workspace.addFeed')"
                  @click="openFeed(node)"
                />
                <q-btn
                  flat
                  dense
                  round
                  color="negative"
                  icon="delete"
                  :aria-label="t('workspace.remove')"
                  @click="removeById(node.id, node.name)"
                />
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </div>
    </div>

    <div class="text-subtitle1 q-mt-lg q-mb-sm">
      {{ t('workspace.loadsTitle') }}
    </div>
    <div
      v-if="!loads.length"
      class="text-grey-6"
    >
      {{ t('workspace.noLoads') }}
    </div>
    <q-list
      v-else
      bordered
      separator
      data-testid="load-list"
    >
      <q-item
        v-for="load in loads"
        :key="`${load.kind}:${load.load_id}`"
        data-testid="load-row"
      >
        <q-item-section class="col-12 col-sm-3">
          <q-item-label>{{ load.label }}</q-item-label>
          <q-item-label caption>
            {{ load.weight_kg ?? '–' }} kg · {{ load.power_w ?? '–' }} W
          </q-item-label>
        </q-item-section>
        <q-item-section>
          <div class="row q-col-gutter-xs">
            <q-select
              :model-value="load.rigging_point_id"
              class="col-12 col-sm-4"
              dense
              outlined
              clearable
              emit-value
              map-options
              :options="pointOptions"
              :label="t('workspace.loadHang')"
              data-testid="load-point"
              @update:model-value="(v) => assign(load, { rigging_point_id: v || null })"
            />
            <q-select
              :model-value="load.power_node_id"
              class="col-12 col-sm-4"
              dense
              outlined
              clearable
              emit-value
              map-options
              :options="nodeOptions"
              :label="t('workspace.loadPlug')"
              data-testid="load-node"
              @update:model-value="(v) => assign(load, { power_node_id: v || null, power_connector: v ? load.power_connector || connectorsOf(v)[0]?.value || '' : '' })"
            />
            <q-select
              :model-value="load.power_connector || null"
              class="col-12 col-sm-4"
              dense
              outlined
              emit-value
              map-options
              :disable="!load.power_node_id"
              :options="connectorsOf(load.power_node_id)"
              :label="t('workspace.loadConnector')"
              data-testid="load-connector"
              @update:model-value="(v) => assign(load, { power_connector: v })"
            />
          </div>
        </q-item-section>
        <q-item-section side>
          <q-badge
            :color="loadStatusColor(load.power_status)"
            :label="load.power_status"
          />
        </q-item-section>
      </q-item>
    </q-list>

    <q-dialog
      v-model="createOpen"
      :maximized="$q.screen.lt.sm"
    >
      <q-card style="width: 640px; max-width: 100vw">
        <q-card-section class="text-h6">
          {{ t('workspace.addPowerNode') }}
        </q-card-section>
        <q-card-section class="q-pt-none row q-col-gutter-sm">
          <q-input
            v-model="form.name"
            class="col-12 col-sm-6"
            dense
            outlined
            :label="t('workspace.trussName')"
            data-testid="new-power-name"
          />
          <q-select
            v-model="form.kind"
            class="col-12 col-sm-6"
            dense
            outlined
            emit-value
            map-options
            :options="kindOptions"
            :label="t('workspace.powerKind')"
            data-testid="new-power-kind"
          />
          <q-select
            v-if="form.kind !== 'source'"
            v-model="form.parent_id"
            class="col-12 col-sm-6"
            dense
            outlined
            emit-value
            map-options
            :options="nodeOptions"
            :label="t('workspace.powerParent')"
            data-testid="new-power-parent"
          />
          <q-select
            v-model="form.feed_connector"
            class="col-12 col-sm-6"
            dense
            outlined
            emit-value
            map-options
            :options="form.kind === 'source' ? allConnectors : connectorsOf(form.parent_id)"
            :label="t('workspace.powerFeed')"
            data-testid="new-power-feed"
          />
          <q-input
            v-model.number="form.rating_amps"
            class="col-6"
            dense
            outlined
            type="number"
            :label="t('workspace.powerRating')"
          />
          <q-select
            v-model="form.phase"
            class="col-6"
            dense
            outlined
            clearable
            emit-value
            :options="['L1', 'L2', 'L3']"
            :label="t('workspace.outputPhase')"
          />
          <div class="col-12">
            <OutputsField
              v-model="form.outputs"
              :connectors="allConnectors"
            />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            no-caps
            :label="t('common.cancel')"
          />
          <q-btn
            color="primary"
            no-caps
            :label="t('workspace.save')"
            data-testid="create-power-save"
            @click="createNode"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog
      v-model="editOpen"
      :maximized="$q.screen.lt.sm"
    >
      <q-card style="width: 640px; max-width: 100vw">
        <q-card-section class="text-h6">
          {{ editing?.name }}
        </q-card-section>
        <q-card-section class="q-pt-none row q-col-gutter-sm">
          <q-input
            v-model.number="editForm.rating_amps"
            class="col-6"
            dense
            outlined
            type="number"
            :label="t('workspace.powerRating')"
          />
          <q-toggle
            v-model="editForm.active"
            class="col-6"
            :label="t('workspace.powerActive')"
          />
          <div class="col-12">
            <OutputsField
              v-model="editForm.outputs"
              :connectors="allConnectors"
            />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            no-caps
            :label="t('common.cancel')"
          />
          <q-btn
            color="primary"
            no-caps
            :label="t('workspace.save')"
            data-testid="edit-power-save"
            @click="saveEdit"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="feedOpen">
      <q-card style="width: 480px; max-width: 100vw">
        <q-card-section class="text-h6">
          {{ t('workspace.addFeed') }}: {{ editing?.name }}
        </q-card-section>
        <q-card-section class="q-pt-none">
          <q-select
            v-model="feedForm.parent_id"
            dense
            outlined
            emit-value
            map-options
            class="q-mb-sm"
            :options="nodeOptions.filter((o) => o.value !== editing?.id)"
            :label="t('workspace.feedFrom')"
          />
          <q-select
            v-model="feedForm.feed_connector"
            dense
            outlined
            emit-value
            map-options
            :options="connectorsOf(feedForm.parent_id)"
            :label="t('workspace.powerFeed')"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            no-caps
            :label="t('common.cancel')"
          />
          <q-btn
            color="primary"
            no-caps
            :disable="!feedForm.parent_id || !feedForm.feed_connector"
            :label="t('workspace.save')"
            @click="addFeed"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import { useGraphStore } from '@/stores/graph';
import OutputsField from '@/components/OutputsField.vue';
import { loadStatusColor, outputsLabel, powerTreeRows } from '@/utils/workspace';

const props = defineProps({ jobId: { type: String, required: true } });
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const summary = ref(null);
const catalog = ref([]);
const createOpen = ref(false);
const editOpen = ref(false);
const feedOpen = ref(false);
const editing = ref(null);
const form = reactive({});
const editForm = reactive({ rating_amps: null, active: true, outputs: [] });
const feedForm = reactive({ parent_id: null, feed_connector: '' });

const points = computed(() =>
  graph.devices.filter((d) => d.kind === 'rigging_point').sort((a, b) => a.position - b.position),
);
const tree = computed(() => powerTreeRows(summary.value?.nodes || []));
const loads = computed(() => summary.value?.loads || []);
const kindOptions = ['source', 'distro', 'breakout'].map((v) => ({
  value: v,
  label: t(`workspace.kind${v[0].toUpperCase()}${v.slice(1)}`),
}));
const kindLabel = (kind) => kindOptions.find((o) => o.value === kind)?.label || kind;
const allConnectors = computed(() => catalog.value.map((c) => ({ value: c.key, label: c.label })));
const connectorLabel = (key) => catalog.value.find((c) => c.key === key)?.label || key;
const pointOptions = computed(() => points.value.map((p) => ({ value: p.id, label: p.name })));
const nodeOptions = computed(() => tree.value.map((n) => ({ value: n.id, label: n.name })));
const graphNode = (id) => graph.devices.find((d) => d.id === id);
const summaryPoint = (id) => (summary.value?.points || []).find((p) => p.id === id);

function connectorsOf(nodeId) {
  const outputs = graphNode(nodeId)?.attributes?.outputs || [];
  return [...new Set(outputs.map((o) => o.connector))].map((value) => ({
    value,
    label: connectorLabel(value),
  }));
}

const failed = (err) =>
  $q.notify({
    type: 'negative',
    message: err.response?.data?.detail?.message || err.response?.data?.detail || err.message,
  });

async function refresh() {
  try {
    summary.value = await graph.fetchRiggingSummary(props.jobId);
  } catch (err) {
    failed(err);
  }
}

onMounted(async () => {
  try {
    catalog.value = (await api.get('/power-connectors')).data;
  } catch (err) {
    failed(err);
  }
  await refresh();
});
watch(() => [graph.devices.length, graph.edges.length], refresh);

async function save(node, changes) {
  try {
    await graph.updateDevice(props.jobId, node.id, changes);
    await refresh();
  } catch (err) {
    if (err.response?.status !== 409) failed(err);
  }
}
const saveAttr = (node, key, value) => save(node, { attributes: { [key]: value } });
const saveByNodeId = (id, changes) => save(graphNode(id) || { id }, changes);

async function addPoint() {
  try {
    await graph.createRiggingPoint(props.jobId, { name: `${t('rigging.trusses')} ${points.value.length + 1}` });
    await refresh();
  } catch (err) {
    failed(err);
  }
}

function openCreate() {
  Object.assign(form, {
    name: '',
    kind: tree.value.length ? 'distro' : 'source',
    parent_id: null,
    feed_connector: '',
    phase: null,
    rating_amps: null,
    outputs: [],
  });
  createOpen.value = true;
}

async function createNode() {
  try {
    await graph.createPowerNode(props.jobId, {
      name: form.name,
      kind: form.kind,
      parent_id: form.kind === 'source' ? null : form.parent_id,
      feed_connector: form.feed_connector || '',
      phase: form.phase || null,
      rating_amps: form.rating_amps || null,
      outputs: form.outputs,
    });
    createOpen.value = false;
    await refresh();
  } catch (err) {
    failed(err);
  }
}

function openEdit(node) {
  editing.value = node;
  const attrs = graphNode(node.id)?.attributes || {};
  Object.assign(editForm, {
    rating_amps: attrs.rating_amps ?? null,
    active: attrs.active ?? true,
    outputs: (attrs.outputs || []).map((o) => ({ ...o })),
  });
  editOpen.value = true;
}

async function saveEdit() {
  const node = graphNode(editing.value.id);
  if (!node) return;
  await save(node, {
    attributes: {
      rating_amps: editForm.rating_amps || null,
      active: editForm.active,
      outputs: editForm.outputs,
    },
  });
  editOpen.value = false;
}

function openFeed(node) {
  editing.value = node;
  Object.assign(feedForm, { parent_id: null, feed_connector: '' });
  feedOpen.value = true;
}

async function addFeed() {
  try {
    await graph.addPowerFeed(props.jobId, editing.value.id, { ...feedForm });
    feedOpen.value = false;
    await refresh();
  } catch (err) {
    failed(err);
  }
}

async function assign(load, changes) {
  try {
    await graph.assignLoad(props.jobId, load.id, changes);
    await refresh();
  } catch (err) {
    failed(err);
    await refresh();
  }
}

function removeNode(node) {
  removeById(node.id, node.name);
}

function removeById(id, name) {
  $q.dialog({ title: t('workspace.remove'), message: name, cancel: true, persistent: true }).onOk(
    async () => {
      try {
        await graph.deleteDevice(props.jobId, id);
        await refresh();
      } catch (err) {
        if (err.response?.status !== 409) failed(err);
        else $q.notify({ type: 'negative', message: err.response?.data?.detail?.message || err.response?.data?.detail });
      }
    },
  );
}
</script>
