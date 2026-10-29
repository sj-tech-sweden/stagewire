<template>
  <div class="q-ml-sm">
    <div class="row items-center q-gutter-xs q-py-xs wrap">
      <q-icon
        :name="step.kind === 'fixture' ? 'lightbulb' : 'device_hub'"
        :color="step.kind === 'fixture' ? 'warning' : 'primary'"
        size="xs"
      />
      <span class="text-body2">{{ step.label || defaultLabel }}</span>
      <q-badge
        v-if="step.connector"
        color="grey-7"
        class="q-ml-xs"
      >
        {{ step.connector }}
      </q-badge>
      <span
        v-if="step.in_port || step.out_port"
        class="text-caption text-grey-7"
      >
        {{ [step.in_port, step.out_port].filter(Boolean).join(' → ') }}
      </span>
      <q-space />
      <q-btn
        flat
        dense
        round
        icon="add"
        :aria-label="t('dmxChain.addChild')"
        @click="$emit('addChild', step.id)"
      />
      <q-btn
        flat
        dense
        round
        icon="edit"
        :aria-label="t('app.actions.edit')"
        @click="$emit('edit', step)"
      />
      <q-btn
        flat
        dense
        round
        icon="delete"
        color="negative"
        :aria-label="t('dmxChain.deleteStep')"
        @click="$emit('delete', step)"
      />
    </div>
    <DmxStepNode
      v-for="child in step.children"
      :key="child.id"
      :step="child"
      @add-child="$emit('addChild', $event)"
      @edit="$emit('edit', $event)"
      @delete="$emit('delete', $event)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const props = defineProps({
  step: { type: Object, required: true },
});
defineEmits(['addChild', 'edit', 'delete']);

const defaultLabel = computed(() =>
  props.step.kind === 'fixture' ? t('dmxChain.kindFixture') : t('dmxChain.kindDevice'),
);
</script>
