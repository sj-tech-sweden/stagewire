<template>
  <div>
    <div class="row q-gutter-sm q-mb-xs">
      <q-select
        v-model="footprintFilter"
        :options="footprintOptions"
        emit-value
        map-options
        clearable
        dense
        outlined
        :label="t('venues.filterFootprint')"
        class="col"
      />
      <q-select
        v-model="stageFilter"
        :options="stageOptions"
        emit-value
        map-options
        clearable
        dense
        outlined
        :label="t('venues.filterStage')"
        class="col"
      />
    </div>
    <q-select
      :model-value="modelValue"
      :options="options"
      use-input
      input-debounce="150"
      :label="label"
      :hint="hint"
      emit-value
      map-options
      clearable
      @filter="onFilter"
      @update:model-value="(v) => emit('update:modelValue', v || null)"
    >
      <template #no-option>
        <q-item>
          <q-item-section class="text-grey-7">
            {{ t('venues.noResults') }}
          </q-item-section>
        </q-item>
      </template>
      <template #option="scope">
        <q-item v-bind="scope.itemProps">
          <q-item-section avatar>
            <q-icon name="meeting_room" />
          </q-item-section>
          <q-item-section>
            <q-item-label>{{ scope.opt.label }}</q-item-label>
            <q-item-label caption>
              {{ scope.opt.description }}
            </q-item-label>
          </q-item-section>
        </q-item>
      </template>
    </q-select>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useVenuesStore } from '@/stores/venues';

const props = defineProps({
  modelValue: { type: String, default: null },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
});
const emit = defineEmits(['update:modelValue']);

const { t } = useI18n({ useScope: 'global' });
const venuesStore = useVenuesStore();

const footprintFilter = ref(null);
const stageFilter = ref(null);

const footprintOptions = [
  { value: 'rectangular', label: t('venues.footprintShapes.rectangular') },
  { value: 'arena_circular', label: t('venues.footprintShapes.arena_circular') },
  { value: 'amphitheater', label: t('venues.footprintShapes.amphitheater') },
  { value: 'custom_polygon', label: t('venues.footprintShapes.custom_polygon') },
];
const stageOptions = [
  { value: 'proscenium', label: t('venues.stageShapes.proscenium') },
  { value: 'thrust', label: t('venues.stageShapes.thrust') },
  { value: 'arena_center', label: t('venues.stageShapes.arena_center') },
  { value: 'runway', label: t('venues.stageShapes.runway') },
];

const shapeFiltered = computed(() =>
  venuesStore.venues.filter(
    (v) =>
      (!footprintFilter.value || v.footprint_shape === footprintFilter.value) &&
      (!stageFilter.value || v.stage_shape === stageFilter.value),
  ),
);

const options = ref([]);

function rebuild(search) {
  const term = (search || '').trim().toLowerCase();
  options.value = shapeFiltered.value
    .filter((v) => !term || v.name.toLowerCase().includes(term))
    .map((v) => ({
      value: v.id,
      label: v.name,
      description: t('venues.sizeSummary', {
        w: v.venue_width_cm,
        h: v.venue_height_cm,
      }),
    }));
}

rebuild('');

watch([shapeFiltered, () => venuesStore.venues], () => rebuild(''));

function onFilter(val, update) {
  update(() => rebuild(val));
}
</script>
