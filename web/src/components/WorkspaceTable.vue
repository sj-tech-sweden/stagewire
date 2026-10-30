<template>
  <div>
    <q-list
      v-if="$q.screen.lt.sm"
      separator
    >
      <q-item
        v-for="device in devices"
        :key="device.id"
        clickable
        :active="device.id === selectedId"
        @click="emit('select', device.id)"
      >
        <q-item-section>
          <q-item-label>{{ device.name }}</q-item-label>
          <q-item-label caption>
            {{ device.domain }} · {{ device.kind || '—' }}
          </q-item-label>
          <q-item-label
            v-if="device.notes"
            caption
          >
            {{ device.notes }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-badge
            v-if="needsBookingRequest(device)"
            color="warning"
            text-color="black"
            :label="t('workspace.unbooked')"
          />
          <q-badge
            v-else-if="device.stockwire_booked"
            color="positive"
            :label="t('workspace.booked')"
          />
        </q-item-section>
      </q-item>
    </q-list>

    <q-table
      v-else
      flat
      dense
      virtual-scroll
      :virtual-scroll-item-size="44"
      :rows="devices"
      :columns="columns"
      row-key="id"
      :rows-per-page-options="[0]"
      hide-bottom
      class="sticky-header-table"
      style="max-height: 70vh"
      data-testid="workspace-table"
      @row-click="(_, row) => emit('select', row.id)"
    >
      <template #body-cell-name="slot">
        <q-td
          :props="slot"
          :class="{ 'bg-selected': slot.row.id === selectedId }"
        >
          <q-input
            :model-value="slot.row.name"
            dense
            borderless
            @click.stop
            @change="(v) => save(slot.row, { name: v })"
          />
        </q-td>
      </template>
      <template #body-cell-notes="slot">
        <q-td :props="slot">
          <q-input
            :model-value="slot.row.notes"
            dense
            borderless
            @click.stop
            @change="(v) => save(slot.row, { notes: v })"
          />
        </q-td>
      </template>
      <template #body-cell-stockwire="slot">
        <q-td :props="slot">
          <q-btn
            v-if="needsBookingRequest(slot.row)"
            dense
            no-caps
            color="warning"
            text-color="black"
            icon="add_shopping_cart"
            :label="t('workspace.requestAdd')"
            @click.stop="emit('request-booking', slot.row)"
          />
          <q-badge
            v-else-if="slot.row.stockwire_booked"
            color="positive"
            :label="t('workspace.booked')"
          />
          <span
            v-else-if="slot.row.stockwire_product_name"
            class="text-grey-6"
          >{{ slot.row.stockwire_product_name }}</span>
        </q-td>
      </template>
    </q-table>
  </div>
</template>

<script setup>
import { isRevisionConflict } from '@/utils/graph';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { isPowerNode, needsBookingRequest, powerInletLabel } from '@/utils/workspace';

const props = defineProps({
  jobId: { type: String, required: true },
  devices: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
});
const emit = defineEmits(['select', 'request-booking']);

const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();

const columns = computed(() => [
  { name: 'name', label: t('workspace.colName'), field: 'name', align: 'left' },
  { name: 'domain', label: t('workspace.colDomain'), field: 'domain', align: 'left' },
  { name: 'kind', label: t('workspace.colKind'), field: 'kind', align: 'left' },
  { name: 'inlet', label: t('workspace.colInlet'), field: (row) => (isPowerNode(row) ? '' : powerInletLabel(row.attributes?.power_inlet)), align: 'left' },
  { name: 'stockwire', label: t('workspace.colStockwire'), field: 'stockwire_product_name', align: 'left' },
  { name: 'notes', label: t('workspace.colNotes'), field: 'notes', align: 'left' },
]);

async function save(row, changes) {
  try {
    await graph.updateDevice(props.jobId, row.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
    }
  }
}
</script>
