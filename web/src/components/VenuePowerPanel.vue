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

        <!-- Supplies: one row per supply root (mains + each generator), compared per source -->
        <div class="text-subtitle2 q-mb-xs">
          {{ t('workspace.venueSupplies') }}
        </div>
        <div
          v-for="supply in supplies"
          :key="supply.id"
          class="row items-center q-mb-xs q-px-sm q-py-xs"
          :class="supply.over ? 'text-negative' : 'text-grey-7'"
          data-testid="venue-supply"
          style="border-left: 3px solid currentColor"
        >
          <q-icon
            :name="kindIcon(groupById[supply.id]?.kind)"
            class="q-mr-xs"
          />
          <div class="col">
            <span class="text-weight-bold">{{ groupById[supply.id]?.name || '—' }}</span>
            <span class="text-caption q-ml-xs">{{ kindLabel(groupById[supply.id]?.kind) }}</span>
            <span class="q-ml-sm">
              {{ t('workspace.supplyLoad', { amps: formatAmps(supply.amps), rating: formatAmps(groupById[supply.id]?.rating_amps) }) }}
            </span>
            <span v-if="supply.over"> · {{ t('workspace.supplyOver') }}</span>
          </div>
        </div>
        <div class="row q-mb-sm q-gutter-xs">
          <q-btn
            v-if="!hasIncoming"
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
            icon="bolt"
            :label="t('workspace.addVenueGenerator')"
            data-testid="add-venue-generator"
            @click="addGenerator"
          >
            <q-tooltip>{{ t('workspace.addVenueGeneratorTooltip') }}</q-tooltip>
          </q-btn>
        </div>

        <!-- Supply tree: panels / breakouts / circuits, editable -->
        <div class="row items-center q-mb-xs">
          <div class="text-subtitle2 col">
            {{ t('workspace.venueGroups') }}
          </div>
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
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('workspace.addVenueBreakout')"
            data-testid="add-venue-breakout"
            @click="addBreakout()"
          >
            <q-tooltip>{{ t('workspace.addVenueBreakoutTooltip') }}</q-tooltip>
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
          <q-select
            :model-value="row.group.kind"
            class="col-6 col-sm-2"
            dense
            outlined
            emit-value
            map-options
            :options="kindOptions"
            :label="t('workspace.venueGroupKind')"
            data-testid="venue-group-kind"
            @update:model-value="(v) => changeKind(row.group, v)"
          />
          <q-input
            :model-value="row.group.name"
            class="col-6 col-sm-3"
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
            class="col-4 col-sm-1"
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
            class="col-4 col-sm-1"
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
          <q-toggle
            :model-value="row.group.temporary"
            class="col-6 col-sm-1"
            dense
            :label="t('workspace.temporary')"
            :hint="t('workspace.temporaryHint')"
            data-testid="venue-group-temporary"
            @update:model-value="() => toggleTemporary(row.group)"
          />
          <div class="col-12 col-sm-2 text-caption">
            {{ formatAmps(groupLoad(row.group.id)) }} A
            <span v-if="groupOver(row.group)"> · {{ t('workspace.venueGroupOver') }}</span>
          </div>
          <q-btn
            v-if="canHostCircuit(row.group.kind)"
            flat
            dense
            round
            color="primary"
            icon="power"
            data-testid="add-venue-circuit"
            :aria-label="t('workspace.addVenueCircuit')"
            @click="addCircuit(row.group.id)"
          >
            <q-tooltip>{{ t('workspace.addVenueCircuitTooltip', { name: row.group.name || '—' }) }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="canHostBoard(row.group.kind)"
            flat
            dense
            round
            color="primary"
            icon="subdirectory_arrow_right"
            data-testid="add-venue-subpanel"
            :aria-label="t('workspace.addVenueSubPanel')"
            @click="addPanel(row.group.id)"
          >
            <q-tooltip>{{ t('workspace.addVenueSubPanelTooltip', { name: row.group.name || '—' }) }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="canHostBoard(row.group.kind)"
            flat
            dense
            round
            color="primary"
            icon="hub"
            data-testid="add-venue-breakout-row"
            :aria-label="t('workspace.addVenueBreakout')"
            @click="addBreakout(row.group.id)"
          >
            <q-tooltip>{{ t('workspace.addVenueBreakoutTooltip') }}</q-tooltip>
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
            :options="circuitOptions"
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

// The power the venue offers: a tree of supply nodes (incoming mains, generators, panels,
// breakouts) holding fused circuits (kind 'group') whose outlets you plug gear into. Each node has
// a rating (its breaker) and outlets/groups belong to the venue so they exist for every job held
// there. A node is brought into a job's power tree when something is fed from it, so editing here
// is safe at any time. The panel is driven either by a job (resolving the venue from the job) or
// directly by a venueId (the venue Standard Base Rig editor).
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

const KIND_OPTIONS = [
  { value: 'incoming', label: 'Incoming (mains)' },
  { value: 'generator', label: 'Generator' },
  { value: 'panel', label: 'Panel' },
  { value: 'breakout', label: 'Breakout' },
  { value: 'group', label: 'Circuit' },
];
// i18n keys hold human labels per kind; reuse them so the UI and the kind select agree.
const kindOptions = computed(() => KIND_OPTIONS.map((k) => ({ value: k.value, label: kindLabel(k.value) })));
const KIND_ICONS = {
  incoming: 'electrical_services',
  generator: 'bolt',
  panel: 'view_module',
  breakout: 'hub',
  group: 'power',
};
function kindIcon(kind) {
  return KIND_ICONS[kind] || 'power';
}
function kindLabel(kind) {
  if (!kind) return '';
  const key = `kind${kind[0].toUpperCase()}${kind.slice(1)}`;
  return t(`workspace.${key}`);
}
// A node that can host a board/breakout underneath it (a supply root, a panel, or another breakout).
function canHostBoard(kind) {
  return ['incoming', 'generator', 'panel', 'breakout'].includes(kind);
}
// A node that can hold fused circuits.
function canHostCircuit(kind) {
  return ['panel', 'breakout'].includes(kind);
}

const groupById = computed(() => Object.fromEntries(groups.value.map((g) => [g.id, g])));
const hasIncoming = computed(() => groups.value.some((g) => g.kind === 'incoming'));

// Outlet group select only offers circuits (kind 'group'): outlets plug into fused circuits, never
// directly into a panel/breakout/supply.
const circuitOptions = computed(() =>
  groups.value
    .filter((g) => g.kind === 'group')
    .map((g) => ({ value: g.id, label: (g.temporary ? '⏱ ' : '') + (g.name || '—') })),
);

// The power tree, flattened with a depth so an arbitrarily nested hierarchy (incoming -> panel ->
// sub-panel -> ...) renders without a recursive component. Each node's actual load is looked up
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
// per-outlet, per-group and per-supply results by element id so the rows can look their own up.
const powerLoad = ref(null);
const loadById = computed(() => {
  const map = {};
  if (powerLoad.value) {
    for (const el of [...powerLoad.value.outlets, ...powerLoad.value.groups, ...(powerLoad.value.supplies || [])]) {
      map[el.id] = el;
    }
  }
  return map;
});
const supplies = computed(() => powerLoad.value?.supplies ?? []);
const totalLoad = computed(() => (powerLoad.value ? powerLoad.value.total_amps : 0));

function elementAmps(id) {
  return loadById.value[id]?.amps ?? 0;
}
function elementOver(id) {
  return Boolean(loadById.value[id]?.over);
}
// A node's load is the real draw beneath it: this is what its breaker rating is checked against.
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
// Eligible parents depend on the node's kind (a supply root has no parent; a circuit may only sit in
// a panel/breakout; a board may hang off a root, a panel, or another breakout). Self and descendants
// are excluded so the tree can never loop.
function parentOptions(group) {
  const excluded = new Set([group.id, ...descendantIds(group.id)]);
  let allowed;
  if (group.kind === 'incoming' || group.kind === 'generator') {
    allowed = [];
  } else if (group.kind === 'group') {
    allowed = groups.value.filter((g) => g.kind === 'panel' || g.kind === 'breakout');
  } else {
    allowed = groups.value.filter((g) => ['incoming', 'generator', 'panel', 'breakout'].includes(g.kind));
  }
  return [
    { value: null, label: t('workspace.venueGroupTop') },
    ...allowed
      .filter((g) => !excluded.has(g.id))
      .map((g) => ({ value: g.id, label: (g.temporary ? '⏱ ' : '') + (g.name || '—') })),
  ];
}

const caption = computed(() =>
  resolvedVenueId.value
    ? t('workspace.venuePowerCount', { groups: groups.value.length, outlets: outlets.value.length })
    : '',
);

const failed = (err) => $q.notify({ type: 'negative', message: apiErrorText(err) });

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

function countKind(kind) {
  return groups.value.filter((g) => g.kind === kind).length + 1;
}

const addIncoming = () =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      name: t('workspace.venueIncoming'),
      rating_amps: 63,
      phases: 3,
      kind: 'incoming',
    }),
  );
