<template>
  <q-expansion-item
    v-model="open"
    icon="electrical_services"
    :label="t('workspace.venuePower')"
    :caption="caption"
    class="q-mb-md venue-power"
    header-class="bg-grey-9 text-white"
    data-testid="venue-power"
  >
    <q-card flat>
      <q-card-section v-if="!resolvedVenueId">
        <div class="text-grey-6">
          {{ t('workspace.venuePowerNoVenue') }}
        </div>
      </q-card-section>
      <q-card-section v-else>
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t('workspace.venuePowerHint') }}
        </div>

        <div
          v-if="incomingGroup"
          class="row items-center q-mb-sm q-px-sm q-py-xs"
          :class="incomingOver ? 'text-negative' : 'text-grey-7'"
          style="border-left: 3px solid currentColor"
        >
          <q-icon
            name="electrical_services"
            class="q-mr-xs"
          />
          <div>
            <span class="text-subtitle2">{{ t('workspace.venueIncoming') }}:</span>
            <span class="text-weight-bold">
              {{ formatAmps(totalLoad) }} / {{ formatAmps(incomingGroup.rating_amps) }} A
            </span>
            <span v-if="incomingOver"> · {{ t('workspace.venueGroupOver') }}</span>
          </div>
        </div>

        <div class="row items-center q-mb-xs">
          <div class="text-subtitle2 col">
            {{ t('workspace.venueGroups') }}
          </div>
          <q-btn
            v-if="!incomingGroup"
            flat
            no-caps
            icon="electrical_services"
            :label="t('workspace.addVenueIncoming')"
            data-testid="add-venue-incoming"
            @click="addIncoming"
          />
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('workspace.addVenuePanel')"
            data-testid="add-venue-group"
            @click="addPanel()"
          >
            <q-tooltip>{{ t('workspace.addVenuePanelTooltip') }}</q-tooltip>
          </q-btn>
        </div>
        <div
          v-for="row in groupRows"
          :key="row.group.id"
          class="row q-col-gutter-xs items-center q-mb-xs venue-group"
          :class="groupOver(row.group) ? 'text-negative' : ''"
          :style="{ marginLeft: row.depth * 18 + 'px' }"
          data-testid="venue-group"
        >
          <q-input
            :model-value="row.group.name"
            class="col-12 col-sm-4"
            dense
            outlined
            :label="t('workspace.trussName')"
            data-testid="venue-group-name"
            @change="(v) => saveGroup(row.group, { name: v })"
          />
          <q-input
            :model-value="row.group.rating_amps"
            class="col-6 col-sm-2"
            dense
            outlined
            type="number"
            :label="t('workspace.powerRating')"
            data-testid="venue-group-rating"
            @change="(v) => saveGroup(row.group, { rating_amps: v === '' ? null : Number(v) })"
          />
          <q-select
            :model-value="row.group.phases"
            class="col-4 col-sm-2"
            dense
            outlined
            emit-value
            :options="[1, 3]"
            :label="t('workspace.venueGroupPhases')"
            @update:model-value="(v) => saveGroup(row.group, { phases: v })"
          />
          <q-select
            v-if="row.group.phases === 1"
            :model-value="row.group.phase || 'L1'"
            class="col-4 col-sm-2"
            dense
            outlined
            emit-value
            :options="['L1', 'L2', 'L3']"
            :label="t('workspace.outputPhase')"
            data-testid="venue-group-phase"
            @update:model-value="(v) => saveGroup(row.group, { phase: v })"
          />
          <q-select
            :model-value="row.group.parent_id"
            class="col-6 col-sm-3"
            dense
            outlined
            clearable
            emit-value
            map-options
            :options="parentOptions(row.group)"
            :label="t('workspace.venueGroupParent')"
            data-testid="venue-group-parent"
            @update:model-value="(v) => saveGroup(row.group, { parent_id: v || null })"
          />
          <div class="col-12 col-sm-2 text-caption">
            {{ formatAmps(groupLoad(row.group.id)) }} A
            <span v-if="groupOver(row.group)"> · {{ t('workspace.venueGroupOver') }}</span>
          </div>
          <q-btn
            flat
            dense
            round
            color="primary"
            icon="subdirectory_arrow_right"
            :aria-label="t('workspace.addVenueSubPanel')"
            @click="addPanel(row.group.id)"
          >
            <q-tooltip>{{ t('workspace.addVenueSubPanelTooltip', { name: row.group.name || '—' }) }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="removeGroup(row.group)"
          />
        </div>

        <div class="row items-center q-mt-md q-mb-xs">
          <div class="text-subtitle2 col">
            {{ t('workspace.venueOutlets') }}
          </div>
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('workspace.addVenueOutlet')"
            data-testid="add-venue-outlet"
            @click="addOutlet"
          />
        </div>
        <div
          v-for="outlet in outlets"
          :key="outlet.id"
          class="row q-col-gutter-xs items-center q-mb-xs"
          data-testid="venue-outlet"
        >
          <q-input
            :model-value="outlet.name"
            class="col-12 col-sm-3"
            dense
            outlined
            :label="t('workspace.trussName')"
            data-testid="venue-outlet-name"
            @change="(v) => saveOutlet(outlet, { name: v })"
          />
          <ConnectorSelect
            :model-value="outlet.connector"
            power
            class="col-6 col-sm-3"
            :label="t('workspace.outputConnector')"
            data-testid="venue-outlet-connector"
            @update:model-value="(v) => saveOutlet(outlet, { connector: v })"
          />
          <q-select
            :model-value="outlet.group_id"
            class="col-6 col-sm-3"
            dense
            outlined
            clearable
            emit-value
            map-options
            :options="groupOptions"
            :label="t('workspace.venueGroup')"
            data-testid="venue-outlet-group"
            @update:model-value="(v) => saveOutlet(outlet, { group_id: v || null })"
          />
          <q-input
            :model-value="outlet.rating_amps"
            class="col-4 col-sm-2"
            dense
            outlined
            type="number"
            :label="t('workspace.powerRating')"
            @change="(v) => saveOutlet(outlet, { rating_amps: v === '' ? null : Number(v) })"
          />
          <div
            class="col-4 col-sm-2 self-center text-caption"
            :class="outletOver(outlet.id) ? 'text-negative' : 'text-grey-7'"
          >
            {{ formatAmps(outletLoad(outlet.id)) }} A
            <span v-if="outletOver(outlet.id)"> · {{ t('workspace.venueGroupOver') }}</span>
          </div>
          <q-input
            :model-value="outlet.x_cm"
            class="col-4 col-sm-2"
            dense
            outlined
            type="number"
            :label="t('workspace.outletX')"
            data-testid="venue-outlet-x"
            @change="(v) => saveOutlet(outlet, { x_cm: v === '' ? null : Number(v) })"
          />
          <q-input
            :model-value="outlet.y_cm"
            class="col-4 col-sm-2"
            dense
            outlined
            type="number"
            :label="t('workspace.outletY')"
            data-testid="venue-outlet-y"
            @change="(v) => saveOutlet(outlet, { y_cm: v === '' ? null : Number(v) })"
          />
          <q-btn
            v-if="outlet.x_cm == null || outlet.y_cm == null"
            flat
            dense
            no-caps
            icon="add_location_alt"
            :label="t('workspace.placeOutlet')"
            data-testid="venue-outlet-place"
            @click="saveOutlet(outlet, { x_cm: 100, y_cm: 100 })"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="removeOutlet(outlet)"
          />
        </div>
      </q-card-section>
    </q-card>
  </q-expansion-item>
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import ConnectorSelect from '@/components/ConnectorSelect.vue';

// The power the venue offers: circuits (groups, each with a rating shared by its outlets) and
// the outlets on them. Outlets and groups belong to the venue, so they are there for every job
// held in it. A group or outlet is brought into a job's power tree when something is fed from it
// (see POST /graph/venue-power/outlets/{id}/source), so editing them here is safe at any time.
// The panel can be driven either by a job (it resolves the venue from the job) or directly by a
// venueId, which is what the venue Standard Base Rig editor uses.
const props = defineProps({
  jobId: { type: String, default: null },
  venueId: { type: String, default: null },
});
const emit = defineEmits(['changed']);
const { t } = useI18n();
const $q = useQuasar();
const open = ref(false);
const resolvedVenueId = ref(null);
const groups = ref([]);
const outlets = ref([]);

const groupOptions = computed(() => {
  const ids = new Set(groups.value.map((g) => g.id));
  const depthOf = {};
  const depth = (g, d) => {
    depthOf[g.id] = d;
    groups.value.filter((c) => c.parent_id === g.id).forEach((c) => depth(c, d + 1));
  };
  groups.value.filter((g) => !g.parent_id || !ids.has(g.parent_id)).forEach((g) => depth(g, 0));
  return groups.value.map((g) => ({
    value: g.id,
    label: (g.is_incoming ? '⚡ ' : '    '.repeat(depthOf[g.id] || 0)) + (g.name || '—'),
  }));
});

// The power tree, flattened with a depth so an arbitrarily nested hierarchy (incoming -> panel ->
// sub-panel -> ...) renders without a recursive component. Each group's actual load is looked up
// from the server-side, device-driven summary (groupLoad/groupOver) rather than summed locally.
const groupRows = computed(() => {
  const ids = new Set(groups.value.map((g) => g.id));
  const rows = [];
  const walk = (parentId, depth) => {
    groups.value
      .filter((g) => (g.parent_id || null) === (parentId || null))
      .forEach((g) => {
        rows.push({ group: g, depth });
        walk(g.id, depth + 1);
      });
  };
  groups.value
    .filter((g) => !g.parent_id || !ids.has(g.parent_id))
    .forEach((g) => walk(g.parent_id || null, 0));
  return rows;
});

// The actual load (amps) on each supply element, computed server-side from the watts of the devices
// plugged into the outlets/groups. This is the real draw, not the sum of each socket's capacity, so
// a panel with several sockets is not flagged overloaded just for existing. `loadById` indexes the
// per-outlet, per-group and incoming results by element id so the rows can look their own up.
const powerLoad = ref(null);
const loadById = computed(() => {
  const map = {};
  if (powerLoad.value) {
    for (const el of [...powerLoad.value.outlets, ...powerLoad.value.groups]) {
      map[el.id] = el;
    }
    if (powerLoad.value.incoming) map[powerLoad.value.incoming.id] = powerLoad.value.incoming;
  }
  return map;
});
const totalLoad = computed(() => (powerLoad.value ? powerLoad.value.total_amps : 0));
const incomingGroup = computed(() => groups.value.find((g) => g.is_incoming) || null);
const incomingOver = computed(() => Boolean(powerLoad.value?.incoming?.over));

function elementAmps(id) {
  return loadById.value[id]?.amps ?? 0;
}
function elementOver(id) {
  return Boolean(loadById.value[id]?.over);
}
// A panel's load is the real draw beneath it: this is what its breaker rating is checked against.
function groupLoad(id) {
  return elementAmps(id);
}
function groupOver(group) {
  return elementOver(group.id);
}
function outletLoad(id) {
  return elementAmps(id);
}
function outletOver(id) {
  return elementOver(id);
}
function formatAmps(v) {
  if (v == null) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}
function descendantIds(groupId, acc = new Set()) {
  groups.value
    .filter((g) => g.parent_id === groupId)
    .forEach((c) => {
      acc.add(c.id);
      descendantIds(c.id, acc);
    });
  return acc;
}
// A group's eligible parents are everything except itself and its own descendants (that would loop).
function parentOptions(group) {
  const excluded = new Set([group.id, ...descendantIds(group.id)]);
  return [
    { value: null, label: t('workspace.venueGroupTop') },
    ...groups.value
      .filter((g) => !excluded.has(g.id))
      .map((g) => ({ value: g.id, label: (g.is_incoming ? '⚡ ' : '') + (g.name || '—') })),
  ];
}

const caption = computed(() =>
  resolvedVenueId.value ? t('workspace.venuePowerCount', { groups: groups.value.length, outlets: outlets.value.length }) : '',
);

const failed = (err) =>
  $q.notify({ type: 'negative', message: apiErrorText(err) });

async function load() {
  try {
    // Resolve the venue: directly when venueId is given, otherwise from the job.
    if (props.venueId) {
      resolvedVenueId.value = props.venueId;
    } else {
      const job = (await api.get(`/jobs/${props.jobId}`)).data;
      resolvedVenueId.value = job.venue_id || null;
    }
    if (!resolvedVenueId.value) return;
    const [groupsRes, outletsRes, loadRes] = await Promise.all([
      api.get(`/venues/${resolvedVenueId.value}/power-groups`),
      api.get(`/venues/${resolvedVenueId.value}/power-outlets`),
      api.get(
        props.jobId
          ? `/jobs/${props.jobId}/power-load`
          : `/venues/${resolvedVenueId.value}/power-load`,
      ),
    ]);
    groups.value = groupsRes.data;
    outlets.value = outletsRes.data;
    powerLoad.value = loadRes.data;
  } catch (err) {
    failed(err);
  }
}

async function run(call) {
  try {
    await call();
    await load();
    emit('changed');
  } catch (err) {
    failed(err);
    await load();
  }
}

const addIncoming = () =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      name: t('workspace.venueIncoming'),
      rating_amps: 63,
      phases: 3,
      is_incoming: true,
    }),
  );
