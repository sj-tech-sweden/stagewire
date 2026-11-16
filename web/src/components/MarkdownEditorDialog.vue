<template>
  <!-- Reusable markdown editor for any "notes" field. Opens as a modal with a formatting toolbar,
       a side-by-side editor (left) and a live preview (right); on phones the two stack. The preview
       reuses NotesDisplay so what you type renders exactly as it will once saved. Cancelling discards
       the draft. The toolbar lets non-Markdown users apply formatting: each button manipulates the
       textarea selection and inserts the matching markdown syntax. -->
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
        <!-- Formatting toolbar. Buttons are icon-only with a tooltip label; the actual insertion
             is handled by applyInline / applyBlock / insertLink which read the textarea selection. -->
        <div
          class="row q-gutter-xs wrap q-mb-sm items-center"
          data-testid="markdown-toolbar"
        >
          <q-btn
            flat
            dense
            icon="format_bold"
            :aria-label="t('workspace.toolbar.bold')"
            data-testid="markdown-toolbar-bold"
            @click="applyInline('**', '**', 'bold')"
          >
            <q-tooltip>{{ t('workspace.toolbar.bold') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_italic"
            :aria-label="t('workspace.toolbar.italic')"
            data-testid="markdown-toolbar-italic"
            @click="applyInline('*', '*', 'italic')"
          >
            <q-tooltip>{{ t('workspace.toolbar.italic') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_strikethrough"
            :aria-label="t('workspace.toolbar.strike')"
            data-testid="markdown-toolbar-strike"
            @click="applyInline('~~', '~~', 'strike')"
          >
            <q-tooltip>{{ t('workspace.toolbar.strike') }}</q-tooltip>
          </q-btn>
          <q-separator vertical />
          <q-btn
            flat
            dense
            icon="title"
            :aria-label="t('workspace.toolbar.heading')"
            data-testid="markdown-toolbar-heading"
            @click="applyBlock({ test: (l) => /^#+\s/.test(l), marker: /^#+\s/ }, '# ')"
          >
            <q-tooltip>{{ t('workspace.toolbar.heading') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_list_bulleted"
            :aria-label="t('workspace.toolbar.bullet')"
            data-testid="markdown-toolbar-bullet"
            @click="applyBlock({ test: (l) => /^- /.test(l), marker: /^- / }, '- ')"
          >
            <q-tooltip>{{ t('workspace.toolbar.bullet') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_list_numbered"
            :aria-label="t('workspace.toolbar.numbered')"
            data-testid="markdown-toolbar-numbered"
            @click="applyBlock({ test: (l) => /^\d+\.\s/.test(l), marker: /^\d+\.\s/ }, null, true)"
          >
            <q-tooltip>{{ t('workspace.toolbar.numbered') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_quote"
            :aria-label="t('workspace.toolbar.quote')"
            data-testid="markdown-toolbar-quote"
            @click="applyBlock({ test: (l) => /^> /.test(l), marker: /^> / }, '> ')"
          >
            <q-tooltip>{{ t('workspace.toolbar.quote') }}</q-tooltip>
          </q-btn>
          <q-separator vertical />
          <q-btn
            flat
            dense
            icon="link"
            :aria-label="t('workspace.toolbar.link')"
            data-testid="markdown-toolbar-link"
            @click="insertLink"
          >
            <q-tooltip>{{ t('workspace.toolbar.link') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="code"
            :aria-label="t('workspace.toolbar.code')"
            data-testid="markdown-toolbar-code"
            @click="applyInline('`', '`', 'code')"
          >
            <q-tooltip>{{ t('workspace.toolbar.code') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="data_object"
            :aria-label="t('workspace.toolbar.codeBlock')"
            data-testid="markdown-toolbar-codeblock"
            @click="applyInline('```\n', '\n```', 'code')"
          >
            <q-tooltip>{{ t('workspace.toolbar.codeBlock') }}</q-tooltip>
          </q-btn>
        </div>

        <div
          class="row q-col-gutter-md col-grow"
          :class="{ column: $q.screen.lt.sm }"
        >
          <q-input
            ref="editorInput"
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
import { computed, nextTick, ref, watch } from 'vue';
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
const editorInput = ref(null);

// Re-seed on open so a cancelled edit is discarded and reopening starts from the saved value.
watch(open, (isOpen) => {
  if (isOpen) draft.value = props.value;
});

// The q-input wraps a real <textarea>; we read/write its selection directly for formatting.
// Fallback to the end of the string if the element is somehow unavailable.
function textareaEl() {
  const c = editorInput.value;
  if (!c || !c.$el) return null;
  return c.$el.querySelector('textarea') || c.$el.querySelector('input');
}

// Inline wrap (bold/italic/strike/code): surround the current selection with before/after markers.
// With no selection, insert a placeholder and select it so the user can just type over it.
function applyInline(before, after, placeholder) {
  const ta = textareaEl();
  const val = draft.value;
  const s = ta ? ta.selectionStart : val.length;
  const e = ta ? ta.selectionEnd : val.length;
  const selected = val.slice(s, e) || placeholder;
  const inserted = before + selected + after;
  draft.value = val.slice(0, s) + inserted + val.slice(e);
  if (ta) {
    nextTick(() => {
      ta.focus();
      const start = s + before.length;
      ta.setSelectionRange(start, start + selected.length);
    });
  }
}

// Block prefix (heading/list/quote): prefix every selected line. If every line already carries the
// marker we toggle it off (so the button is a real on/off switch); otherwise we add it. Numbered
// lists renumber from 1 on each line.
function applyBlock({ test, marker }, prefix, numbered = false) {
  const ta = textareaEl();
  const val = draft.value;
  const s = ta ? ta.selectionStart : val.length;
  const e = ta ? ta.selectionEnd : val.length;
  const lineStart = val.lastIndexOf('\n', s - 1) + 1;
  let lineEnd = val.indexOf('\n', e);
  if (lineEnd === -1) lineEnd = val.length;
  const block = val.slice(lineStart, lineEnd);
  const lines = block.split('\n');
  const active = lines.every((l) => test(l));
  const newLines = lines.map((l, i) => {
    const stripped = l.replace(marker, '');
    if (active) return stripped;
    return (numbered ? `${i + 1}. ` : prefix) + stripped;
  });
  const newBlock = newLines.join('\n');
  draft.value = val.slice(0, lineStart) + newBlock + val.slice(lineEnd);
  if (ta) {
    nextTick(() => {
      ta.focus();
      ta.setSelectionRange(lineStart, lineStart + newBlock.length);
    });
  }
}

// Link: insert [selection](url) and select the url placeholder so it can be typed over.
function insertLink() {
  const ta = textareaEl();
  const val = draft.value;
  const s = ta ? ta.selectionStart : val.length;
  const e = ta ? ta.selectionEnd : val.length;
  const selected = val.slice(s, e) || 'link text';
  const inserted = `[${selected}](https://)`;
  draft.value = val.slice(0, s) + inserted + val.slice(e);
  if (ta) {
    nextTick(() => {
      ta.focus();
      const urlStart = s + selected.length + 3; // after "]( "
      ta.setSelectionRange(urlStart, urlStart + 8); // length of "https://"
    });
  }
}

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
