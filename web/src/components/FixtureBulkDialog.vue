<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="bulk-card">
      <q-card-section class="text-h6">
        {{ t('workspace.bulkFixtures') }}
      </q-card-section>
      <q-card-section class="q-pt-none">
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t('workspace.bulkHint') }}
        </div>
        <div
          v-for="(row, i) in rows"
          :key="i"
          class="row q-col-gutter-xs items-center q-mb-sm"
          data-testid="bulk-row"
        >
          <q-select
            v-model="row.fixture_type"
            class="col-12 col-sm-4"
            dense
            outlined
            use-input
            hide-selected
            fill-input
            new-value-mode="add-unique"
            input-debounce="0"
            :options="typeOptions"
            :label="t('lights.fixtureType')"
            data-testid="bulk-type"
            @filter="filterTypes"
            @update:model-value="() => (row.channel_mode = '')"
          />
          <q-select
            v-model="row.channel_mode"
            class="col-6 col-sm-3"
            dense
            outlined
            use-input
            hide-selected
            fill-input
            new-value-mode="add-unique"
            input-debounce="0"
            :options="modeNames(row.fixture_type)"
            :label="t('lights.mode')"
            data-testid="bulk-mode"
            @update:model-value="(v) => pickMode(row, v)"
          />
          <q-input
            v-model.number="row.footprint"
            class="col-3 col-sm-2"
            dense
            outlined
            type="number"
            min="1"
            max="512"
            :label="t('lights.footprint')"
            data-testid="bulk-footprint"
          />
          <q-input
            v-model.number="row.quantity"
            class="col-3 col-sm-2"
            dense
            outlined
            type="number"
            min="1"
            max="200"
            :label="t('workspace.bulkQuantity')"
            data-testid="bulk-quantity"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="close"
            :disable="rows.length === 1"
            :aria-label="t('workspace.remove')"
            @click="rows.splice(i, 1)"
          />
          <q-input
            v-model="row.label"
            class="col-12 col-sm-6"
            dense
            outlined
            :label="t('workspace.bulkLabel')"
          />
          <q-input
            v-model="row.location"
            class="col-6 col-sm-3"
            dense
            outlined
            :label="t('lights.location')"
          />
          <q-input
            v-model="row.gel"
            class="col-6 col-sm-3"
            dense
            outlined
            :label="t('lights.gel')"
          />
        </div>
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('workspace.bulkAddKind')"
          data-testid="bulk-add-kind"
          @click="rows.push(blank())"
        />

        <div class="row q-col-gutter-sm q-mt-md">
          <q-input
            v-model.number="universe"
            class="col-4"
            dense
            outlined
            type="number"
            min="1"
            :label="t('lights.universe')"
            data-testid="bulk-universe"
          />
          <q-input
            v-model="startAddress"
            class="col-4"
            dense
            outlined
            type="number"
            min="1"
            max="512"
            :label="t('workspace.bulkStart')"
            :hint="t('workspace.bulkStartHint')"
            data-testid="bulk-start"
          />
          <q-input
            v-model.number="spacing"
            class="col-4"
            dense
            outlined
            type="number"
            min="0"
            :label="t('workspace.bulkSpacing')"
            :disable="startAddress === '' || startAddress == null"
          />
        </div>
        <div
          class="text-caption q-mt-md"
          data-testid="bulk-total"
        >
          {{ t('workspace.bulkTotal', { n: total }) }}
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
          :disable="!total || busy"
          :loading="busy"
          :label="t('workspace.bulkCreate', { n: total })"
          data-testid="bulk-create"
          @click="create"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useGraphStore } from '@/stores/graph';
import { useFixtureLibraryStore } from '@/stores/fixtureLibrary';
import { modesForType } from '@/utils/workspace';

// Adds several kinds of fixture at once. Each row is a library type (a new name is created in
// the library, like when adding one fixture), an optional mode (which sets the footprint), a
// label prefix and a quantity. The server lays them out from the start address, or on the first
// free addresses when none is given (see POST /graph/fixtures/bulk).
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // Either a job or a venue owns the library; venue takes precedence so a venue mount never
  // silently hits the job endpoints.
  jobId: { type: String, default: null },
  venueId: { type: String, default: null },
});
const context = computed(() =>
  props.venueId ? { kind: 'venue', id: props.venueId } : { kind: 'job', id: props.jobId },
);
const emit = defineEmits(['update:modelValue', 'created', 'error']);
const { t } = useI18n();
const graph = useGraphStore();
const library = useFixtureLibraryStore();
const blank = () => ({
  fixture_type: '',
  channel_mode: '',
  footprint: 1,
  quantity: 1,
  label: '',
  location: '',
  gel: '',
});
const rows = ref([blank()]);
const universe = ref(1);
const startAddress = ref('');
const spacing = ref(0);
const busy = ref(false);
const typeOptions = ref([]);

const total = computed(() =>
  rows.value.reduce((sum, row) => sum + Math.min(200, Math.max(0, Math.floor(Number(row.quantity) || 0))), 0),
);

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    rows.value = [blank()];
    startAddress.value = '';
    spacing.value = 0;
    typeOptions.value = library.types.map((x) => x.name);
  },
);

function filterTypes(value, update) {
  update(() => {
    const needle = value.toLowerCase();
    typeOptions.value = library.types.map((x) => x.name).filter((n) => n.toLowerCase().includes(needle));
  });
}

const modeNames = (type) => modesForType(library.types, type).map((m) => m.name);

// A library mode brings its footprint into the row.
function pickMode(row, name) {
  const mode = modesForType(library.types, row.fixture_type).find((m) => m.name === name);
  if (mode) row.footprint = mode.footprint;
}

async function create() {
  busy.value = true;
  try {
    let created;
    created = await graph.createFixturesBulk(props.jobId, {
      universe: Number(universe.value) || 1,
      start_address: startAddress.value === '' ? null : Number(startAddress.value),
      spacing: Number(spacing.value) || 0,
      items: rows.value.filter((row) => (Number(row.quantity) || 0) >= 1).map((row) => ({
        fixture_type: row.fixture_type || '',
        channel_mode: row.channel_mode || '',
        footprint: Number(row.footprint) || null,
        quantity: Math.min(200, Math.floor(Number(row.quantity))),
        label: row.label,
        location: row.location,
        gel: row.gel,
      })),
    });
    emit('created', created);
    emit('update:modelValue', false);
    // the fixtures exist now; a failed library refresh must not look like a failed create
    library.fetch(context.value).catch(() => {});
  } catch (err) {
    emit('error', err);
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.bulk-card {
  width: 760px;
  max-width: 100vw;
}
</style>
