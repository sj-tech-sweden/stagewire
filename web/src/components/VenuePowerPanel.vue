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
      <q-card-section v-if="!venueId">
        <div class="text-grey-6">
          {{ t('workspace.venuePowerNoVenue') }}
        </div>
      </q-card-section>
      <q-card-section v-else>
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t('workspace.venuePowerHint') }}
        </div>

        <div class="row items-center q-mb-xs">
          <div class="text-subtitle2 col">
            {{ t('workspace.venueGroups') }}
          </div>
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('workspace.addVenueGroup')"
            data-testid="add-venue-group"
            @click="addGroup"
          />
        </div>
        <div
          v-for="group in groups"
          :key="group.id"
          class="row q-col-gutter-xs items-center q-mb-xs"
          data-testid="venue-group"
        >
          <q-input
            :model-value="group.name"
            class="col-12 col-sm-5"
            dense
            outlined
            :label="t('workspace.trussName')"
            data-testid="venue-group-name"
            @change="(v) => saveGroup(group, { name: v })"
          />
          <q-input
            :model-value="group.rating_amps"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            :label="t('workspace.powerRating')"
            data-testid="venue-group-rating"
            @change="(v) => saveGroup(group, { rating_amps: v === '' ? null : Number(v) })"
          />
          <q-select
            :model-value="group.phases"
            class="col-4 col-sm-2"
            dense
            outlined
            emit-value
            :options="[1, 3]"
            :label="t('workspace.venueGroupPhases')"
            @update:model-value="(v) => saveGroup(group, { phases: v })"
          />
          <q-select
            v-if="group.phases === 1"
            :model-value="group.phase || 'L1'"
            class="col-4 col-sm-2"
            dense
            outlined
            emit-value
            :options="['L1', 'L2', 'L3']"
            :label="t('workspace.outputPhase')"
            data-testid="venue-group-phase"
            @update:model-value="(v) => saveGroup(group, { phase: v })"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="removeGroup(group)"
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
const props = defineProps({ jobId: { type: String, required: true } });
const emit = defineEmits(['changed']);
const { t } = useI18n();
const $q = useQuasar();
const open = ref(false);
const venueId = ref(null);
const groups = ref([]);
const outlets = ref([]);

const groupOptions = computed(() => groups.value.map((g) => ({ value: g.id, label: g.name || '—' })));
const caption = computed(() =>
  venueId.value ? t('workspace.venuePowerCount', { groups: groups.value.length, outlets: outlets.value.length }) : '',
);

const failed = (err) =>
  $q.notify({ type: 'negative', message: apiErrorText(err) });

async function load() {
  try {
    const job = (await api.get(`/jobs/${props.jobId}`)).data;
    venueId.value = job.venue_id || null;
    if (!venueId.value) return;
    [groups.value, outlets.value] = (
      await Promise.all([
        api.get(`/venues/${venueId.value}/power-groups`),
        api.get(`/venues/${venueId.value}/power-outlets`),
      ])
    ).map((res) => res.data);
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

const addGroup = () =>
  run(() => api.post(`/venues/${venueId.value}/power-groups`, { name: `${t('workspace.venueGroup')} ${groups.value.length + 1}`, rating_amps: 16, phases: 1 }));
const saveGroup = (group, changes) => run(() => api.patch(`/venues/${venueId.value}/power-groups/${group.id}`, changes));
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
    () => api.delete(`/venues/${venueId.value}/power-groups/${group.id}`),
  );
const addOutlet = () =>
  run(() => api.post(`/venues/${venueId.value}/power-outlets`, { name: `${t('workspace.venueOutlet')} ${outlets.value.length + 1}`, connector: 'schuko', x_cm: 100, y_cm: 100 }));
const saveOutlet = (outlet, changes) => run(() => api.patch(`/venues/${venueId.value}/power-outlets/${outlet.id}`, changes));
const removeOutlet = (outlet) =>
  confirmDelete(t('workspace.venueOutletDeleteWarn', { name: outlet.name || '—' }), () =>
    api.delete(`/venues/${venueId.value}/power-outlets/${outlet.id}`),
  );

onMounted(load);
</script>
