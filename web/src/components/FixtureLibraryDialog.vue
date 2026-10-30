<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="library-card column no-wrap">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 col">
          {{ t('workspace.library') }}
        </div>
        <q-btn
          v-close-popup
          flat
          round
          icon="close"
          :aria-label="t('common.cancel')"
        />
      </q-card-section>

      <q-card-section class="q-gutter-sm">
        <div class="text-caption text-grey-6">
          {{ t('lights.subtitle') }}
        </div>
        <div class="row q-col-gutter-sm items-center">
          <q-input
            v-model="newType"
            class="col"
            dense
            outlined
            :label="t('workspace.typeName')"
            data-testid="library-type-name"
            @keyup.enter="addType"
          />
          <q-btn
            color="primary"
            no-caps
            icon="add"
            :disable="!newType.trim()"
            :label="t('workspace.addType')"
            data-testid="library-add-type"
            @click="addType"
          />
        </div>
        <StockwireProductPicker
          :model-value="null"
          gear-type="fixture"
          :label="t('lights.fromStockwire')"
          :hint="t('lights.fromStockwireHint')"
          @update:model-value="importFromStockwire"
        />
      </q-card-section>

      <q-separator />
      <div class="col scroll">
        <div
          v-if="!library.types.length"
          class="q-pa-md text-grey-6"
        >
          {{ t('workspace.noTypes') }}
        </div>
        <q-expansion-item
          v-for="type in library.types"
          :key="type.id"
          group="types"
          :label="type.name"
          :caption="[type.manufacturer, `${type.modes.length} ${t('workspace.modes')}`].filter(Boolean).join(' · ')"
          data-testid="library-type"
        >
          <div class="q-pa-md q-gutter-sm">
            <div class="row q-col-gutter-sm">
              <q-input
                :model-value="type.name"
                class="col-12 col-sm-6"
                dense
                outlined
                :label="t('workspace.typeName')"
                @change="(v) => saveType(type, { name: v })"
              />
              <q-input
                :model-value="type.manufacturer"
                class="col-12 col-sm-6"
                dense
                outlined
                :label="t('workspace.maker')"
                @change="(v) => saveType(type, { manufacturer: v })"
              />
              <q-input
                :model-value="type.weight_kg"
                class="col-6"
                dense
                outlined
                type="number"
                :label="t('lights.typeWeight')"
                @change="(v) => saveType(type, { weight_kg: v === '' ? null : Number(v) })"
              />
              <q-input
                :model-value="type.power_watts"
                class="col-6"
                dense
                outlined
                type="number"
                :label="t('lights.typePower')"
                @change="(v) => saveType(type, { power_watts: v === '' ? null : Number(v) })"
              />
            </div>
            <q-badge
              v-if="type.source !== 'manual'"
              color="teal"
              :label="type.source"
            />

            <div class="text-subtitle2">
              {{ t('workspace.modes') }}
            </div>
            <div
              v-for="mode in type.modes"
              :key="mode.id"
              class="row q-col-gutter-xs items-center"
              data-testid="library-mode"
            >
              <q-input
                :model-value="mode.name"
                class="col"
                dense
                outlined
                :label="t('lights.mode')"
                @change="(v) => saveMode(type, mode, { name: v })"
              />
              <q-input
                :model-value="mode.footprint"
                class="col-4"
                dense
                outlined
                type="number"
                min="1"
                max="512"
                :label="t('lights.colFootprint')"
                @change="(v) => saveMode(type, mode, { footprint: Number(v) })"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="close"
                :aria-label="t('workspace.remove')"
                @click="run(() => library.deleteMode(jobId, type.id, mode.id))"
              />
            </div>
            <div class="row q-col-gutter-xs items-center">
              <q-input
                v-model="drafts[type.id].name"
                class="col"
                dense
                outlined
                :label="t('workspace.modeName')"
                data-testid="library-mode-name"
              />
              <q-input
                v-model.number="drafts[type.id].footprint"
                class="col-4"
                dense
                outlined
                type="number"
                min="1"
                max="512"
                :label="t('lights.colFootprint')"
                data-testid="library-mode-footprint"
              />
              <q-btn
                color="primary"
                dense
                no-caps
                icon="add"
                :disable="!drafts[type.id].name.trim() || !drafts[type.id].footprint"
                :label="t('workspace.addMode')"
                data-testid="library-add-mode"
                @click="addMode(type)"
              />
            </div>
            <q-btn
              flat
              no-caps
              color="negative"
              icon="delete"
              :label="t('workspace.deleteType')"
              @click="removeType(type)"
            />
          </div>
        </q-expansion-item>
      </div>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useFixtureLibraryStore } from '@/stores/fixtureLibrary';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();
const $q = useQuasar();
const library = useFixtureLibraryStore();
const newType = ref('');
const drafts = reactive({});

watch(
  () => library.types,
  (types) => {
    for (const type of types) drafts[type.id] ||= { name: '', footprint: null };
  },
  { immediate: true, deep: true },
);
watch(
  () => props.modelValue,
  (open) => {
    if (open) library.fetch(props.jobId).catch(() => {});
  },
);

async function run(action) {
  try {
    await action();
  } catch (err) {
    $q.notify({
      type: 'negative',
      message: err.response?.data?.detail?.message || err.response?.data?.detail || err.message,
    });
  }
}

const saveType = (type, changes) => run(() => library.updateType(props.jobId, type.id, changes));
const saveMode = (type, mode, changes) =>
  run(() => library.updateMode(props.jobId, type.id, mode.id, changes));

function addType() {
  const name = newType.value.trim();
  if (!name) return;
  run(async () => {
    await library.createType(props.jobId, { name });
    newType.value = '';
  });
}

function addMode(type) {
  const draft = drafts[type.id];
  run(async () => {
    await library.createMode(props.jobId, type.id, { name: draft.name.trim(), footprint: draft.footprint });
    draft.name = '';
    draft.footprint = null;
  });
}

function removeType(type) {
  $q.dialog({ title: t('workspace.deleteType'), message: type.name, cancel: true, persistent: true }).onOk(() =>
    run(() => library.deleteType(props.jobId, type.id)),
  );
}

function importFromStockwire(product) {
  if (!product?.id) return;
  run(async () => {
    const data = await library.importFromStockwire(props.jobId, product.id);
    $q.notify({ type: 'positive', message: t('lights.fromStockwireDone', { name: data.name }) });
  });
}
</script>

<style scoped>
.library-card {
  width: 640px;
  max-width: 100vw;
  max-height: 90vh;
}
</style>
