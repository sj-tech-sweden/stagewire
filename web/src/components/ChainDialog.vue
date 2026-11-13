<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="chain-card">
      <q-card-section>
        <div class="text-h6">
          {{ title }}
        </div>
        <div class="text-caption text-grey-6">
          {{ t('workspace.chainHint') }}
        </div>
      </q-card-section>
      <q-card-section
        v-if="direct.length"
        class="q-pt-none"
        data-testid="chain-direct"
      >
        <div class="text-caption text-grey-6 q-mb-xs">
          {{ t('workspace.directConnections') }}
        </div>
        <div
          v-for="(line, i) in direct"
          :key="i"
          class="text-body2"
        >
          {{ line }}
        </div>
      </q-card-section>
      <q-card-section class="q-pt-none">
        <div
          v-for="(step, i) in steps"
          :key="i"
          class="row q-col-gutter-xs items-center q-mb-md chain-step"
          :class="{ 'chain-step-locked': step.locked }"
          data-testid="chain-step"
        >
          <div class="col-auto text-grey-6">
            {{ i + 1 }}
          </div>
          <!-- The soft-patched hop: the device whose socket feeds the mixer strip. It is always the
               last step (source first, analog hops in between), so it cannot be moved, changed or
               removed here; its socket is changed in the console panel's Soft patch tab. -->
          <template v-if="step.locked">
            <div class="col row items-center q-gutter-sm">
              <q-icon
                name="lock"
                color="primary"
              />
              <span
                class="text-subtitle2"
                data-testid="chain-locked-device"
              >{{ deviceName(step.device_id) }}</span>
              <q-badge
                color="primary"
                data-testid="chain-locked-badge"
              >
                {{ t('workspace.softPatchBadge', { label: lock?.label || step.patch_label }) }}
              </q-badge>
            </div>
            <div class="col-auto">
              <q-btn
                flat
                dense
                no-caps
                icon="settings_input_component"
                :label="t('workspace.changeInSoftPatch')"
                data-testid="chain-change-soft-patch"
                @click="emit('open-soft-patch')"
              />
            </div>
            <div class="col-12 text-caption text-grey-6">
              {{ t('workspace.softPatchLockedHint') }}
            </div>
          </template>
          <template v-else>
            <q-select
              v-model="step.device_id"
              class="col"
              dense
              outlined
              emit-value
              map-options
              use-input
              input-debounce="0"
              :options="filtered"
              :label="t('workspace.stepDevice')"
              :hint="isNewDeviceValue(step.device_id) ? t('workspace.newDeviceHint') : ''"
              data-testid="chain-device"
              @filter="filterDevices"
            >
              <template #option="scope">
                <q-item
                  v-bind="scope.itemProps"
                  :data-testid="scope.opt.create ? 'chain-device-create' : undefined"
                >
                  <q-item-section
                    v-if="scope.opt.create"
                    avatar
                  >
                    <q-icon
                      name="add_circle"
                      color="primary"
                    />
                  </q-item-section>
                  <q-item-section>
                    <q-item-label>{{ scope.opt.label }}</q-item-label>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
            <q-btn
              flat
              dense
              round
              icon="edit"
              :disable="!step.device_id || isNewDeviceValue(step.device_id)"
              :aria-label="t('workspace.editDevice')"
              data-testid="chain-edit-device"
              @click="editedId = step.device_id"
            >
              <q-tooltip>{{ t('workspace.editDevice') }}</q-tooltip>
            </q-btn>
            <StockwireProductPicker
              v-if="contextKind === 'job' && stockwire.isEnabled"
              class="col-12 col-sm-4"
              :model-value="null"
              own
              :label="t('workspace.stepFromStockwire')"
              :hint="''"
              data-testid="chain-stockwire"
              @update:model-value="(p) => addFromStockwire(step, p)"
            />
            <div class="col-auto">
              <q-btn
                flat
                dense
                round
                icon="arrow_upward"
                :disable="i === 0 || branching"
                :aria-label="t('workspace.stepUp')"
                @click="move(i, -1)"
              />
              <q-btn
                flat
                dense
                round
                icon="arrow_downward"
                :disable="i === steps.length - 1 || branching || !!steps[i + 1]?.locked"
                :aria-label="t('workspace.stepDown')"
                @click="move(i, 1)"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="close"
                :aria-label="t('workspace.remove')"
                @click="steps.splice(i, 1)"
              />
            </div>
            <div class="col-12 chain-fields-gap" />
            <template
              v-for="field in fields"
              :key="field.key"
            >
              <ConnectorSelect
                v-if="field.key === 'connector'"
                v-model="step.connector"
                class="col-6 col-sm"
                :label="t(field.label)"
                :data-testid="`chain-${field.key}`"
              />
              <q-input
                v-else
                v-model="step[field.key]"
                class="col-6 col-sm"
                dense
                outlined
                :label="t(field.label)"
                :data-testid="`chain-${field.key}`"
              />
            </template>
            <q-select
              v-if="busChannels.length"
              v-model="step.bus_connector"
              class="col-6 col-sm"
              dense
              outlined
              clearable
              use-input
              hide-selected
              fill-input
              new-value-mode="add-unique"
              input-debounce="0"
              :options="busChannels"
              :label="t('workspace.busChannel')"
              data-testid="chain-bus-channel"
              @new-value="(v, done) => done(v.trim(), 'add-unique')"
            />
            <q-select
              v-if="branching && i > 0"
              v-model="step.parent_index"
              class="col-6 col-sm"
              dense
              outlined
              emit-value
              map-options
              clearable
              :options="parentOptions(i)"
              :label="t('workspace.stepFrom')"
            />
          </template>
        </div>
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('workspace.addStep')"
          data-testid="chain-add-step"
          @click="addStep"
        />
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
          :disable="saving || steps.some((s) => !s.device_id)"
          :loading="saving"
          :label="t('workspace.save')"
          data-testid="chain-save"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
  <DeviceEditDialog
    :model-value="!!editedId"
    :device="editedDevice"
    :job-id="jobId"
    :venue-id="venueId"
    @update:model-value="(v) => !v && (editedId = null)"
  />
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { computed, nextTick, ref, watch } from 'vue';
import ConnectorSelect from '@/components/ConnectorSelect.vue';
import DeviceEditDialog from '@/components/DeviceEditDialog.vue';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import { useGraphStore } from '@/stores/graph';
import {
  chainDeviceOptions,
  findDeviceByName,
  isNewDeviceValue,
  newChainDeviceBody,
  newDeviceName,
} from '@/utils/workspace';
import { useStockwireStore } from '@/stores/stockwire';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  initial: { type: Array, default: () => [] },
  // {device_id, label, ...} of a channel's soft-patched hop (see softPatchInfo); the matching step
  // in `initial` is flagged `locked` and stays last
  lock: { type: Object, default: null },
  // Cables made outside the chain (in the inspector), shown read-only so the endpoints are visible.
  direct: { type: Array, default: () => [] },
  devices: { type: Array, default: () => [] },
  jobId: { type: String, default: '' },
  venueId: { type: String, default: '' },
  branching: { type: Boolean, default: false },
  // the channels of the bus an output chain feeds (L, R, C, Sub ...); empty for other chains
  busChannels: { type: Array, default: () => [] },
  fields: {
    type: Array,
    default: () => [
      { key: 'connector', label: 'workspace.stepConnector' },
      { key: 'patch_label', label: 'workspace.stepLabel' },
    ],
  },
});
const emit = defineEmits(['update:modelValue', 'save', 'open-soft-patch']);
const { t } = useI18n();
const graph = useGraphStore();
const stockwire = useStockwireStore();
// A chain can live on a job or a venue base rig; scope graph writes to the right context.
const contextId = computed(() => props.venueId || props.jobId);
const contextKind = computed(() => (props.venueId ? 'venue' : 'job'));
// a step's device can be opened for editing without leaving the chain being edited
const editedId = ref(null);
const editedDevice = computed(() => graph.devices.find((d) => d.id === editedId.value) || null);
const $q = useQuasar();
const steps = ref([]);
const filtered = ref([]);
const saving = ref(false);

