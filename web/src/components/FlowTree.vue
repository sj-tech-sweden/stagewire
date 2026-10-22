<template>
  <div
    class="flow-tree-node"
    :class="{ 'flow-tree-child': depth > 0 }"
  >
    <q-card
      flat
      bordered
      :class="[
        'flow-node q-pa-xs',
        compact ? 'text-center' : '',
        isHighlight ? 'flow-node-active' : '',
      ]"
    >
      <div class="text-body2">
        {{ node.name || '—' }}
      </div>
      <div
        v-if="!compact && node.ptype"
        class="text-caption text-grey-7"
      >
        {{ node.ptype }}
      </div>
      <div class="text-caption text-grey-7">
        {{ [node.connector, node.patch_label].filter(Boolean).join(' · ') || '—' }}
      </div>
      <div
        v-if="!compact && node.connectorTag"
        class="text-caption text-grey-7"
      >
        {{ node.connectorTag }}
      </div>
      <div
        v-if="!compact && node.meta"
        class="text-caption text-grey-7"
      >
        {{ node.meta }}
      </div>
      <div
        v-if="!compact && node.notes"
        class="text-caption text-grey-7"
      >
        <TruncateText :text="node.notes" />
      </div>
    </q-card>
    <div
      v-if="node.children && node.children.length"
      class="flow-tree-children"
    >
      <FlowTree
        v-for="(child, ci) in node.children"
        :key="child.id || ci"
        :node="child"
        :depth="depth + 1"
        :highlight="highlight"
        :compact="compact"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import TruncateText from 'components/TruncateText.vue'

defineOptions({ name: 'FlowTree' })

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  highlight: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const isHighlight = computed(
  () => !!props.highlight && props.node.name === props.highlight,
)
</script>

<style scoped>
.flow-tree-children {
  position: relative;
  margin-left: 12px;
  padding-left: 18px;
}
.flow-tree-child {
  position: relative;
}
.flow-tree-child::before {
  content: '';
  position: absolute;
  left: -18px;
  top: 16px;
  width: 18px;
  border-top: 2px solid rgba(150, 150, 150, 0.55);
}
.flow-tree-child::after {
  content: '';
  position: absolute;
  left: -18px;
  top: 0;
  width: 0;
  border-left: 2px solid rgba(150, 150, 150, 0.55);
  height: 100%;
}
.flow-tree-children > .flow-tree-child:last-child::after {
  height: 16px;
}
.flow-node-active {
  background: rgba(63, 135, 63, 0.18);
  border-color: var(--ec-accent, #35a853);
}
</style>
