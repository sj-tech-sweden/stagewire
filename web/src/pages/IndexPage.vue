<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="text-h5">
        {{ t('jobs.title') }}
      </div>
      <q-space />
      <q-btn
        color="primary"
        icon="add"
        :label="t('jobs.newJob')"
        @click="dialog = true"
      />
    </div>

    <q-input
      v-model="query"
      dense
      outlined
      clearable
      debounce="300"
      class="q-mb-md"
      :label="t('jobs.search')"
      data-testid="job-search"
      @update:model-value="(v) => store.fetchJobs({ search: v || '' })"
    >
      <template #prepend>
        <q-icon name="search" />
      </template>
    </q-input>

    <q-banner
      v-if="store.error"
      class="bg-negative text-white q-mb-md"
    >
      {{ store.error }}
    </q-banner>

    <q-linear-progress
      v-if="store.loading && store.jobs.length"
      indeterminate
      color="primary"
      class="q-mb-sm"
    />

    <q-inner-loading :showing="store.loading && !store.jobs.length" />

    <q-list
      v-if="store.jobs.length"
      bordered
      separator
    >
      <q-item
        v-for="job in store.jobs"
        :key="job.id"
        v-ripple
        clickable
        @click="openJob(job.id)"
      >
        <q-item-section>
          <q-item-label>{{ job.title }}</q-item-label>
          <q-item-label caption>
            {{ job.venue_name || t('jobs.noVenue') }}
            <span v-if="job.event_date"> · {{ formatDate(job.event_date) }}</span>
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-item-label
            v-if="stockwire.isEnabled"
            caption
          >
            {{ t('jobs.stockwire') }}: {{ job.stockwire_job_id || '—' }}
          </q-item-label>
        </q-item-section>
      </q-item>
    </q-list>

    <div
      v-if="store.jobs.length"
      class="row items-center justify-center q-gutter-sm q-mt-sm"
      data-testid="jobs-footer"
    >
      <span class="text-caption text-grey-6">
        {{ t('jobs.showing', { n: store.jobs.length, total: store.total }) }}
      </span>
      <q-btn
        v-if="store.hasMore"
        flat
        no-caps
        icon="expand_more"
        :label="t('jobs.loadMore')"
        :loading="store.loading"
        data-testid="jobs-more"
        @click="store.loadMore()"
      />
    </div>

    <q-card
      v-else
      flat
      bordered
      class="q-pa-lg text-center text-grey"
    >
      {{ t('jobs.noJobs') }}
    </q-card>

    <q-dialog v-model="dialog">
      <q-card style="min-width: 400px">
        <q-card-section>
          <div class="text-h6">
            {{ t('jobs.createTitle') }}
          </div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input
            v-model="form.title"
            :label="t('jobs.fieldTitle')"
            autofocus
          />
          <q-select
            v-model="form.venue_id"
            :options="venueOptions"
            :label="t('jobs.fieldVenue')"
            :hint="t('jobs.venueHint')"
            use-input
            emit-value
            map-options
            clearable
            input-debounce="0"
            @filter="onVenueFilter"
          >
            <template #no-option="{ inputValue }">
              <q-item>
                <q-item-section>
                  <q-btn
                    flat
                    no-caps
                    color="primary"
                    :label="t('venues.createNew', { name: inputValue || '' })"
                    @click="onCreateVenue(inputValue)"
                  />
                </q-item-section>
              </q-item>
            </template>
          </q-select>
          <DateTimePicker
            v-model="form.event_date"
            :label="t('jobs.fieldEventDate')"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('jobs.create')"
            color="primary"
            :disable="!form.title"
            @click="create"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useJobsStore } from '@/stores/jobs';
import { useVenuesStore } from '@/stores/venues';
import { useStockwireStore } from '@/stores/stockwire';
import DateTimePicker from '@/components/DateTimePicker.vue';

const { t } = useI18n({ useScope: "global" })
const router = useRouter()
const store = useJobsStore();
const venues = useVenuesStore();
const stockwire = useStockwireStore();

function openJob(id) {
  router.push(`/jobs/${id}`)
}
const dialog = ref(false);
const query = ref(store.search || '');
const venueSearch = ref('');
const venueOptions = computed(() =>
  venues.venues
    .filter((v) => v.name.toLowerCase().includes(venueSearch.value.toLowerCase()))
    .map((v) => ({ value: v.id, label: v.name })),
);
const form = ref({
  title: '',
  venue_id: null,
  event_date: '',
});

// The venue picker filters the cached venue list; the no-option button adds a brand new venue
// when the typed name does not match an existing one, so the picker doubles as a quick venue form.
function onVenueFilter(val, update) {
  venueSearch.value = val || '';
  update(() => {});
}

async function onCreateVenue(name) {
  const trimmed = (name || '').trim();
  if (!trimmed) return;
  const created = await venues.createVenue({ name: trimmed });
  form.value.venue_id = created.id;
  venueSearch.value = '';
}

watch(dialog, (open) => {
  if (open) venues.fetchVenues();
});

onMounted(() => store.fetchJobs());

async function create() {
  // venue_id is linked after creation (the link also seeds the venue's base rig); the create
  // payload itself only carries the editable job fields.
  const { venue_id, ...rest } = form.value;
  const payload = { ...rest };
  for (const key of Object.keys(payload)) {
    if (payload[key] === '') payload[key] = null;
  }
  const job = await store.createJob(payload);
  if (venue_id) {
    await venues.assignJobVenue(job.id, venue_id);
  }
  dialog.value = false;
  form.value = { title: '', venue_id: null, event_date: '' };
  query.value = '';
  await store.fetchJobs({ search: '' });
}

function formatDate(value) {
  return new Date(value).toLocaleString();
}
</script>
