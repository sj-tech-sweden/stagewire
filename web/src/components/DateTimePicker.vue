<template>
  <q-input
    :model-value="display"
    :label="label"
    readonly
    :rules="rules"
    :hint="hint"
    @click="popupDate = true"
  >
    <template #append>
      <q-icon
        name="event"
        class="cursor-pointer"
      >
        <q-popup-proxy
          v-model="popupDate"
          cover
          transition-show="scale"
          transition-hide="scale"
        >
          <q-date
            v-model="datePart"
            mask="YYYY-MM-DD"
            today-btn
          >
            <div class="row items-center justify-end">
              <q-btn
                v-close-popup
                label="OK"
                color="primary"
                flat
              />
            </div>
          </q-date>
        </q-popup-proxy>
      </q-icon>
      <q-icon
        name="access_time"
        class="cursor-pointer"
      >
        <q-popup-proxy
          v-model="popupTime"
          cover
          transition-show="scale"
          transition-hide="scale"
        >
          <q-time
            v-model="timePart"
            mask="HH:mm"
            format24h
          >
            <div class="row items-center justify-end">
              <q-btn
                v-close-popup
                label="OK"
                color="primary"
                flat
              />
            </div>
          </q-time>
        </q-popup-proxy>
      </q-icon>
    </template>
  </q-input>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  rules: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const popupDate = ref(false)
const popupTime = ref(false)
const datePart = ref('')
const timePart = ref('')

function split(value) {
  if (!value) return { d: '', t: '' }
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return { d: '', t: '' }
  const pad = (n) => String(n).padStart(2, '0')
  return {
    d: `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`,
    t: `${pad(dt.getHours())}:${pad(dt.getMinutes())}`,
  }
}

function join(d, t) {
  if (!d || !t) return ''
  return `${d}T${t}`
}

watch(
  () => props.modelValue,
  (v) => {
    const { d, t } = split(v)
    datePart.value = d
    timePart.value = t
  },
  { immediate: true },
)

const display = computed(() => join(datePart.value, timePart.value))

watch([datePart, timePart], () => {
  const joined = join(datePart.value, timePart.value)
  if (joined !== props.modelValue) emit('update:modelValue', joined)
})
</script>
