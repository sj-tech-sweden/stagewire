<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card style="width: 640px; max-width: 100vw">
      <q-card-section class="text-h6">
        {{ t('workspace.jobDetails') }}
      </q-card-section>
      <q-card-section class="q-pt-none q-gutter-sm">
        <q-input
          v-model="form.title"
          dense
          outlined
          :label="t('jobs.fieldTitle')"
          data-testid="job-title"
        />
        <q-input
          v-model="form.venue_name"
          dense
          outlined
          :label="t('jobs.fieldVenue')"
        />
        <q-select
          v-model="form.venue_id"
          dense
          outlined
          clearable
          emit-value
          map-options
          :options="venueOptions"
          :label="t('venues.assignLabel')"
          :hint="t('venues.assignHint')"
          data-testid="job-venue"
        />
        <DateTimePicker
          v-model="form.event_date"
          :label="t('jobs.fieldEventDate')"
        />
        <div class="row q-col-gutter-sm">
          <q-input
            v-model="form.start_date"
            class="col-6"
            dense
            outlined
            type="date"
            :label="t('jobs.fieldStartDate')"
            data-testid="job-start-date"
          />
          <q-input
            v-model="form.end_date"
            class="col-6"
            dense
            outlined
            type="date"
            :label="t('jobs.fieldEndDate')"
            data-testid="job-end-date"
          />
        </div>
        <q-input
          v-model="form.notes"
          dense
          outlined
          type="textarea"
          autogrow
          :label="t('jobs.fieldNotes')"
        />

        <q-separator class="q-my-md" />
        <div class="text-subtitle2">
          {{ t('stockwire.linkedJob') }}
        </div>
        <div class="row items-center q-gutter-sm">
          <q-chip
            dense
            square
            :color="job?.stockwire_job_id ? 'positive' : 'grey-7'"
            text-color="white"
            icon="link"
            data-testid="job-stockwire-status"
          >
            {{ job?.stockwire_job_id ? t('stockwire.linkedAs', { id: job.stockwire_job_id }) : t('stockwire.notLinked') }}
          </q-chip>
          <template v-if="!job?.stockwire_job_id">
            <q-btn
              dense
              outline
              no-caps
              color="primary"
              icon="link"
              :label="t('stockwire.linkExisting')"
              data-testid="job-link-existing"
              @click="openLink"
            />
            <q-btn
              dense
              outline
              no-caps
              color="primary"
              icon="add"
              :label="t('stockwire.createNew')"
              :loading="busy"
              data-testid="job-create-stockwire"
              @click="link(null)"
            />
          </template>
          <q-btn
            dense
            outline
            no-caps
            color="primary"
            icon="open_in_new"
            :label="t('stockwire.openInStockwire')"
            :disable="!job?.stockwire_job_id"
            data-testid="job-open-stockwire"
            @click="openInStockwire"
          />
          <q-btn
            dense
            outline
            no-caps
            color="primary"
            icon="playlist_add"
            :label="t('workspace.syncStockwire')"
            :loading="pushing"
            :disable="!job?.stockwire_job_id"
            data-testid="job-sync-stockwire"
            @click="sync"
          />
        </div>
        <div class="text-caption text-grey-6">
          {{ t('stockwire.addDevicesHint') }}
        </div>
        <div
          v-if="message"
          class="text-caption"
          :class="error ? 'text-negative' : 'text-positive'"
        >
          {{ message }}
        </div>

        <div v-if="linkOpen">
          <q-input
            v-model="search"
            dense
            outlined
            :label="t('stockwire.linkSearch')"
            data-testid="job-link-search"
            @update:model-value="onSearch"
          />
          <q-list
            bordered
            separator
            class="q-mt-xs"
          >
            <q-item
              v-for="r in results"
              :key="r.id"
              clickable
              data-testid="job-link-result"
              @click="link(r.id)"
            >
              <q-item-section>
                <q-item-label>{{ r.name || r.title || r.id }}</q-item-label>
                <q-item-label caption>
                  #{{ r.id }}<span v-if="r.venue_name"> · {{ r.venue_name }}</span>
                </q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="!results.length && !loading">
              <q-item-section class="text-grey-6">
                {{ t('stockwire.notFound') }}
              </q-item-section>
            </q-item>
          </q-list>
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
          :disable="!form.title.trim()"
          :label="t('workspace.save')"
          data-testid="job-save"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { computed, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { api } from '@/boot/api';
import DateTimePicker from '@/components/DateTimePicker.vue';
import { useVenuesStore } from '@/stores/venues';
import { useStockwireStore } from '@/stores/stockwire';

// The job itself: title, venue, date and notes, and its link to a Stockwire job (link an existing
// one, create one, open it through the deeplink, send the gear to it). These are the same calls the
// job page makes, so both show the same job.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  job: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue', 'saved']);
const { t } = useI18n();
const venues = useVenuesStore();
const stockwire = useStockwireStore();
const form = reactive({
  title: '',
  venue_name: '',
  venue_id: null,
  event_date: '',
  start_date: '',
  end_date: '',
  notes: '',
});
const busy = ref(false);
const pushing = ref(false);
const message = ref('');
const error = ref(false);
const linkOpen = ref(false);
const search = ref('');
const results = ref([]);
const loading = ref(false);
let timer = null;

const venueOptions = computed(() => venues.venues.map((v) => ({ value: v.id, label: v.name })));
const failure = (err) => apiErrorText(err) || t('stockwire.noIntegration');

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    Object.assign(form, {
      title: props.job?.title || '',
      venue_name: props.job?.venue_name || '',
      venue_id: props.job?.venue_id || null,
      event_date: props.job?.event_date || '',
      start_date: props.job?.start_date || '',
      end_date: props.job?.end_date || '',
      notes: props.job?.notes || '',
    });
    message.value = '';
    linkOpen.value = false;
    venues.fetchVenues();
  },
);