const addPanel = (parentId = null) =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      // A panel without an explicit parent is nested under the incoming supply so the hierarchy
      // reads incoming -> panel -> sub-panel; only a venue with no supply starts a top-level board.
      name: `${t('workspace.venuePanel')} ${groups.value.length + 1}`,
      rating_amps: 16,
      phases: 1,
      parent_id: parentId ?? incomingGroup.value?.id ?? null,
    }),
  );
const saveGroup = (group, changes) => run(() => api.patch(`/venues/${resolvedVenueId.value}/power-groups/${group.id}`, changes));
// A group or outlet belongs to the venue, so deleting one changes every job held there: it is
// confirmed first and says what it detaches.
function confirmDelete(message, call) {
  $q.dialog({ title: t('workspace.remove'), message, cancel: true, persistent: true }).onOk(() => run(call));
}
const removeGroup = (group) =>
  confirmDelete(
    t('workspace.venueGroupDeleteWarn', {
      name: group.name || '—',
      n: outlets.value.filter((o) => o.group_id === group.id).length,
    }),
    () => api.delete(`/venues/${resolvedVenueId.value}/power-groups/${group.id}`),
  );
const addOutlet = () =>
  run(() => api.post(`/venues/${resolvedVenueId.value}/power-outlets`, { name: `${t('workspace.venueOutlet')} ${outlets.value.length + 1}`, connector: 'schuko', x_cm: 100, y_cm: 100 }));
const saveOutlet = (outlet, changes) => run(() => api.patch(`/venues/${resolvedVenueId.value}/power-outlets/${outlet.id}`, changes));
const removeOutlet = (outlet) =>
  confirmDelete(t('workspace.venueOutletDeleteWarn', { name: outlet.name || '—' }), () =>
    api.delete(`/venues/${resolvedVenueId.value}/power-outlets/${outlet.id}`),
  );

onMounted(load);
</script>
