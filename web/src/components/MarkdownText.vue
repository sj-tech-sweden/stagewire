<template>
  <!-- eslint-disable vue/no-v-html -- content is markdown rendered and sanitized with DOMPurify before injection -->
  <div
    class="sw-markdown"
    v-html="html"
  />
  <!-- eslint-enable vue/no-v-html -->
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  source: { type: String, default: '' },
})

const html = computed(() => {
  if (!props.source) return ''
  const raw = marked.parse(props.source, { async: false, breaks: true, gfm: true })
  return DOMPurify.sanitize(raw)
})
</script>

<style scoped>
.sw-markdown {
  white-space: normal;
  word-break: break-word;
}
.sw-markdown :deep(p) {
  margin: 0 0 0.4em;
}
.sw-markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.sw-markdown :deep(ul),
.sw-markdown :deep(ol) {
  padding-left: 1.2em;
  margin: 0 0 0.4em;
}
.sw-markdown :deep(code) {
  background: rgba(127, 127, 127, 0.2);
  padding: 0 0.25em;
  border-radius: 3px;
}
.sw-markdown :deep(pre) {
  background: rgba(127, 127, 127, 0.15);
  padding: 0.5em;
  overflow: auto;
  border-radius: 4px;
}
.sw-markdown :deep(a) {
  color: var(--q-primary);
}
</style>
