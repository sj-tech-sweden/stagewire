<template>
  <div data-testid="device-editor">
    <div class="row items-center q-mb-md">
      <div class="text-subtitle1 col">
        {{ t('devices.title') }}
      </div>
      <q-btn
        color="primary"
        no-caps
        icon="add"
        :label="t('devices.createDevice')"
        data-testid="new-device"
        @click="openDialog(null)"
      />
    </div>

    <div
      v-if="!gear.length"
      class="text-grey-6"
    >
      {{ t('workspace.noGear') }}
    </div>

    <q-list
      v-else-if="$q.screen.lt.sm"
      bordered
      separator
    >
      <q-item
        v-for="device in gear"
        :key="device.id"
        clickable
        @click="openDialog(device)"
      >
        <q-item-section>
          <q-item-label>{{ device.name }}</q-item-label>
          <q-item-label caption>
            {{ typeLabel(device) }} · {{ portsLabel(device) }}
          </q-item-label>
        </q-item-section>
      </q-item>
    </q-list>

    <q-table
      v-else
      flat
      dense
      bordered
      virtual-scroll
      :virtual-scroll-item-size="44"
      :rows="gear"
      :columns="columns"
      row-key="id"
      :rows-per-page-options="[0]"
      hide-bottom
      class="sticky-header-table"
      style="max-height: 70vh"
      data-testid="device-table"
    >
      <template #body-cell-name="slot">
        <q-td :props="slot">
          <q-input
            :model-value="slot.row.name"
            dense
            borderless
            @change="(v) => quickSave(slot.row, { name: v })"
          />
        </q-td>
      </template>
      <template #body-cell-type="slot">
        <q-td :props="slot">
          {{ typeLabel(slot.row) }}
        </q-td>
      </template>
      <template #body-cell-ports="slot">
        <q-td :props="slot">
          {{ portsLabel(slot.row) }}
        </q-td>
      </template>
      <template #body-cell-io="slot">
        <q-td :props="slot">
          <span v-if="effective(slot.row)">
            {{ effective(slot.row).input_count ?? '–' }} / {{ effective(slot.row).output_count ?? '–' }}
          </span>
        </q-td>
      </template>
      <template #body-cell-weight="slot">
        <q-td :props="slot">
          {{ effective(slot.row)?.weight_kg_effective ?? '' }}
          <q-badge
            v-if="effective(slot.row)?.weight_source === 'stockwire' && stockwire.isEnabled"
            color="teal"
            label="SW"
          />
        </q-td>
      </template>
      <template #body-cell-power="slot">
        <q-td :props="slot">
          {{ effective(slot.row)?.power_watts_effective ?? '' }}
          <q-badge
            v-if="effective(slot.row)?.power_source === 'stockwire' && stockwire.isEnabled"
            color="teal"
            label="SW"
          />
        </q-td>
      </template>
      <template #body-cell-inlet="slot">
        <q-td :props="slot">
          <q-select
            :model-value="slot.row.attributes?.power_inlet || 'iec_c13'"
            :options="POWER_INLETS"
            emit-value
            map-options
            dense
            borderless
            data-testid="device-inlet"
            @update:model-value="(v) => saveInlet(slot.row, v)"
          />
          <div
            v-if="pluggedInto(slot.row)"
            class="text-caption text-grey-6"
          >
            → {{ pluggedInto(slot.row) }}
          </div>
        </q-td>
      </template>
      <template #body-cell-patched="slot">
        <q-td :props="slot">
          {{ effective(slot.row)?.patch_point_count || '' }}
        </q-td>
      </template>
      <template #body-cell-actions="slot">
        <q-td :props="slot">
          <q-btn
            flat
            dense
            round
            icon="edit"
            :aria-label="t('app.actions.edit')"
            data-testid="edit-device"
            @click="openDialog(slot.row)"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="remove(slot.row)"
          />
        </q-td>
      </template>
    </q-table>

    <DeviceDialog
      v-model="dialogOpen"
      :node="editing"
      :effective="editing ? graph.effective[editing.id] : null"
      :job-id="props.jobId"
      @save="save"
    />
  </div>
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { useStockwireStore } from '@/stores/stockwire';
import DeviceDialog from '@/components/DeviceDialog.vue';
import { POWER_INLETS, connectorLabel, deviceCreateBody, devicePatch, isGear, portGroups } from '@/utils/workspace';

