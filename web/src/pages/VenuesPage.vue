<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">
        {{ t('venues.title') }}
      </div>
      <q-btn
        color="primary"
        icon="add"
        :label="t('venues.newVenue')"
        @click="openCreate"
      />
    </div>

    <q-card
      v-if="!venues.loading && !venues.venues.length"
      flat
      bordered
    >
      <q-card-section class="text-grey-7">
        {{ t('venues.empty') }}
      </q-card-section>
    </q-card>

    <q-list
      v-else
      bordered
      separator
      class="rounded-borders"
    >
      <q-item
        v-for="v in venues.venues"
        :key="v.id"
        v-ripple
        clickable
        @click="openEdit(v)"
      >
        <q-item-section avatar>
          <q-avatar
            rounded
            size="48px"
          >
            <img
              v-if="v.background_image_url"
              :src="fullImageUrl(v.background_image_url)"
              alt=""
            >
            <q-icon
              v-else
              name="meeting_room"
            />
          </q-avatar>
        </q-item-section>
        <q-item-section>
          <q-item-label>{{ v.name }}</q-item-label>
          <q-item-label caption>
            {{ t('venues.sizeSummary', { w: v.venue_width_cm, h: v.venue_height_cm }) }}
            · {{ t('venues.stageSummary', { w: v.stage_width_cm, h: v.stage_height_cm }) }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-btn
            flat
            round
            dense
            icon="delete"
            color="negative"
            :aria-label="t('common.delete')"
            @click.stop="confirmDelete(v)"
          />
        </q-item-section>
      </q-item>
    </q-list>

    <q-dialog
      v-model="dialog"
      persistent
    >
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ editingId ? t('venues.editVenue') : t('venues.newVenue') }}
        </q-card-section>

        <q-card-section class="q-gutter-md">
          <q-input
            v-model="form.name"
            :label="t('venues.fieldName')"
            :rules="[(val) => !!val || t('common.required')]"
          />
          <div class="text-subtitle2">
            {{ t('venues.venueSize') }}
          </div>
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="form.venue_width_cm"
              type="number"
              :label="t('venues.venueWidth')"
              dense
              class="col"
            />
            <q-input
              v-model.number="form.venue_height_cm"
              type="number"
              :label="t('venues.venueHeight')"
              dense
              class="col"
            />
          </div>
          <div class="text-subtitle2">
            {{ t('venues.stageSection') }}
          </div>
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="form.stage_x_cm"
              type="number"
              :label="t('venues.stageX')"
              dense
              class="col"
            />
            <q-input
              v-model.number="form.stage_y_cm"
              type="number"
              :label="t('venues.stageY')"
              dense
              class="col"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="form.stage_width_cm"
              type="number"
              :label="t('venues.stageWidth')"
              dense
              class="col"
            />
            <q-input
              v-model.number="form.stage_height_cm"
              type="number"
              :label="t('venues.stageHeight')"
              dense
              class="col"
            />
          </div>

          <div>
            <q-file
              :model-value="null"
              accept="image/*"
              :label="t('venues.uploadFloorPlan')"
              dense
              clearable
              :loading="uploading"
              @update:model-value="onFloorPlanPicked"
            >
              <template #append>
                <q-icon name="image" />
              </template>
            </q-file>
            <div
              v-if="form.background_image_url"
              class="row items-center q-gutter-sm q-mt-xs"
            >
              <img
                :src="fullImageUrl(form.background_image_url)"
                alt=""
                style="max-width: 160px; max-height: 110px; border-radius: 4px"
              >
              <q-btn
                flat
                dense
                round
                icon="delete"
                color="negative"
                :aria-label="t('venues.removeFloorPlan')"
                @click="form.background_image_url = ''"
              />
            </div>
          </div>

          <q-input
            v-model="form.notes"
            :label="t('venues.fieldNotes')"
            type="textarea"
            autogrow
          />

          <div
            v-if="editingId"
            class="q-pa-sm rounded-borders bg-grey-2 text-grey-10"
          >
            <div class="text-subtitle2">
              {{ t('venues.propagateTitle') }}
            </div>
            <div class="text-body2 q-mb-sm">
              {{ t('venues.propagateHint') }}
            </div>
            <div class="row q-gutter-sm">
              <q-btn
                outline
                no-caps
                :label="t('venues.propagateAll')"
                :loading="propagating"
                @click="propagate('all')"
              />
              <q-btn
                outline
                no-caps
                :label="t('venues.propagateNewer')"
                :loading="propagating"
                @click="propagate('newer')"
              />
            </div>
            <q-banner
              dense
              rounded
              role="status"
              class="bg-blue-grey-2 text-blue-grey-10 text-weight-medium q-mt-sm"
            >
              <template #avatar>
                <q-icon
                  name="update"
                  color="blue-grey-10"
                />
              </template>
              {{ lastPropagatedText }}
            </q-banner>
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn
            flat
            :label="t('common.cancel')"
            @click="dialog = false"
          />
          <q-btn
            color="primary"
            :label="t('common.save')"
            :disable="!form.name.trim()"
            :loading="saving"
            @click="save"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import { getApiBaseUrl } from '@/utils/runtime-config';