async function save() {
  try {
    await api.patch(`/jobs/${props.jobId}`, {
      title: form.title,
      venue_name: form.venue_name,
      event_date: form.event_date || null,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      notes: form.notes,
    });
    if ((form.venue_id || null) !== (props.job?.venue_id || null)) {
      await venues.assignJobVenue(props.jobId, form.venue_id || null);
    }
    emit('saved');
    emit('update:modelValue', false);
  } catch (err) {
    error.value = true;
    message.value = failure(err);
  }
}

async function searchJobs() {
  loading.value = true;
  try {
    const { data } = await api.get('/stockwire/rental-jobs', {
      params: { search: search.value?.trim() || undefined },
    });
    results.value = data.items || [];
  } catch (err) {
    results.value = [];
    error.value = true;
    message.value = failure(err);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  clearTimeout(timer);
  timer = setTimeout(searchJobs, 300);
}

function openLink() {
  linkOpen.value = true;
  search.value = '';
  searchJobs();
}

async function link(existingId) {
  busy.value = true;
  message.value = '';
  error.value = false;
  try {
    const { data } = await api.post(`/stockwire/jobs/${props.jobId}/link`, {
      stockwire_job_id: existingId ? String(existingId) : null,
    });
    message.value = t('stockwire.linked', { id: data.stockwire_job_id });
    linkOpen.value = false;
    emit('saved');
  } catch (err) {
    error.value = true;
    message.value = failure(err);
  } finally {
    busy.value = false;
  }
}

async function openInStockwire() {
  const tab = window.open('', '_blank');
  try {
    const url = await stockwire.jobDeeplink(props.jobId);
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (err) {
    tab?.close();
    error.value = true;
    message.value = failure(err);
  }
}

async function sync() {
  pushing.value = true;
  message.value = '';
  error.value = false;
  try {
    const { data } = await api.post(`/jobs/${props.jobId}/sync-stockwire`);
    const summary = t('workspace.stockwireSynced', {
      added: data.added.length,
      updated: data.updated.length,
      removed: data.removed.length,
    });
    // items Stockwire refused are listed, not hidden behind a green message
    error.value = Boolean(data.errors?.length);
    message.value = data.errors?.length
      ? `${summary}. ${t('workspace.syncErrors', { n: data.errors.length })}: ${data.errors.slice(0, 3).join('; ')}`
      : summary;
  } catch (err) {
    error.value = true;
    message.value = failure(err);
  } finally {
    pushing.value = false;
  }
}
</script>
