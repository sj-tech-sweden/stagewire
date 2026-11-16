<template>
  <!-- Reusable markdown editor for any "notes" field. Opens as a modal with a side-by-side editor
       (left) and a live preview (right); on phones the two stack. The preview reuses NotesDisplay so
       what you type renders exactly as it will once saved. Cancelling discards the draft. -->
  <q-dialog
    v-model="open"
    persistent
    maximized
  >
    <q-card class="column">
      <q-bar class="bg-primary text-white">
        <div class="text-subtitle1 ellipsis">
          {{ title || t('workspace.notes') }}
        </div>
        <q-space />
        <q-btn
          dense
          flat
          round
          icon="close"
          :aria-label="t('app.actions.cancel')"
          @click="cancel"
        />
      </q-bar>

      <q-card-section class="col column q-pa-md overflow-auto">
        <div
          class="row q-col-gutter-md col-grow"
          :class="{ column: $q.screen.lt.sm }"
        >
          <q-input
            v-model="draft"
            type="textarea"
            outlined
            autogrow
            class="col"
            :label="t('workspace.editNotes')"
            :hint="t('workspace.markdownHint')"
            data-testid="markdown-editor-input"
          />
          <div class="col column">
            <div class="text-caption text-grey-7 q-mb-xs">
              {{ t('workspace.preview') }}
            </div>
            <div class="notes-preview col q-pa-sm rounded-borders">
              <NotesDisplay
                v-if="draft"
                :notes="draft"
                :rows="0"
              />
              <div
                v-else
                class="text-grey-6"
              >
                {{ t('workspace.previewEmpty') }}
              </div>
            </div>
          </div>
        </div>
      </q-card-section>

      <q-card-actions
        align="right"
        class="q-pa-md"
      >
        <q-btn
          flat
          :label="t('app.actions.cancel')"
          data-testid="markdown-editor-cancel"
          @click="cancel"
        />
        <q-btn
          color="primary"
          :label="t('app.actions.save')"
          data-testid="markdown-editor-save"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import NotesDisplay from './NotesDisplay.vue';

const props = defineProps({
  // v-model open/close state of the dialog.
  modelValue: { type: Boolean, default: false },
  // Heading shown in the dialog bar; falls back to a generic "Notes" label.
  title: { type: String, default: '' },
  // Current notes text (markdown). Seeded into the editor each time the dialog opens.
  value: { type: String, default: '' },
});
const emit = defineEmits(['update:modelValue', 'save']);

const { t } = useI18n();
const $q = useQuasar();

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
});
const draft = ref(props.value);

// Re-seed on open so a cancelled edit is discarded and reopening starts from the saved value.
watch(open, (isOpen) => {
  if (isOpen) draft.value = props.value;
});

function cancel() {
  open.value = false;
}

function save() {
  emit('save', draft.value);
  open.value = false;
}
</script>

<style scoped>
/* Mirror the rendered-notes look so the preview reads like the saved result. */
.notes-preview {
  background: rgba(127, 127, 127, 0.08);
  border: 1px solid rgba(127, 127, 127, 0.25);
  overflow: auto;
}
</style>