// A venue's Standard Base Rig reuses this editor, so it accepts an optional `venueId`; store calls
// route by the active graph scope, so passing the right id (venue when present, else job) is enough.
const props = defineProps({
  jobId: { type: String, default: null },
  venueId: { type: String, default: null },
});
const scopeId = computed(() => props.venueId || props.jobId);
const { t, te } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const stockwire = useStockwireStore();
const dialogOpen = ref(false);
const editing = ref(null);

const gear = computed(() =>
  graph.devices.filter((d) => isGear(d) && d.kind !== 'case').sort((a, b) => a.name.localeCompare(b.name)),
);
const columns = computed(() => [
  { name: 'name', label: t('devices.name'), field: 'name', align: 'left' },
  { name: 'type', label: t('devices.type'), field: 'kind', align: 'left' },
  { name: 'ports', label: t('devices.ports'), field: () => '', align: 'left' },
  { name: 'io', label: `${t('devices.inputs')} / ${t('devices.outputs')}`, field: () => '', align: 'left' },
  { name: 'weight', label: t('devices.weight'), field: () => '', align: 'right' },
  { name: 'power', label: t('devices.power'), field: () => '', align: 'right' },
  { name: 'inlet', label: t('workspace.colInlet'), field: () => '', align: 'left' },
  { name: 'patched', label: t('workspace.chain'), field: () => '', align: 'right' },
  { name: 'actions', label: '', field: () => '', align: 'right' },
]);

const effective = (device) => graph.effective[device.id];
// A device's kind is one of our types or, for gear imported from Stockwire, the free-text category
// it came with ("Microphones"), which has no translation: show it as it is instead of a missing key.
const typeLabel = (device) => {
  if (!device.kind) return '';
  const key = `devices.types.${device.kind}`;
  return te(key) ? t(key) : device.kind;
};
const portsLabel = (device) =>
  portGroups(device.ports)
    .map((g) => `${{ in: '↓', out: '↑', both: '↕' }[g.direction]}${g.count || ''} ${connectorLabel(g.connector)}`.trim())
    .join(', ');

// A device's power inlet is edited in the table; where it is plugged in comes from its node.
const pluggedInto = (device) =>
  graph.devices.find((d) => d.id === device.attributes?.power_node_id)?.name || '';
async function saveInlet(device, value) {
  try {
    await graph.updateDevice(scopeId.value, device.id, { attributes: { power_inlet: value } });
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}

const refresh = () => graph.fetchEffective(scopeId.value).catch(() => {});
onMounted(refresh);
watch(() => graph.devices.length, refresh);

const failed = (err) =>
  $q.notify({ type: 'negative', message: apiErrorText(err) });

function openDialog(device) {
  editing.value = device;
  dialogOpen.value = true;
}

async function quickSave(device, changes) {
  try {
    await graph.updateDevice(scopeId.value, device.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}

async function save(form) {
  try {
    if (editing.value) {
      await graph.updateDevice(scopeId.value, editing.value.id, devicePatch(editing.value, form));
    } else {
      await graph.createAudioDevice(scopeId.value, deviceCreateBody(form));
    }
    dialogOpen.value = false;
    refresh();
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}

function remove(device) {
  $q.dialog({ title: t('workspace.remove'), message: device.name, cancel: true, persistent: true }).onOk(
    async () => {
      try {
        await graph.deleteDevice(scopeId.value, device.id);
      } catch (err) {
        if (err.response?.status === 409) {
          $q.notify({ type: 'warning', message: t('workspace.deviceInUse') });
        } else {
          failed(err);
        }
      }
    },
  );
}
</script>