import { useVenuesStore } from '@/stores/venues';

const { t } = useI18n({ useScope: 'global' });
const $q = useQuasar();
const venues = useVenuesStore();

const dialog = ref(false);
const editingId = ref(null);
const editingVenue = ref(null);
const saving = ref(false);
const uploading = ref(false);
const propagating = ref(false);

const EMPTY = {
  name: '',
  notes: '',
  venue_width_cm: 0,
  venue_height_cm: 0,
  stage_x_cm: 0,
  stage_y_cm: 0,
  stage_width_cm: 0,
  stage_height_cm: 0,
  background_image_url: '',
};
const form = reactive({ ...EMPTY });

const lastPropagatedText = computed(() => {
  const at = editingVenue.value?.propagated_at;
  if (!at) return t('venues.neverPropagated');
  return t('venues.lastPropagated', { date: new Date(at).toLocaleString() });
});

function fullImageUrl(value) {
  if (!value) return value;
  if (/^https?:\/\//i.test(value)) return value;
  return getApiBaseUrl() + value;
}

function openCreate() {
  editingId.value = null;
  editingVenue.value = null;
  Object.assign(form, EMPTY);
  dialog.value = true;
}

function openEdit(v) {
  editingId.value = v.id;
  editingVenue.value = v;
  Object.assign(form, {
    name: v.name,
    notes: v.notes || '',
    venue_width_cm: v.venue_width_cm,
    venue_height_cm: v.venue_height_cm,
    stage_x_cm: v.stage_x_cm,
    stage_y_cm: v.stage_y_cm,
    stage_width_cm: v.stage_width_cm,
    stage_height_cm: v.stage_height_cm,
    background_image_url: v.background_image_url || '',
  });
  dialog.value = true;
}

function payload() {
  return {
    ...form,
    name: form.name.trim(),
    venue_width_cm: Number(form.venue_width_cm) || 0,
    venue_height_cm: Number(form.venue_height_cm) || 0,
    stage_x_cm: Number(form.stage_x_cm) || 0,
    stage_y_cm: Number(form.stage_y_cm) || 0,
    stage_width_cm: Number(form.stage_width_cm) || 0,
    stage_height_cm: Number(form.stage_height_cm) || 0,
  };
}

async function save() {
  saving.value = true;
  try {
    if (editingId.value) {
      editingVenue.value = await venues.updateVenue(editingId.value, payload());
    } else {
      const created = await venues.createVenue(payload());
      editingId.value = created.id;
      editingVenue.value = created;
    }
    dialog.value = false;
  } catch (err) {
    $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('app.actions.saveFailed') });
  } finally {
    saving.value = false;
  }
}

async function onFloorPlanPicked(file) {
  if (!file) {
    form.background_image_url = '';
    return;
  }
  uploading.value = true;
  try {
    const body = new FormData();
    body.append('file', file);
    const { data } = await api.post('/uploads', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    form.background_image_url = data.url;
  } catch (err) {
    $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('common.errorOccurred') });
  } finally {
    uploading.value = false;
  }
}

async function propagate(scope) {
  if (!editingId.value) return;
  $q.dialog({
    title: t('venues.propagateTitle'),
    message: t('venues.propagateConfirm'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    propagating.value = true;
    try {
      await venues.updateVenue(editingId.value, payload());
      const result = await venues.propagateVenue(editingId.value, scope);
      editingVenue.value = venues.venues.find((v) => v.id === editingId.value) || editingVenue.value;
      $q.notify({ type: 'positive', message: t('venues.propagated', { count: result.updated }) });
    } catch (err) {
      $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('common.errorOccurred') });
    } finally {
      propagating.value = false;
    }
  });
}

function confirmDelete(v) {
  $q.dialog({
    title: t('venues.deleteTitle'),
    message: t('venues.deleteConfirm', { name: v.name }),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await venues.deleteVenue(v.id);
    } catch (err) {
      $q.notify({ type: 'negative', message: err?.response?.data?.detail || t('common.deleteFailed') });
    }
  });
}

onMounted(() => {
  venues.fetchVenues();
});
</script>
