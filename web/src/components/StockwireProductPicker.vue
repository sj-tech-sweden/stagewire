<template>
  <q-select
    :model-value="modelValue"
    :options="options"
    :label="label"
    :hint="hint === null ? t('stockwire.pickerHint') : hint"
    use-input
    input-debounce="300"
    clearable
    dense
    :option-label="optionLabel"
    :option-value="optionValue"
    @filter="onFilter"
    @update:model-value="onPick"
    @clear="onClear"
  >
    <template #option="scope">
      <q-item
        v-bind="scope.itemProps"
        :class="{ 'text-primary': scope.opt.__freetext }"
      >
        <q-item-section>
          <q-item-label>{{ scope.opt.__freetext ? t('stockwire.useTyped', { text: scope.opt.name }) : scope.opt.name }}</q-item-label>
          <q-item-label
            v-if="!scope.opt.__freetext"
            caption
          >
            <span v-if="scope.opt.category">{{ scope.opt.category }}</span>
            <span v-if="scope.opt.brand"> · {{ scope.opt.brand }}</span>
            <span v-if="scope.opt.manufacturer"> · {{ scope.opt.manufacturer }}</span>
            <span v-if="scope.opt.sku"> · {{ scope.opt.sku }}</span>
            <span v-if="scope.opt.__local">{{ t('stockwire.inThisJob') }}</span>
            <span v-if="scope.opt.device_count != null"> · ×{{ scope.opt.device_count }}</span>
          </q-item-label>
        </q-item-section>
      </q-item>
    </template>
    <template #no-option>
      <q-item>
        <q-item-section class="text-grey">
          {{ searchFailed ? `${t('stockwire.searchFailed')}: ${searchFailed}` : t('stockwire.typeToSearch') }}
        </q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup>
import { ref } from 'vue';
import { Notify } from 'quasar';
import { apiErrorText } from '@/utils/errors';
import { useI18n } from 'vue-i18n';
import { useStockwireStore } from '@/stores/stockwire';

const props = defineProps({
  modelValue: { type: Object, default: null },
  gearType: { type: String, default: null },
  label: { type: String, default: 'Product' },
  hint: { type: String, default: null },
  // list the company's own equipment (products with devices, the device count is the quantity)
  // instead of every product in the Stockwire catalog
  own: { type: Boolean, default: false },
  // things already in the job to offer first: [{ id, name, stockwire_product_id }]
  localItems: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue']);

const { t } = useI18n({ useScope: 'global' });
const store = useStockwireStore();

const options = ref([]);
const searchFailed = ref('');

const optionLabel = (o) => (o && typeof o === 'object' ? o.name || '' : String(o ?? ''));
const optionValue = (o) => (o && typeof o === 'object' ? `${o.id ?? ''}|${o.name ?? ''}` : String(o ?? ''));

function freetext(name) {
  return { id: null, name, sku: null, brand: null, manufacturer: null, category_id: null, category: null };
}

function toOption(p) {
  return {
    id: String(p.id),
    name: p.name,
    sku: p.sku,
    brand: p.brand,
    manufacturer: p.manufacturer,
    category_id: p.category_id,
    category: store.categoryPath(p.category_id) || p.category,
    device_count: p.device_count ?? null,
  };
}

async function searchCatalog(q) {
  const cats = store.categoriesForGearType(props.gearType);
  if (props.own) {
    const res = await store.searchOwnProducts({ search: q, limit: 20, ...(cats.length ? { category_id: cats } : {}) });
    return (res.items || []).map(toOption);
  }
  const base = { search: q, limit: 20 };
  const groups = cats.length
    ? await Promise.all(cats.map((id) => store.searchProducts({ ...base, category_id: id })))
    : [await store.searchProducts(base)];
  const seen = new Set();
  const out = [];
  for (const res of groups) {
    for (const p of res.items || []) {
      if (!seen.has(p.id)) {
        seen.add(p.id);
        out.push(toOption(p));
      }
    }
  }
  return out;
}

async function onFilter(val, update) {
  const q = (val || '').trim();
  if (!q) {
    update(() => {
      options.value = [];
    });
    return;
  }
  if (!Object.keys(store.categoryMap).length) {
    try {
      await store.loadCategoryMap();
    } catch {
      /* ignore */
    }
  }
  if (!store.categories.length) {
    try {
      await store.loadCategories();
    } catch {
      /* ignore */
    }
  }
  let items = [];
  searchFailed.value = '';
  try {
    items = await searchCatalog(q);
  } catch (err) {
    // not "no results": say the search itself failed (the typed text can still be used)
    searchFailed.value = apiErrorText(err);
    Notify.create({ type: 'warning', message: `${t('stockwire.searchFailed')}: ${searchFailed.value}` });
  }
  const needle = q.toLowerCase();
  const local = props.localItems
    .filter((d) => d.name.toLowerCase().includes(needle))
    .map((d) => ({ __local: true, id: d.stockwire_product_id || null, name: d.name, job_device_id: d.id, sku: null }));
  update(() => {
    options.value = [{ __freetext: true, name: q }, ...local, ...items];
  });
}

function onPick(value) {
  if (!value) {
    emit('update:modelValue', null);
    return;
  }
  if (typeof value === 'string') {
    emit('update:modelValue', freetext(value.trim()));
    return;
  }
  if (value.__freetext) {
    emit('update:modelValue', freetext(value.name));
    return;
  }
  emit('update:modelValue', {
    job_device_id: value.job_device_id || null,
    id: value.id,
    name: value.name,
    sku: value.sku,
    brand: value.brand,
    manufacturer: value.manufacturer,
    category_id: value.category_id,
    category: value.category,
  });
}

function onClear() {
  emit('update:modelValue', null);
}
</script>
