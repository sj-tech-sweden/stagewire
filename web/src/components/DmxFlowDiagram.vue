<template>
  <div
    v-if="layout.nodes.length"
    class="dmx-flow-scroll"
  >
    <div
      class="dmx-flow"
      :style="{ width: layout.width + 'px', height: layout.height + 'px' }"
    >
      <svg
        :width="layout.width"
        :height="layout.height"
        class="dmx-flow-arrows"
      >
        <defs>
          <marker
            :id="arrowId"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path
              d="M 0 0 L 10 5 L 0 10 z"
              fill="#9aa0a6"
            />
          </marker>
        </defs>
        <g
          v-for="(e, i) in layout.edges"
          :key="`e-${i}`"
        >
          <line
            :x1="e.x1"
            :y1="e.y1"
            :x2="e.x2"
            :y2="e.y2"
            stroke="#9aa0a6"
            stroke-width="2"
            :marker-end="`url(#${arrowId})`"
          />
          <text
            v-if="e.label"
            :x="(e.x1 + e.x2) / 2"
            :y="(e.y1 + e.y2) / 2 - 5"
            class="dmx-flow-edge-label"
            text-anchor="middle"
          >
            {{ truncate(e.label, 16) }}
          </text>
        </g>
      </svg>
      <div
        v-for="n in layout.nodes"
        :key="n.node.id"
        class="dmx-flow-node"
        :class="n.node.kind === 'fixture' ? 'is-fixture' : 'is-device'"
        :style="nodeStyle(n)"
        @click="$emit('edit', n.node)"
      >
        <div class="dmx-flow-title">
          {{ truncate(n.node.label || (n.node.kind === 'fixture' ? t('dmxChain.kindFixture') : t('dmxChain.kindDevice')), 18) }}
        </div>
        <div class="dmx-flow-sub">
          {{ subLabel(n.node) }}
        </div>
        <q-btn
          class="dmx-flow-add"
          round
          dense
          size="sm"
          icon="add"
          color="primary"
          :aria-label="t('dmxChain.addChild')"
          @click.stop="$emit('add-child', n.node.id)"
        />
        <q-btn
          class="dmx-flow-del"
          round
          dense
          size="sm"
          icon="close"
          color="negative"
          :aria-label="t('dmxChain.deleteStep')"
          @click.stop="$emit('delete', n.node)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps({
  steps: { type: Array, default: () => [] },
  universeNumber: { type: Number, default: 0 },
});

defineEmits(['edit', 'add-child', 'delete']);

const { t } = useI18n();

const colW = 200;
const rowH = 80;
const nodeW = 168;
const nodeH = 54;
const mx = 16;
const my = 16;
const TOP_PAD = 32;

const arrowId = `dmx-flow-arrow-${Math.random().toString(36).slice(2, 8)}`;

function nodeX(depth) {
  return mx + depth * colW;
}
function nodeY(ry) {
  return my + TOP_PAD + ry;
}

function truncate(value, max = 18) {
  if (!value) return '';
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function subLabel(node) {
  const bits = [];
  if (node.kind === 'fixture') bits.push(t('dmxChain.kindFixture'));
  else bits.push(t('dmxChain.kindDevice'));
  if (node.in_port) bits.push(`in ${node.in_port}`);
  if (node.out_port) bits.push(`out ${node.out_port}`);
  if (node.connector) bits.push(node.connector);
  return bits.join(' · ') || '—';
}

const layout = computed(() => {
  const pos = {};
  let leaf = 0;
  let maxDepth = 0;
  const collected = [];

  function firstPass(nodes, depth) {
    let lo = Infinity;
    let hi = -Infinity;
    for (const n of nodes) {
      maxDepth = Math.max(maxDepth, depth);
      if (n.children && n.children.length) {
        const [clo, chi] = firstPass(n.children, depth + 1);
        const ry = (clo + chi) / 2;
        pos[n.id] = { depth, ry };
        collected.push({ node: n, depth, ry });
        lo = Math.min(lo, clo);
        hi = Math.max(hi, chi);
      } else {
        const ry = leaf * rowH;
        leaf += 1;
        pos[n.id] = { depth, ry };
        collected.push({ node: n, depth, ry });
        lo = Math.min(lo, ry);
        hi = Math.max(hi, ry);
      }
    }
    return [lo, hi];
  }

  firstPass(props.steps, 0);

  const height = Math.max(leaf * rowH, rowH) + my * 2 + TOP_PAD;
  const width = (maxDepth + 1) * colW + mx * 2;

  const nodes = collected.map((c) => ({ ...c }));
  const edges = [];
  for (const rec of nodes) {
    const children = rec.node.children || [];
    for (const c of children) {
      const childRec = nodes.find((r) => r.node.id === c.id);
      if (!childRec) continue;
      edges.push({
        x1: nodeX(rec.depth) + nodeW,
        y1: nodeY(rec.ry),
        x2: nodeX(childRec.depth),
        y2: nodeY(childRec.ry),
        label: c.connector || c.in_port || '',
      });
    }
  }

  return { nodes, edges, width, height };
});

function nodeStyle(n) {
  return {
    left: `${nodeX(n.depth)}px`,
    top: `${nodeY(n.ry) - nodeH / 2}px`,
    width: `${nodeW}px`,
    height: `${nodeH}px`,
  };
}
</script>

<style scoped>
.dmx-flow-scroll {
  overflow: auto;
  max-width: 100%;
}
.dmx-flow {
  position: relative;
}
.dmx-flow-arrows {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.dmx-flow-node {
  position: absolute;
  border-radius: 8px;
  padding: 4px 8px;
  cursor: pointer;
  border: 2px solid #26a69a;
  background: #e3f4f1;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}
.dmx-flow-node.is-fixture {
  border-color: #ef9a1b;
  background: #fff4e0;
}
.dmx-flow-title {
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dmx-flow-sub {
  font-size: 11px;
  color: #5f6368;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dmx-flow-edge-label {
  font-size: 10px;
  fill: #5f6368;
}
.dmx-flow-add {
  position: absolute;
  right: -10px;
  top: 50%;
  transform: translateY(-50%);
}
.dmx-flow-del {
  position: absolute;
  right: 6px;
  top: -10px;
}
</style>