const blank = () => ({
  device_id: null,
  connector: '',
  patch_label: '',
  in_port: '',
  out_port: '',
  bus_connector: '',
  notes: '',
  parent_index: null,
});
// The picker's devices, plus a typed-but-not-yet-created device of any step so it keeps showing its
// name after it is chosen (it only becomes a real device on Save).
const options = () => [
  ...props.devices.map((d) => ({ label: d.name, value: d.id })),
  ...steps.value
    .filter((s) => isNewDeviceValue(s.device_id))
    .map((s) => ({ label: `${newDeviceName(s.device_id)} (${t('workspace.newDeviceTag')})`, value: s.device_id })),
];

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    steps.value = props.initial.map((s) => ({ ...s }));
    filtered.value = options();
  },
);

// Searching Stockwire from a patch point: the picked product becomes a device in the job (with
// its connectors and power inlet) and is chosen for this step at once.
async function addFromStockwire(step, product) {
  if (!product) return;
  // A venue base rig doesn't mint Stockwire product devices, so the picker is hidden in venue mode.
  if (contextKind.value === 'venue') return;
  try {
    const created = await graph.createDeviceFromProduct(contextId.value, product);
    await nextTick();
    filtered.value = options();
    if (!filtered.value.some((o) => o.value === created.id)) {
      filtered.value = [...filtered.value, { label: created.name, value: created.id }];
    }
    step.device_id = created.id;
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  }
}

