<template>
  <div
    v-if="nodes.length"
    class="notes-display"
    data-testid="notes-display"
  >
    <!-- Rendered markdown. The DOMPurify output is turned into Vue vnodes (SafeNodes) rather than
         injected with v-html, so no raw HTML sink exists and only allowlisted attributes reach the DOM. -->
    <div
      ref="bodyRef"
      class="notes-body"
      :class="{ 'notes-clamp': !expanded && overflowing }"
      :style="clampStyle"
    >
      <SafeNodes :nodes="nodes" />
    </div>
    <q-btn
      v-if="overflowing"
      flat
      dense
      no-caps
      size="sm"
      color="primary"
      class="q-mt-xs"
      :icon-right="expanded ? 'expand_less' : 'expand_more'"
      :label="expanded ? t('app.actions.readLess') : t('app.actions.readMore')"
      :data-testid="expanded ? 'notes-read-less' : 'notes-read-more'"
      @click="expanded = !expanded"
    />
  </div>
</template>

<script setup>
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

const props = defineProps({
  // Raw notes text. May contain markdown; rendered and sanitized below.
  notes: { type: String, default: '' },
  // Lines shown when collapsed. The "read more" toggle only appears when the rendered
  // content is actually taller than this. Use 0 to never collapse.
  rows: { type: Number, default: 4 },
});

const { t } = useI18n();
const expanded = ref(false);
const overflowing = ref(false);
const bodyRef = ref(null);

// Only these attributes are copied from sanitized markup. DOMPurify already strips event handlers
// and unsafe URLs; this allowlist is a second guard so a future DOMPurify config change cannot
// pass arbitrary attributes through.
const ALLOWED_ATTRS = new Set(['href', 'title', 'alt', 'src', 'colspan', 'rowspan', 'align', 'target', 'rel']);

// async:false forces a synchronous string; breaks:true turns single newlines into <br>.
const nodes = computed(() => {
  const text = (props.notes || '').trim();
  if (!text) return [];
  const parsed = marked.parse(text, { async: false, breaks: true, gfm: true });
  // RETURN_DOM_FRAGMENT yields DOM nodes instead of an HTML string, so nothing is re-parsed as HTML.
  return Array.from(DOMPurify.sanitize(parsed, { RETURN_DOM_FRAGMENT: true }).childNodes);
});

function toVNode(node) {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent;
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const attrs = {};
  for (const { name, value } of node.attributes) {
    if (ALLOWED_ATTRS.has(name)) attrs[name] = value;
  }
  const children = Array.from(node.childNodes).map(toVNode).filter((c) => c !== null);
  return h(node.tagName.toLowerCase(), attrs, children);
}

const SafeNodes = ({ nodes: list }) => list.map(toVNode).filter((v) => v !== null);
SafeNodes.props = ['nodes'];

const clampStyle = computed(() => {
  if (expanded.value || !props.rows) return {};
  return { maxHeight: `${props.rows * 1.5}rem`, overflow: 'hidden' };
});

// Decide whether the collapsed view actually cuts off content. scrollHeight reports the full
// content height even under overflow:hidden, so this is independent of the expanded state.
function measure() {
  const el = bodyRef.value;
  if (!el || !props.rows) {
    overflowing.value = false;
    return;
  }
  const cs = getComputedStyle(el);
  const lh = parseFloat(cs.lineHeight);
  const lineHeightPx = Number.isNaN(lh)
    ? parseFloat(cs.fontSize) * 1.5
    : lh;
  overflowing.value = el.scrollHeight > lineHeightPx * props.rows + 1;
}

onMounted(() => {
  measure();
  window.addEventListener('resize', measure);
});
onBeforeUnmount(() => window.removeEventListener('resize', measure));
watch(
  () => [props.notes, props.rows],
  () => nextTick(measure),
);
</script>

<style scoped>
.notes-body {
  line-height: 1.5;
  /* Let links inside notes open in a new tab without the surrounding app navigating. */
  word-break: break-word;
}
.notes-body :deep(a) {
  color: var(--q-primary);
  text-decoration: underline;
}
.notes-clamp {
  position: relative;
}
/* Fade the last visible line so the cut-off isn't abrupt when collapsed. */
.notes-clamp::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 1.5em;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0), currentColor);
  opacity: 0.12;
  pointer-events: none;
}
</style>
