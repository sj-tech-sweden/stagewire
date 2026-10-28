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
    <div
      v-if="check.clashes.length || check.overflow"
      class="text-negative text-caption q-mb-xs"
    >
      <span v-if="check.clashes.length">
        {{ t('lights.clashesWith', { names: clashNames }) }}
      </span>
      <span v-if="check.overflow">
        {{ t('lights.pastChannel512') }}
      </span>
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
          'dmx-cell--clash': selected.has(c) && taken.has(c),
          'dmx-cell--was': was.has(c),
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
import {
  clashesFor,
  DMX_CHANNELS,
  firstFreeAddress,
  footprintOf,
  occupiedChannels,
} from '@/utils/dmx';

const props = defineProps({
  modelValue: { type: Number, default: null },
  fixtures: { type: Array, default: () => [] },
  universe: { type: Number, default: 1 },
  footprint: { type: Number, default: 1 },
  excludeId: { type: String, default: null },
  // The address the fixture has now, shown as an outline while the new address is chosen.
  originalAddress: { type: Number, default: null },
});
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n({ useScope: 'global' });

const channels = Array.from({ length: DMX_CHANNELS }, (_, i) => i + 1);
const taken = computed(() => occupiedChannels(props.fixtures, props.universe, props.excludeId));
const usedCount = computed(() => taken.value.size);
const firstFree = computed(() =>
  firstFreeAddress(props.fixtures, props.universe, props.footprint, props.excludeId),
);

const span = (start, width) => {
  const set = new Set();
  if (start) for (let c = start; c < start + width && c <= DMX_CHANNELS; c += 1) set.add(c);
  return set;
};
const selected = computed(() => span(props.modelValue, footprintOf({ footprint: props.footprint })));
const was = computed(() =>
  props.originalAddress && props.originalAddress !== props.modelValue
    ? span(props.originalAddress, footprintOf({ footprint: props.footprint }))
    : new Set(),
);
const check = computed(() =>
  clashesFor(props.fixtures, props.universe, props.modelValue, props.footprint, props.excludeId),
);
const clashNames = computed(() =>
  check.value.clashes
    .map((f) => `${f.device_name || t('lights.fixtureSection')} (${f.dmx_address}–${f.dmx_address + footprintOf(f) - 1})`)
    .join(', '),
);

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
.dmx-cell--clash {
  background: #e53935;
  color: #fff;
  box-shadow: inset 0 0 0 2px #ffcdd2;
}
.dmx-cell--was {
  box-shadow: inset 0 0 0 2px #ffb300;
}
</style>
