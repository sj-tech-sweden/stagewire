<template>
  <q-dialog
    :model-value="modelValue"
    :position="$q.screen.lt.sm ? 'standard' : 'right'"
    :maximized="$q.screen.lt.sm"
    :seamless="$q.screen.gt.xs"
    full-height
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="catalog-card column no-wrap">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 col">
          {{ t('workspace.catalog') }}
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
        <q-input
          v-model="store.q"
          dense
          outlined
          clearable
          debounce="300"
          :label="t('workspace.search')"
          data-testid="catalog-search"
          @update:model-value="run"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
        <div class="row q-col-gutter-sm">
          <q-select
            v-model="store.categories"
            class="col-12 col-sm-6"
            dense
            outlined
            multiple
            use-chips
            :options="Object.keys(store.facets.category)"
            :label="t('workspace.category')"
            @update:model-value="run"
          />
          <q-select
            v-model="store.manufacturers"
            class="col-12 col-sm-6"
            dense
            outlined
            multiple
            use-chips
            :options="Object.keys(store.facets.manufacturer)"
            :label="t('workspace.manufacturer')"
            @update:model-value="run"
          />
        </div>
        <q-toggle
          v-model="store.inStockOnly"
          dense
          :label="t('workspace.inStock')"
        />
        <div
          v-if="!store.dateRangeSupported"
          class="text-caption text-grey-6"
        >
          {{ t('workspace.noDateFilter') }}
        </div>
      </q-card-section>

      <q-separator />
      <div class="row items-center q-px-md q-py-xs text-caption">
        <span class="col">{{ t('workspace.results', { n: store.visibleItems.length }) }}</span>
        <q-btn
          flat
          dense
          no-caps
          :label="t('workspace.selectAll')"
          @click="selectVisible"
        />
        <q-btn
          flat
          dense
          no-caps
          :label="t('workspace.clear')"
          @click="store.clearSelection()"
        />
      </div>

      <q-banner
        v-if="store.error"
        class="bg-negative text-white"
        dense
      >
        {{ store.error }}
      </q-banner>
      <q-linear-progress
        v-if="store.loading"
        indeterminate
      />

      <q-virtual-scroll
        class="col"
        :items="store.visibleItems"
        :virtual-scroll-item-size="64"
        separator
      >
        <template #default="{ item }">
          <q-item
            :key="item.id"
            v-ripple
            clickable
            data-testid="catalog-item"
            :draggable="$q.screen.gt.xs"
            @dragstart="(e) => onDragStart(e, item)"
            @click="store.toggle(item.id)"
          >
            <q-item-section avatar>
              <q-checkbox
                :model-value="!!store.selected[item.id]"
                @update:model-value="store.toggle(item.id)"
              />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ item.name }}</q-item-label>
              <q-item-label caption>
                {{ [item.manufacturer, item.category].filter(Boolean).join(' · ') }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-badge
                v-if="item.booked"
                color="positive"
                :label="`${t('workspace.bookedOnJob')} ×${item.booked_qty}`"
              />
              <q-item-label caption>
                {{ t('workspace.available') }}: {{ item.available_qty ?? '–' }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </template>
      </q-virtual-scroll>

      <q-separator />
      <q-expansion-item
        dense
        icon="inventory_2"
        :label="t('workspace.caseTitle')"
        @show="loadCases"
      >
        <div class="q-px-sm q-pt-sm text-caption text-grey-6">
          {{ t('workspace.caseHint') }}
        </div>
        <div class="row q-pa-sm q-col-gutter-sm items-center">
          <q-select
            v-model="caseId"
            class="col"
            dense
            outlined
            emit-value
            map-options
            :options="caseOptions"
            :label="t('workspace.caseId')"
            data-testid="case-select"
          />
          <q-btn
            color="primary"
            no-caps
            :disable="!caseId"
            :label="t('workspace.caseAdd')"
            @click="addCase"
          />
        </div>
      </q-expansion-item>

      <q-card-actions>
        <q-btn
          class="full-width"
          color="primary"
          no-caps
          :disable="!store.selectedItems.length || adding"
          :loading="adding"
          :label="t('workspace.addSelected', { n: store.selectedItems.length })"
          data-testid="catalog-add"
          @click="addSelected"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useCatalogStore } from '@/stores/catalog';
import { useGraphStore } from '@/stores/graph';
import { PRODUCT_MIME, deviceFromProduct } from '@/utils/workspace';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  jobId: { type: String, required: true },
  stockwireJobId: { type: String, default: null },
});
const emit = defineEmits(['update:modelValue']);

const { t } = useI18n();
const $q = useQuasar();
const store = useCatalogStore();
const graph = useGraphStore();
const caseId = ref(null);
const caseOptions = ref([]);
const adding = ref(false);

const run = () => store.search(props.stockwireJobId);

watch(
  () => props.modelValue,
  (open) => {
    if (open) run();
  },
);

async function loadCases() {
  try {
    const cases = await store.cases();
    caseOptions.value = cases.map((c) => ({
      label: `${c.name || c.asset_tag} (${c.child_count})`,
      value: c.id,
    }));
  } catch {
    caseOptions.value = [];
  }
}

function onDragStart(event, item) {
  const payload = store.selected[item.id] ? store.selectedItems : [item];
  event.dataTransfer.setData(PRODUCT_MIME, JSON.stringify(payload));
  event.dataTransfer.effectAllowed = 'copy';
}

function selectVisible() {
  const next = { ...store.selected };
  store.visibleItems.forEach((item) => {
    next[item.id] = true;
  });
  store.selected = next;
}

async function addSelected() {
  adding.value = true;
  try {
    const created = await graph.createDevices(
      props.jobId,
      store.selectedItems.map((item) => deviceFromProduct(item)),
    );
    store.clearSelection();
    $q.notify({ type: 'positive', message: t('workspace.added', { n: created.length }) });
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
  } finally {
    adding.value = false;
  }
}

async function addCase() {
  adding.value = true;
  try {
    const children = await store.caseChildren(caseId.value);
    if (!children.length) {
      $q.notify({ type: 'warning', message: t('workspace.caseEmpty') });
      return;
    }
    const parent = await graph.createDevice(props.jobId, {
      domain: 'other',
      kind: 'case',
      name: caseOptions.value.find((o) => o.value === caseId.value)?.label.replace(/ \(\d+\)$/, '') || `Case ${caseId.value}`,
      stockwire_device_id: String(caseId.value),
      ports: [],
      attributes: {},
    });
    const created = await graph.createDevices(
      props.jobId,
      children.map((child) =>
        deviceFromProduct(
          { ...child.product, device_id: child.id, category: child.product?.category },
          { parentId: parent.id },
        ),
      ),
    );
    $q.notify({ type: 'positive', message: t('workspace.added', { n: created.length + 1 }) });
    caseId.value = null;
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || err.message });
  } finally {
    adding.value = false;
  }
}
</script>

<style scoped>
.catalog-card {
  width: 480px;
  max-width: 100vw;
}
</style>
