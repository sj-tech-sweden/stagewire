<template>
  <div class="dmx-grid">
    <div class="row items-center q-mb-xs">
      <div class="col text-caption text-grey-7">
        {{ t('lights.gridSummary', { universe, used: usedCount }) }}
      </div>
      <q-btn
        flat
        dense
        icon="auto_fix_high"
        :label="t('lights.firstFree')"
        :disable="firstFree === null"
        @click="emit('update:modelValue', firstFree)"
      />
    </div>
    <div class="dmx-cells">
      <button
        v-for="c in channels"
        :key="c"
        type="button"
        class="dmx-cell"
        :class="{
          'dmx-cell--taken': taken.has(c),
          'dmx-cell--selected': selected.has(c),
        }"
        :title="titleOf(c)"
        :aria-label="`${t('lights.channel')} ${c}`"
        @click="emit('update:modelValue', c)"
      >
        {{ c }}
      </button>
    </div>
    <div class="text-caption text-grey-7 q-mt-xs">
      {{ t('lights.gridHint') }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { DMX_CHANNELS, firstFreeAddress, footprintOf, occupiedChannels } from '@/utils/dmx';

const props = defineProps({
  modelValue: { type: Number, default: null },
  fixtures: { type: Array, default: () => [] },
  universe: { type: Number, default: 1 },
  footprint: { type: Number, default: 1 },
  excludeId: { type: String, default: null },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n({ useScope: 'global' });

const channels = Array.from({ length: DMX_CHANNELS }, (_, i) => i + 1);
const taken = computed(() => occupiedChannels(props.fixtures, props.universe, props.excludeId));
const usedCount = computed(() => taken.value.size);
const firstFree = computed(() =>
  firstFreeAddress(props.fixtures, props.universe, props.footprint, props.excludeId),
);
const selected = computed(() => {
  const set = new Set();
  if (props.modelValue) {
    for (let c = props.modelValue; c < props.modelValue + footprintOf({ footprint: props.footprint }); c += 1) {
      set.add(c);
    }
  }
  return set;
});

function titleOf(c) {
  const f = taken.value.get(c);
  if (!f) return `${c}`;
  return `${c} · ${f.device_name || t('lights.fixtureSection')} (${f.dmx_address}–${f.dmx_address + footprintOf(f) - 1})`;
}
</script>

<style scoped>
.dmx-cells {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(32px, 1fr));
  gap: 2px;
  max-height: 260px;
  overflow-y: auto;
}
.dmx-cell {
  font-size: 10px;
  height: 24px;
  border: 1px solid rgba(128, 128, 128, 0.35);
  background: transparent;
  color: inherit;
  cursor: pointer;
  border-radius: 3px;
}
.dmx-cell--taken {
  background: rgba(244, 67, 54, 0.28);
}
.dmx-cell--selected {
  background: var(--q-primary, #3f873f);
  color: #fff;
}
</style>
