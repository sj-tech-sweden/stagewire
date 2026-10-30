<template>
  <div data-testid="lights-editor">
    <div class="row items-center q-mb-md q-gutter-sm">
      <div class="text-subtitle1 col">
        {{ t('lights.title') }}
      </div>
      <q-btn
        color="primary"
        no-caps
        icon="add"
        :label="t('workspace.addFixture')"
        data-testid="add-fixture"
        @click="addFixtures(1)"
      />
      <q-btn
        flat
        no-caps
        icon="playlist_add"
        :label="t('workspace.addFixtures', { n: 8 })"
        @click="addFixtures(8)"
      />
    </div>

    <div
      v-if="!fixtures.length"
      class="text-grey-6"
    >
      {{ t('workspace.noFixtures') }}
    </div>

    <q-list
      v-else-if="$q.screen.lt.sm"
      bordered
      separator
    >
      <q-item
        v-for="fixture in fixtures"
        :key="fixture.id"
      >
        <q-item-section>
          <q-item-label>{{ fixture.name }}</q-item-label>
          <q-item-label caption>
            U{{ fixture.attributes.universe ?? '–' }} · {{ fixture.attributes.dmx_address ?? '–' }}
            · {{ fixture.attributes.footprint ?? 1 }} ch · {{ fixture.attributes.fixture_type || '' }}
          </q-item-label>
          <q-item-label
            v-if="flagsOf(fixture).conflict || flagsOf(fixture).overflow"
            class="text-negative"
            caption
          >
            {{ flagsOf(fixture).conflict ? t('lights.conflict') : t('lights.overflow') }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('workspace.remove')"
            @click="remove(fixture)"
          />
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
      :rows="fixtures"
      :columns="columns"
      row-key="id"
      :rows-per-page-options="[0]"
      hide-bottom
      style="max-height: 560px"
      data-testid="fixture-table"
    >
      <template
        v-for="field in numberFields"
        #[`body-cell-${field}`]="slot"
        :key="field"
      >
        <q-td :props="slot">
          <q-input
            :model-value="slot.row.attributes[field]"
            dense
            borderless
            type="number"
            style="width: 76px"
            :data-testid="`fixture-${field}`"
            @change="(v) => saveAttr(slot.row, field, v === '' ? null : Number(v))"
          />
        </q-td>
      </template>
      <template
        v-for="field in textFields"
        #[`body-cell-${field}`]="slot"
        :key="field"
      >
        <q-td :props="slot">
          <q-input
            :model-value="slot.row.attributes[field]"
            dense
            borderless
            @change="(v) => saveAttr(slot.row, field, v || null)"
          />
        </q-td>
      </template>
      <template #body-cell-check="slot">
        <q-td :props="slot">
          <q-icon
            v-if="flagsOf(slot.row).conflict"
            name="warning"
            color="negative"
            data-testid="dmx-conflict"
          >
            <q-tooltip>{{ t('lights.conflict') }}</q-tooltip>
          </q-icon>
          <q-icon
            v-if="flagsOf(slot.row).overflow"
            name="error"
            color="negative"
            data-testid="dmx-overflow"
          >
            <q-tooltip>{{ t('lights.overflow') }}</q-tooltip>
          </q-icon>
        </q-td>
      </template>
      <template #body-cell-actions="slot">
        <q-td :props="slot">
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
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useGraphStore } from '@/stores/graph';
import { dmxFlags } from '@/utils/dmx';
import { fixtureView, fixturesOf } from '@/utils/workspace';

const props = defineProps({ jobId: { type: String, required: true } });
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();

const numberFields = ['universe', 'dmx_address', 'footprint'];
const textFields = ['fixture_type', 'channel_mode', 'location', 'gel', 'purpose'];
const fixtures = computed(() => fixturesOf(graph.devices));
const flags = computed(() => dmxFlags(fixtures.value.map(fixtureView)));
const flagsOf = (fixture) => flags.value.get(fixture.id) || { conflict: false, overflow: false };

const columns = computed(() => [
  { name: 'name', label: t('workspace.colName'), field: 'name', align: 'left' },
  { name: 'universe', label: t('lights.colUniverse'), field: () => '', align: 'left' },
  { name: 'dmx_address', label: t('lights.colAddress'), field: () => '', align: 'left' },
  { name: 'fixture_type', label: t('lights.colFixtureType'), field: () => '', align: 'left' },
  { name: 'channel_mode', label: t('lights.colChannelMode'), field: () => '', align: 'left' },
  { name: 'footprint', label: t('lights.colFootprint'), field: () => '', align: 'left' },
  { name: 'location', label: t('lights.colLocation'), field: () => '', align: 'left' },
  { name: 'gel', label: t('lights.colGel'), field: () => '', align: 'left' },
  { name: 'purpose', label: t('lights.colPurpose'), field: () => '', align: 'left' },
  { name: 'check', label: t('lights.colStatus'), field: () => '', align: 'center' },
  { name: 'actions', label: '', field: () => '', align: 'right' },
]);

const failed = (err) =>
  $q.notify({ type: 'negative', message: err.response?.data?.detail?.message || err.response?.data?.detail || err.message });

async function saveAttr(node, key, value) {
  try {
    await graph.updateDevice(props.jobId, node.id, { attributes: { ...node.attributes, [key]: value } });
  } catch (err) {
    if (err.response?.status !== 409) failed(err);
  }
}

async function addFixtures(count) {
  try {
    for (let i = 0; i < count; i += 1) {
      await graph.createFixture(props.jobId, { footprint: 1 });
    }
  } catch (err) {
    failed(err);
  }
}

function remove(fixture) {
  $q.dialog({ title: t('workspace.remove'), message: fixture.name, cancel: true, persistent: true }).onOk(
    async () => {
      try {
        await graph.deleteDevice(props.jobId, fixture.id);
      } catch (err) {
        if (err.response?.status !== 409) failed(err);
      }
    },
  );
}
</script>
