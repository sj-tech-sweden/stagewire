<template>
  <q-input
    :model-value="display"
    :label="label"
    readonly
    :rules="rules"
    :hint="hint"
    @click="popup = true"
  >
    <template #append>
      <!-- A single trigger opens one popup holding both the calendar and the clock, so the
           event date and time are chosen together rather than via two separate icons. -->
      <q-icon
        name="event"
        class="cursor-pointer"
      >
        <q-popup-proxy
          v-model="popup"
          cover
          transition-show="scale"
          transition-hide="scale"
        >
          <div class="q-pa-sm">
            <div
              class="q-gutter-sm"
              :class="$q.screen.lt.sm ? 'column' : 'row'"
            >
              <q-date
                :model-value="datePart"
                mask="YYYY-MM-DD"
                today-btn
                @update:model-value="onDatePick"
              />
              <q-time
                :model-value="timePart"
                mask="HH:mm"
                format24h
                @update:model-value="onTimePick"
              />
            </div>
            <div class="row items-center justify-end">
              <q-btn
                v-close-popup
                label="OK"
                color="primary"
                flat
              />
            </div>
          </div>
        </q-popup-proxy>
      </q-icon>
    </template>
  </q-input>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  rules: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])
const $q = useQuasar()

const popup = ref(false)
const datePart = ref('')
const timePart = ref('')

function split(value) {
  if (!value) return { d: '', t: '' }
  // The model is either 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:mm'. Splitting on the literal
  // keeps the date in YYYY-MM-DD (the field we show) without timezone drift: parsing
  // 'YYYY-MM-DD' through `new Date()` would treat it as UTC midnight and shift the day
  // in negative-offset zones.
  const [d, tRaw] = String(value).split('T')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d || '')) {
    // Defensive fallback for any other ISO shape.
    const dt = new Date(value)
    if (Number.isNaN(dt.getTime())) return { d: '', t: '' }
    const pad = (n) => String(n).padStart(2, '0')
    return {
      d: `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`,
      t: `${pad(dt.getHours())}:${pad(dt.getMinutes())}`,
    }
  }
  return { d, t: tRaw ? tRaw.slice(0, 5) : '' }
}

function join(d, t) {
  if (!d) return ''
  // A date without an explicit time is saved as local midnight (T00:00) so the value is
  // meaningful and the read-only list renders it on the correct day in any timezone.
  // (Storing a bare 'YYYY-MM-DD' would be read back as UTC midnight and could shift the
  // displayed day for viewers west of UTC.)
  return t ? `${d}T${t}` : `${d}T00:00`
}

watch(
  () => props.modelValue,
  (v) => {
    const { d, t } = split(v)
    datePart.value = d
    // A date saved without an explicit time is stored as local midnight (T00:00) so it renders
    // on the correct day everywhere. Treat that as "no time" here so the field keeps showing
    // just the date (YYYY-MM-DD) rather than "YYYY-MM-DD 00:00".
    timePart.value = t === '00:00' ? '' : t
  },
  { immediate: true },
)

// Quasar's q-date/q-time can emit a spurious null while the parent round-trips the model value
// (the dialog re-renders and re-initialises the popup). Ignore it so a valid selection is not
// clobbered back to empty.
function onDatePick(val) {
  if (val == null || val === '') return
  datePart.value = val
}

function onTimePick(val) {
  if (val == null || val === '') return
  timePart.value = val
}

// Show the date as soon as it is picked, even before a time is chosen. The date stays in
// YYYY-MM-DD (the picker mask) rather than the localized format, and the 24h time is
// appended with a space when present.
const display = computed(() => {
  const d = datePart.value
  if (!d) return ''
  return timePart.value ? `${d} ${timePart.value}` : d
})

watch([datePart, timePart], () => {
  const joined = join(datePart.value, timePart.value)
  if (joined !== props.modelValue) emit('update:modelValue', joined)
})
</script>
