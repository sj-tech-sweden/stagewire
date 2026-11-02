<template>
  <q-dialog
    :model-value="!!conflict"
    persistent
    @update:model-value="onDiscard"
  >
    <q-card class="conflict-card">
      <q-card-section>
        <div class="text-h6">
          {{ t('conflictDialog.title') }}
        </div>
        <div class="text-body2 q-mt-xs">
          {{ t('conflictDialog.body') }}
        </div>
      </q-card-section>
      <q-card-section
        v-if="conflict"
        class="q-pt-none"
      >
        <q-list separator>
          <q-item
            v-for="item in conflict.conflicts"
            :key="item.field"
            class="column q-py-md"
          >
            <div class="text-subtitle2">
              {{ item.field }}
            </div>
            <q-option-group
              v-model="choices[item.field]"
              :options="[
                { value: 'mine', label: `${t('conflictDialog.mine')}: ${show(item.mine)}` },
                { value: 'theirs', label: `${t('conflictDialog.theirs')}: ${show(item.theirs)}` },
              ]"
              type="radio"
            />
          </q-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          no-caps
          :label="t('conflictDialog.discard')"
          @click="onDiscard"
        />
        <q-btn
          color="primary"
          no-caps
          :label="t('conflictDialog.apply')"
          @click="emit('resolve', { ...choices })"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { reactive, watch } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps({ conflict: { type: Object, default: null } });
const emit = defineEmits(['resolve', 'discard']);
const { t } = useI18n();
const choices = reactive({});

watch(
  () => props.conflict,
  (conflict) => {
    Object.keys(choices).forEach((key) => delete choices[key]);
    (conflict?.conflicts || []).forEach((item) => {
      choices[item.field] = 'theirs';
    });
  },
  { immediate: true },
);

const show = (value) => (value === null || value === undefined || value === '' ? '—' : String(value));
const onDiscard = () => emit('discard');
</script>

<style scoped>
.conflict-card {
  width: 480px;
  max-width: 95vw;
}
</style>
