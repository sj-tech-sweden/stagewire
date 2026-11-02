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
        <StockwireProductPicker
          :model-value="null"
          :label="t('devices.fromStockwire')"
          :hint="t('devices.fromStockwireHint')"
          data-testid="device-from-stockwire"
          @update:model-value="importProduct"
        />
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
          <ConnectorSelect
            v-model="port.connector"
            class="col-5 col-sm-5"
            :label="t('channels.patchPoint.connector')"
            data-testid="port-connector"
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
          <q-select
            v-model="form.power_inlet"
            class="col-12"
            dense
            outlined
            emit-value
            map-options
            clearable
            :options="POWER_INLETS"
            :label="t('workspace.powerInlet')"
            :hint="t('workspace.powerInletHint')"
            data-testid="power-inlet"
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
          class="q-gutter-sm"
          data-testid="sensor-calculator"
        >
          <q-select
            v-model="sensorPreset"
            :options="sensorPresetOptions"
            :label="t('devices.sensorPreset')"
            emit-value
            map-options
            clearable
            dense
            outlined
            data-testid="sensor-preset"
            @update:model-value="applySensorPreset"
          />
          <div class="row q-col-gutter-sm">
            <q-input
              v-model="sensorAspect"
              :label="t('devices.sensorAspect')"
              :hint="t('devices.sensorAspectHint')"
              dense
              outlined
              class="col-4"
              data-testid="sensor-aspect"
            />
            <q-input
              v-model="sensorDiagonal"
              :label="t('devices.sensorDiagonal')"
              :hint="t('devices.sensorDiagonalHint')"
              dense
              outlined
              class="col-5"
              data-testid="sensor-diagonal"
            />
            <q-select
              :model-value="sensorDiagonalUnit"
              :options="sensorUnitOptions"
              emit-value
              map-options
              dense
              outlined
              class="col-3"
              @update:model-value="convertSensorDiagonal"
            />
          </div>
          <div class="row items-center q-gutter-sm">
            <div
              class="col text-caption"
              data-testid="sensor-calc-text"
            >
              {{ sensorCalcText }}
            </div>
            <q-btn
              v-if="calculatedSensorWidth"
              flat
              dense
              no-caps
              color="primary"
              :label="t('devices.useCalculatedWidth')"
              data-testid="sensor-use-calculated"
              @click="useCalculatedSensorWidth"
            />
          </div>
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
import { apiErrorText } from '@/utils/errors';
import { computed, reactive, ref, watch } from 'vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import { api } from '@/boot/api';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import {
  diagonalToMm,
  findPreset,
  mmToDiagonal,
  parseAspect,
  parseLength,
  SENSOR_PRESETS,
  sensorDiagonalMm,
  sensorWidthFromDiagonal,
} from '@/utils/sensor';
import {
  CAMERA_TYPES,
  CONNECTOR_PRESETS,
  DEVICE_TYPES,
  IO_DEVICE_TYPES,
  POWER_INLETS,
  addConnector,
  deviceForm,
  fillFormFromSpecs,
} from '@/utils/workspace';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  node: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue', 'save']);
const { t } = useI18n();
const $q = useQuasar();
const form = reactive(deviceForm(null));
const typeOptions = computed(() => DEVICE_TYPES.map((v) => ({ value: v, label: t(`devices.types.${v}`) })));

// Picking a Stockwire product brings in its connectors, power inlet, weight and power (see
// docs/stockwire-integration-spec.md section 3.10); nothing is lost if the product has none.
async function importProduct(product) {
  if (!product || typeof product !== 'object') return;
  try {
    const { data } = await api.get(`/stockwire/products/${product.id}/device-specs`);
    fillFormFromSpecs(form, product, data);
  } catch (err) {
    // the product is still chosen; its connectors, inlet and weight have to be filled in by hand
    fillFormFromSpecs(form, product, {});
    $q.notify({ type: 'warning', message: `${t('devices.specsFailed')}: ${apiErrorText(err)}` });
  }
}

// The sensor width a camera needs for its field of view can be typed in mm, picked from a standard
// sensor size, or worked out from the diagonal and aspect ratio printed on the spec sheet (the
// diagonal may be in inches, also as a fraction such as 1/2.3). Only the width is stored; the
// preset, aspect and diagonal are scratch inputs that are cleared when the dialog opens.
const sensorPreset = ref(null);
const sensorAspect = ref('');
const sensorDiagonal = ref('');
const sensorDiagonalUnit = ref('mm');
const sensorPresetOptions = SENSOR_PRESETS.map((p) => ({ value: p.id, label: `${p.label} · ${p.width} × ${p.height} mm` }));
const sensorUnitOptions = [
  { value: 'mm', label: 'mm' },
  { value: 'in', label: 'in' },
];
const calculatedSensorWidth = computed(() => {
  const diagonal = parseLength(sensorDiagonal.value);
  const aspect = parseAspect(sensorAspect.value);
  if (!diagonal || !aspect) return null;
  return sensorWidthFromDiagonal(diagonalToMm(diagonal, sensorDiagonalUnit.value), aspect);
});
const sensorCalcText = computed(() =>
  calculatedSensorWidth.value
    ? t('devices.sensorCalculated', { mm: calculatedSensorWidth.value.toFixed(2) })
    : t('devices.sensorCalcHint'),
);
function formatDiagonal(mm, unit) {
  const digits = unit === 'in' ? 10000 : 100;
  return String(Math.round(mmToDiagonal(mm, unit) * digits) / digits);
}
function applySensorPreset(id) {
  const preset = findPreset(id);
  if (!preset) return;
  form.sensor_width_mm = preset.width;
  sensorAspect.value = preset.aspect;
  sensorDiagonal.value = formatDiagonal(sensorDiagonalMm(preset.width, preset.height), sensorDiagonalUnit.value);
}
// Switching the unit converts the number already typed instead of reinterpreting it.
function convertSensorDiagonal(unit) {
  const diagonal = parseLength(sensorDiagonal.value);
  if (diagonal) sensorDiagonal.value = formatDiagonal(diagonalToMm(diagonal, sensorDiagonalUnit.value), unit);
  sensorDiagonalUnit.value = unit;
}
function useCalculatedSensorWidth() {
  if (calculatedSensorWidth.value) form.sensor_width_mm = Math.round(calculatedSensorWidth.value * 100) / 100;
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    Object.assign(form, deviceForm(props.node));
    sensorPreset.value = null;
    sensorAspect.value = '';
    sensorDiagonal.value = '';
    sensorDiagonalUnit.value = 'mm';
  },
);
</script>

<style scoped>
.device-card {
  width: 760px;
  max-width: 100vw;
}
</style>
