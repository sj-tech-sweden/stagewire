<template>
  <q-btn
    flat
    dense
    icon="view_column"
    :label="t('columns.button')"
    size="sm"
  >
    <q-menu
      anchor="bottom right"
      self="top right"
    >
      <q-list
        dense
        style="min-width: 240px"
      >
        <q-item-label
          header
          class="text-caption"
        >
          {{ t('columns.hint') }}
        </q-item-label>
        <q-item
          v-for="(col, idx) in prefs.ordered.value"
          :key="col.name"
        >
          <q-item-section side>
            <q-toggle
              :model-value="col.shown"
              :disable="col.locked"
              dense
              @update:model-value="() => prefs.toggle(col.name)"
            />
          </q-item-section>
          <q-item-section>{{ col.label || col.name }}</q-item-section>
          <q-item-section side>
            <div class="row no-wrap">
              <q-btn
                flat
                dense
                round
                size="sm"
                icon="arrow_upward"
                :disable="idx === 0"
                @click="prefs.move(col.name, -1)"
              />
              <q-btn
                flat
                dense
                round
                size="sm"
                icon="arrow_downward"
                :disable="idx === prefs.ordered.value.length - 1"
                @click="prefs.move(col.name, 1)"
              />
            </div>
          </q-item-section>
        </q-item>
        <q-separator />
        <q-item
          v-close-popup
          clickable
          @click="prefs.reset()"
        >
          <q-item-section>{{ t('columns.reset') }}</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup>
import { useI18n } from 'vue-i18n';

defineProps({
  prefs: { type: Object, required: true },
});

const { t } = useI18n({ useScope: 'global' });
</script>
