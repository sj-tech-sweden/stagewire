<template>
  <div class="truncate-text-wrap">
    <div
      ref="el"
      class="truncate-text"
      :style="
        needsClamp && !expanded
          ? {
            display: '-webkit-box',
            WebkitLineClamp: lines,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }
          : {}
      "
    >
      <slot>{{ text }}</slot>
    </div>
    <q-btn
      v-if="needsClamp"
      flat
      dense
      size="xs"
      class="q-mt-none q-pa-none"
      :label="expanded ? t('common.showLess') : t('common.readMore')"
      @click="expanded = !expanded"
    />
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  text: { type: String, default: '' },
  lines: { type: Number, default: 2 },
})

const expanded = ref(false)
const needsClamp = ref(false)
const el = ref(null)

function measure() {
  const node = el.value
  if (!node) return
  const style = window.getComputedStyle(node)
  const lh = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.4
  const maxH = lh * props.lines + 1
  needsClamp.value = node.scrollHeight > maxH + 2
}

onMounted(() => nextTick(measure))
watch(
  () => [props.text, props.lines],
  () => nextTick(measure),
)
</script>

<style scoped>
.truncate-text {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
