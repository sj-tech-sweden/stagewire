<template>
  <q-input
    :model-value="modelValue"
    :label="label"
    :rules="rules"
    :hint="hint"
    readonly
    dense
    outlined
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
            :options="options"
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
        v-if="modelValue"
        name="cancel"
        class="cursor-pointer"
        @click.stop="$emit('update:modelValue', '')"
      />
    </template>
  </q-input>
</template>

<script setup>
import { ref, watch } from 'vue';

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  rules: { type: Array, default: () => [] },
  // Optional day filter passed straight to q-date (e.g. disable past dates).
  options: { type: [Function, Array], default: undefined },
});
const emit = defineEmits(['update:modelValue']);

const popupDate = ref(false);
const datePart = ref(props.modelValue || '');

watch(
  () => props.modelValue,
  (v) => {
    datePart.value = v || '';
  },
  { immediate: true },
);

watch(datePart, (d) => {
  if (d !== props.modelValue) emit('update:modelValue', d || '');
});
</script>
