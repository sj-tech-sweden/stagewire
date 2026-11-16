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
             is handled by applyInline / togglePrefix / toggleNumbered / toggleHeading / insertLink which read
       the textarea selection. -->
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
          <q-separator vertical />
          <template
            v-for="level in headingLevels"
            :key="level"
          >
            <q-btn
              flat
              dense
              :label="`H${level}`"
              :aria-label="`${t('workspace.toolbar.heading')} ${level}`"
              :data-testid="`markdown-toolbar-heading-${level}`"
              @click="toggleHeading(level)"
            >
              <q-tooltip>{{ t('workspace.toolbar.heading') }} {{ level }}</q-tooltip>
            </q-btn>
          </template>
          <q-separator vertical />
          <q-btn
            flat
            dense
            icon="format_list_bulleted"
            :aria-label="t('workspace.toolbar.bullet')"
            data-testid="markdown-toolbar-bullet"
            @click="togglePrefix('- ')"
          >
            <q-tooltip>{{ t('workspace.toolbar.bullet') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_list_numbered"
            :aria-label="t('workspace.toolbar.numbered')"
            data-testid="markdown-toolbar-numbered"
            @click="toggleNumbered()"
          >
            <q-tooltip>{{ t('workspace.toolbar.numbered') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            icon="format_quote"
            :aria-label="t('workspace.toolbar.quote')"
            data-testid="markdown-toolbar-quote"
            @click="togglePrefix('> ')"
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

// Inline wrap (bold/italic/strike/code). This is a toggle: if the selection (or, for a collapsed
// cursor, the word under it) is already wrapped in the markers, they are removed; otherwise they are
// added around it. Toggling off works whether the markers sit just outside the selection or are part
// of the selected text itself.
function expandWord(val, pos) {
  let start = pos;
  let end = pos;
  while (start > 0 && !/\s/.test(val[start - 1])) start -= 1;
  while (end < val.length && !/\s/.test(val[end])) end += 1;
  return { start, end };
}

function applyInline(before, after, placeholder) {
  const ta = textareaEl();
  const val = draft.value;
  let s = ta ? ta.selectionStart : val.length;
  let e = ta ? ta.selectionEnd : val.length;
  if (s === e) {
    // Collapsed cursor: act on the whole word so clicking inside "**bold**" toggles it.
    const w = expandWord(val, s);
    s = w.start;
    e = w.end;
  }
  const selText = val.slice(s, e);
  const outerBefore = val.slice(s - before.length, s) === before;
  const outerAfter = val.slice(e, e + after.length) === after;
  let newStart;
  let newEnd;
  if (outerBefore && outerAfter) {
    // Markers sit just outside the selection: drop them, keep the inner text selected.
    draft.value = val.slice(0, s - before.length) + selText + val.slice(e + after.length);
    newStart = s - before.length;
    newEnd = newStart + selText.length;
  } else if (
    selText.startsWith(before) &&
    selText.endsWith(after) &&
    selText.length >= before.length + after.length
  ) {
    // Selection itself includes the markers: unwrap to the inner text.
    const inner = selText.slice(before.length, selText.length - after.length);
    draft.value = val.slice(0, s) + inner + val.slice(e);
    newStart = s;
    newEnd = newStart + inner.length;
  } else {
    // Not wrapped: wrap it (or insert a placeholder when there is nothing to wrap).
    const target = selText || placeholder;
    const inserted = before + target + after;
    draft.value = val.slice(0, s) + inserted + val.slice(e);
    newStart = s + before.length;
    newEnd = newStart + target.length;
  }
  if (ta) {
    nextTick(() => {
      ta.focus();
      ta.setSelectionRange(newStart, newEnd);
    });
  }
}

// The heading/block buttons operate on whole lines. This returns the bounds of the selected line
// range (expanding a collapsed cursor to its full line) so each toggle can read/replace the block.
function selectedLineBounds(ta, val) {
  const s = ta ? ta.selectionStart : val.length;
  const e = ta ? ta.selectionEnd : val.length;
  const lineStart = val.lastIndexOf('\n', s - 1) + 1;
  let lineEnd = val.indexOf('\n', e);
  if (lineEnd === -1) lineEnd = val.length;
  return { lineStart, lineEnd, lines: val.slice(lineStart, lineEnd).split('\n') };
}

// Simple per-line prefix (bullet / quote). Toggles: if every selected line already has the prefix,
// remove it; otherwise add it to every line.
function togglePrefix(marker) {
  const ta = textareaEl();
  const val = draft.value;
  const { lineStart, lineEnd, lines } = selectedLineBounds(ta, val);
  const active = lines.every((l) => l.startsWith(marker));
  const newLines = lines.map((l) => (active ? l.slice(marker.length) : marker + l));
  const newBlock = newLines.join('\n');
  draft.value = val.slice(0, lineStart) + newBlock + val.slice(lineEnd);
  if (ta) {
    nextTick(() => {
      ta.focus();
      ta.setSelectionRange(lineStart, lineStart + newBlock.length);
    });
  }
}

// Ordered list: toggles the `n. ` prefix off when present, otherwise renumbers every selected line
// from 1. We strip any existing `n. ` first so re-clicking converts rather than stacking numbers.
function toggleNumbered() {
  const ta = textareaEl();
  const val = draft.value;
  const { lineStart, lineEnd, lines } = selectedLineBounds(ta, val);
  const active = lines.every((l) => /^\d+\.\s/.test(l));
  const newLines = lines.map((l, i) => {
    const stripped = l.replace(/^\d+\.\s?/, '');
    return active ? stripped : `${i + 1}. ${stripped}`;
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

// Heading (H1-H6): toggles the exact level off when every selected line already has it; otherwise
// converts every line to that level (replacing any other heading level, or adding it). This is what
// makes the level buttons behave like a radio group: clicking the active level removes it, clicking
// another level switches to it instead of stripping the line to plain text.
function toggleHeading(level) {
  const ta = textareaEl();
  const val = draft.value;
  const { lineStart, lineEnd, lines } = selectedLineBounds(ta, val);
  const marker = '#'.repeat(level) + ' ';
  const active = lines.every((l) => l.startsWith(marker));
  const newLines = lines.map((l) => {
    const withoutHeading = l.replace(/^#+\s?/, '');
    return active ? withoutHeading : marker + withoutHeading;
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

const headingLevels = [1, 2, 3, 4, 5, 6];

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
