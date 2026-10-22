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
          <q-item-label caption>
            {{ t('jobs.stockwire') }}: {{ job.stockwire_job_id || '—' }}
          </q-item-label>
        </q-item-section>
      </q-item>
    </q-list>

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
          <q-input
            v-model="form.venue_name"
            :label="t('jobs.fieldVenue')"
          />
          <DateTimePicker
            v-model="form.event_date"
            :label="t('jobs.fieldEventDate')"
          />
          <q-input
            v-model="form.stockwire_job_id"
            :label="t('jobs.fieldStockwireId')"
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
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useJobsStore } from 'stores/jobs';
import DateTimePicker from 'components/DateTimePicker.vue';

const { t } = useI18n({ useScope: "global" })
const router = useRouter()
const store = useJobsStore();

function openJob(id) {
  router.push(`/jobs/${id}`)
}
const dialog = ref(false);
const form = ref({
  title: '',
  venue_name: '',
  event_date: '',
  stockwire_job_id: '',
});

onMounted(() => store.fetchJobs());

async function create() {
  const payload = { ...form.value };
  for (const key of Object.keys(payload)) {
    if (payload[key] === '') payload[key] = null;
  }
  await store.createJob(payload);
  dialog.value = false;
  form.value = { title: '', venue_name: '', event_date: '', stockwire_job_id: '' };
  await store.fetchJobs();
}

function formatDate(value) {
  return new Date(value).toLocaleString();
}
</script>
