<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="device-card">
      <q-card-section>
        <div class="text-h6">
          {{ node ? t('devices.edit') : t('devices.createDevice') }}
        </div>
      </q-card-section>
      <q-card-section class="q-pt-none q-gutter-sm">
        <div class="row q-col-gutter-sm">
          <q-input
            v-model="form.name"
            class="col-12 col-sm-7"
            dense
            outlined
            :label="t('devices.name')"
            data-testid="device-name"
          />
          <q-select
            v-model="form.device_type"
            class="col-12 col-sm-5"
            dense
            outlined
            emit-value
            map-options
            :options="typeOptions"
            :label="t('devices.type')"
            data-testid="device-type"
          />
        </div>
        <q-input
          v-model="form.notes"
          dense
          outlined
          autogrow
          :label="t('channels.fieldNotes')"
        />

        <div class="text-subtitle2 q-mt-md">
          {{ t('devices.ports') }}
        </div>
        <div
          class="row q-gutter-xs q-mb-sm"
          data-testid="connector-presets"
        >
          <q-chip
            v-for="preset in CONNECTOR_PRESETS"
            :key="preset.label"
            dense
            clickable
            icon="add"
            data-testid="connector-preset"
            @click="form.ports = addConnector(form.ports, preset)"
          >
            {{ preset.label }}
          </q-chip>
        </div>
        <div
          v-for="(port, i) in form.ports"
          :key="i"
          class="row q-col-gutter-xs items-center"
        >
          <q-select
            v-model="port.direction"
            class="col-4 col-sm-3"
            dense
            outlined
            emit-value
            map-options
            :options="[
              { label: t('devices.directionIn'), value: 'in' },
              { label: t('devices.directionOut'), value: 'out' },
              { label: t('devices.directionBoth'), value: 'both' },
            ]"
            :label="t('devices.direction')"
            data-testid="port-direction"
          />
          <q-select
            v-model="port.connector"
            class="col-5 col-sm-5"
            dense
            outlined
            use-input
            hide-selected
            fill-input
            emit-value
            map-options
            new-value-mode="add-unique"
            input-debounce="0"
            :options="connectorOptions"
            :label="t('channels.patchPoint.connector')"
            data-testid="port-connector"
            @filter="filterConnectors"
          />
          <q-input
            v-model.number="port.count"
            class="col-3 col-sm-2"
            dense
            outlined
            type="number"
            min="0"
            :label="t('devices.count')"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="close"
            :aria-label="t('workspace.remove')"
            @click="form.ports.splice(i, 1)"
          />
        </div>
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('devices.addPort')"
          data-testid="add-port"
          @click="form.ports.push({ direction: 'in', connector: '', count: 1 })"
        />

        <div class="row q-col-gutter-sm q-mt-md">
          <q-input
            v-model="form.weight_kg"
            class="col-6"
            dense
            outlined
            type="number"
            :label="t('devices.weight')"
          />
          <q-input
            v-model="form.power_w"
            class="col-6"
            dense
            outlined
            type="number"
            :label="t('devices.power')"
          />
        </div>
        <div
          v-if="IO_DEVICE_TYPES.includes(form.device_type)"
          class="row q-col-gutter-sm"
        >
          <q-input
            v-model="form.input_override"
            class="col-6"
            dense
            outlined
            type="number"
            :label="t('devices.inputs')"
          />
          <q-input
            v-model="form.output_override"
            class="col-6"
            dense
            outlined
            type="number"
            :label="t('devices.outputs')"
          />
        </div>

        <div
          v-if="form.device_type === 'fixture'"
          class="row q-col-gutter-sm"
        >
          <q-input
            v-model="form.fixture_type"
            class="col-12 col-sm-6"
            dense
            outlined
            :label="t('devices.fixtureType')"
          />
          <q-input
            v-model="form.channel_mode"
            class="col-6 col-sm-3"
            dense
            outlined
            :label="t('devices.channelMode')"
          />
          <q-input
            v-model="form.footprint_channels"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            :label="t('devices.footprint')"
          />
          <q-input
            v-model="form.default_gel"
            class="col-12"
            dense
            outlined
            :label="t('devices.defaultGel')"
          />
        </div>
        <div
          v-if="CAMERA_TYPES.includes(form.device_type)"
          class="row q-col-gutter-sm"
        >
          <q-input
            v-model="form.sensor_width_mm"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            :label="t('devices.sensorWidth')"
          />
          <q-input
            v-model="form.focal_min_mm"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            :label="t('devices.focalMin')"
          />
          <q-input
            v-model="form.focal_max_mm"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            :label="t('devices.focalMax')"
          />
          <q-input
            v-model="form.max_distance_m"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            :label="t('devices.maxDistance')"
          />
        </div>
        <div
          v-if="form.device_type === 'projector'"
          class="row q-col-gutter-sm"
        >
          <q-input
            v-model="form.throw_ratio_min"
            class="col-4"
            dense
            outlined
            type="number"
            :label="t('devices.throwRatioMin')"
          />
          <q-input
            v-model="form.throw_ratio_max"
            class="col-4"
            dense
            outlined
            type="number"
            :label="t('devices.throwRatioMax')"
          />
          <q-input
            v-model="form.image_aspect_ratio"
            class="col-4"
            dense
            outlined
            type="number"
            :label="t('devices.imageAspect')"
          />
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
          :disable="!form.name.trim()"
          :label="t('workspace.save')"
          data-testid="device-save"
          @click="emit('save', form)"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  CAMERA_TYPES,
  CONNECTOR_CHOICES,
  CONNECTOR_PRESETS,
  DEVICE_TYPES,
  IO_DEVICE_TYPES,
  addConnector,
  deviceForm,
} from '@/utils/workspace';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  node: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const form = reactive(deviceForm(null));
const connectorOptions = ref(CONNECTOR_CHOICES);

// The connector list is a suggestion: a typed value that is not in it is kept as it is.
function filterConnectors(value, update) {
  update(() => {
    const needle = value.toLowerCase();
    connectorOptions.value = CONNECTOR_CHOICES.filter(
      (c) => c.label.toLowerCase().includes(needle) || c.value.includes(needle),
    );
  });
}
const typeOptions = computed(() => DEVICE_TYPES.map((v) => ({ value: v, label: t(`devices.types.${v}`) })));

watch(
  () => props.modelValue,
  (open) => {
    if (open) Object.assign(form, deviceForm(props.node));
  },
);
</script>

<style scoped>
.device-card {
  width: 760px;
  max-width: 100vw;
}
</style>
