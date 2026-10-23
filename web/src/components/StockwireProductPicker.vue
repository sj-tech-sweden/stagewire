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
          </q-item-label>
        </q-item-section>
      </q-item>
    </template>
    <template #no-option>
      <q-item>
        <q-item-section class="text-grey">
          {{ t('stockwire.typeToSearch') }}
        </q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup>
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useStockwireStore } from '@/stores/stockwire';

const props = defineProps({
  modelValue: { type: Object, default: null },
  gearType: { type: String, default: null },
  label: { type: String, default: 'Product' },
  hint: { type: String, default: null },
});
const emit = defineEmits(['update:modelValue']);

const { t } = useI18n({ useScope: 'global' });
const store = useStockwireStore();

const options = ref([]);

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
  };
}

async function searchCatalog(q) {
  const cats = store.categoriesForGearType(props.gearType);
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
  try {
    items = await searchCatalog(q);
  } catch {
    items = [];
  }
  update(() => {
    options.value = [{ __freetext: true, name: q }, ...items];
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