// A generator is a second supply root (no parent) and is temporary by default (hired kit).
const addGenerator = () =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      name: `${t('workspace.kindGenerator')} ${countKind('generator')}`,
      rating_amps: 16,
      phases: 1,
      kind: 'generator',
      temporary: true,
    }),
  );
// A panel without an explicit parent is nested under the incoming supply so the hierarchy reads
// incoming -> panel -> sub-panel; only a venue with no supply starts a top-level board.
const addPanel = (parentId = null) =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      name: `${t('workspace.venuePanel')} ${countKind('panel')}`,
      rating_amps: 16,
      phases: 1,
      kind: 'panel',
      parent_id: parentId ?? (hasIncoming.value ? groups.value.find((g) => g.kind === 'incoming').id : null),
    }),
  );
// A breakout is a temporary distro; default it under the incoming supply (or the node it was added on).
const addBreakout = (parentId = null) =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      name: `${t('workspace.kindBreakout')} ${countKind('breakout')}`,
      rating_amps: 16,
      phases: 1,
      kind: 'breakout',
      temporary: true,
      parent_id: parentId ?? (hasIncoming.value ? groups.value.find((g) => g.kind === 'incoming').id : null),
    }),
  );
// A circuit (fused group) lives inside a panel/breakout.
const addCircuit = (parentId) =>
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-groups`, {
      name: `${t('workspace.kindGroup')} ${countKind('group')}`,
      rating_amps: 16,
      phases: 1,
      kind: 'group',
      parent_id: parentId,
    }),
  );
const saveGroup = (group, changes) =>
  run(() => api.patch(`/venues/${resolvedVenueId.value}/power-groups/${group.id}`, changes));
// Reclassifying a node keeps the tree valid: a supply root cannot keep a parent, so clear it.
function changeKind(group, kind) {
  const changes = { kind };
  if ((kind === 'incoming' || kind === 'generator') && group.parent_id) {
    changes.parent_id = null;
  }
  saveGroup(group, changes);
}
function toggleTemporary(group) {
  saveGroup(group, { temporary: !group.temporary });
}
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
  run(() =>
    api.post(`/venues/${resolvedVenueId.value}/power-outlets`, {
      name: `${t('workspace.venueOutlet')} ${outlets.value.length + 1}`,
      connector: 'schuko',
      x_cm: 100,
      y_cm: 100,
    }),
  );
const saveOutlet = (outlet, changes) =>
  run(() => api.patch(`/venues/${resolvedVenueId.value}/power-outlets/${outlet.id}`, changes));
const removeOutlet = (outlet) =>
  confirmDelete(t('workspace.venueOutletDeleteWarn', { name: outlet.name || '—' }), () =>
    api.delete(`/venues/${resolvedVenueId.value}/power-outlets/${outlet.id}`),
  );

onMounted(load);
</script>