function filterDevices(value, update) {
  update(() => {
    // typing a name that is not a device offers 'Create "<name>"' first; typing the exact name of an
    // existing device offers just that device (no duplicate is made)
    filtered.value = chainDeviceOptions(options(), value, (text) => t('workspace.createDeviceNamed', { text }));
  });
}

function parentOptions(i) {
  return steps.value.slice(0, i).map((_, index) => ({ label: `${t('workspace.stepFrom')} ${index + 1}`, value: index }));
}

const deviceName = (id) => props.devices.find((d) => d.id === id)?.name || graph.devices.find((d) => d.id === id)?.name || '?';

// New steps go BEFORE the locked soft-patched hop, never after it.
function addStep() {
  const at = steps.value.findIndex((s) => s.locked);
  if (at < 0) steps.value.push(blank());
  else steps.value.splice(at, 0, blank());
}

function move(i, delta) {
  const target = i + delta;
  // a step may not be moved onto (or past) the locked soft-patched hop at the end
  const limit = steps.value.findIndex((s) => s.locked);
  if (target < 0 || target >= steps.value.length || (limit >= 0 && target >= limit)) return;
  const [item] = steps.value.splice(i, 1);
  steps.value.splice(target, 0, item);
}

// A typed device is created when the chain is SAVED, not when it is chosen, so cancelling the dialog
// leaves no stray devices behind. Each step's id is replaced by the new device's id right away, so a
// second press of Save (or a retry after a failure part-way) reuses what was already made instead of
// creating it again. A name that matches an existing device picks that device.
async function materialise() {
  for (const step of steps.value) {
    if (!isNewDeviceValue(step.device_id)) continue;
    const name = newDeviceName(step.device_id);
    const existing = findDeviceByName(props.devices, name) || findDeviceByName(graph.devices, name);
    if (existing) {
      step.device_id = existing.id;
      continue;
    }
    const created = await graph.createAudioDevice(contextId.value, newChainDeviceBody(name));
    step.device_id = created.id;
  }
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    await materialise();
    emit('save', cleaned());
  } catch (err) {
    $q.notify({ type: 'negative', message: apiErrorText(err) });
  } finally {
    saving.value = false;
  }
}

function cleaned() {
  // the locked hop is always sent last, whatever happened to the editable steps
  const ordered = [...steps.value.filter((s) => !s.locked), ...steps.value.filter((s) => s.locked)];
  return ordered.map((s) => ({
    device_id: s.device_id,
    ...Object.fromEntries(props.fields.map((f) => [f.key, s[f.key] || ''])),
    notes: s.notes || '',
    ...(props.busChannels.length ? { bus_connector: s.bus_connector || null } : {}),
    ...(props.branching ? { parent_index: s.parent_index ?? null } : {}),
  }));
}
</script>

<style scoped>
.chain-card {
  width: 860px;
  max-width: 100vw;
}
.chain-step-locked {
  border-left: 3px solid var(--q-primary);
  padding-left: 8px;
}
</style>
