<template>
  <div
    class="row items-center no-wrap"
    data-testid="history-controls"
  >
    <q-btn
      flat
      round
      dense
      icon="undo"
      :disable="!history.canUndo || history.busy"
      :aria-label="t('history.undo')"
      data-testid="history-undo"
      @click="doUndo"
    >
      <q-tooltip>{{ history.canUndo ? t('history.undoTip', { label: title(history.undoEntry) }) : t('history.nothingToUndo') }}</q-tooltip>
    </q-btn>
    <q-btn
      flat
      round
      dense
      icon="redo"
      :disable="!history.canRedo || history.busy"
      :aria-label="t('history.redo')"
      data-testid="history-redo"
      @click="doRedo"
    >
      <q-tooltip>{{ history.canRedo ? t('history.redoTip', { label: title(history.redoEntry) }) : t('history.nothingToRedo') }}</q-tooltip>
    </q-btn>
    <q-btn
      flat
      round
      dense
      icon="history"
      :aria-label="t('history.open')"
      data-testid="history-open"
      @click="open"
    >
      <q-tooltip>{{ t('history.open') }}</q-tooltip>
    </q-btn>

    <q-dialog
      v-model="drawer"
      position="right"
      :maximized="$q.screen.lt.sm"
    >
      <q-card
        class="column no-wrap"
        style="width: 440px; max-width: 100vw; height: 100vh"
        data-testid="history-drawer"
      >
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">
            {{ t('history.title') }}
          </div>
          <q-space />
          <q-btn
            v-close-popup
            flat
            round
            dense
            icon="close"
            :aria-label="t('history.close')"
          />
        </q-card-section>
        <q-card-section class="text-caption text-grey-6">
          {{ t('history.intro') }}
        </q-card-section>
        <q-separator />
        <div
          v-if="!history.entries.length"
          class="q-pa-md text-grey-6"
          data-testid="history-empty"
        >
          {{ t('history.empty') }}
        </div>
        <q-list
          v-else
          separator
          class="col scroll"
        >
          <q-item
            v-for="e in history.entries"
            :key="e.seq"
            clickable
            :class="{ 'history-undone': e.undone }"
            :active="e.seq === history.cursor"
            active-class="bg-primary text-white"
            data-testid="history-entry"
            @click="confirmRestore(e)"
          >
            <q-item-section>
              <q-item-label>{{ stepName(e) }}</q-item-label>
              <q-item-label
                v-if="e.summary"
                caption
                :class="e.seq === history.cursor ? 'text-white' : ''"
              >
                {{ e.summary }}
              </q-item-label>
              <q-item-label
                caption
                :class="e.seq === history.cursor ? 'text-white' : ''"
              >
                {{ relativeTime(e.created_at, now, locale) }}
                <span v-if="e.actor"> · {{ t('history.by', { who: e.actor }) }}</span>
                · {{ t('history.changes', { n: e.changes }) }}
              </q-item-label>
            </q-item-section>
            <q-item-section
              v-if="e.seq === history.cursor"
              side
            >
              <q-badge
                color="white"
                text-color="primary"
                data-testid="history-current"
              >
                {{ t('history.current') }}
              </q-badge>
            </q-item-section>
          </q-item>
          <q-item
            clickable
            :active="history.cursor === 0"
            active-class="bg-primary text-white"
            data-testid="history-entry-start"
            @click="confirmRestore(null)"
          >
            <q-item-section>
              <q-item-label>{{ t('history.beforeAll') }}</q-item-label>
            </q-item-section>
            <q-item-section
              v-if="history.cursor === 0"
              side
            >
              <q-badge
                color="white"
                text-color="primary"
              >
                {{ t('history.current') }}
              </q-badge>
            </q-item-section>
          </q-item>
        </q-list>
        <q-inner-loading :showing="history.busy" />
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
// Undo / redo buttons, Ctrl/Cmd+Z shortcuts and the version drawer for the open job or venue.
// Reloading what the workspace shows after a step is the page's job (`restored` event); the server
// also broadcasts `history.restore` so other open tabs reload.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useHistoryStore } from '@/stores/history';
import { apiErrorText } from '@/utils/errors';
import { historyStepLabel } from '@/utils/workspace';
import { entryTitle, isHistoryConflict, isNothingToDo, relativeTime, shortcutAction } from '@/utils/history';

const props = defineProps({
  kind: { type: String, default: 'job' },
  scopeId: { type: String, required: true },
});
const emit = defineEmits(['restored']);
const { t, te, locale } = useI18n();
// step names come from the server as an `action` key and are translated here (history.actions.*)
const tr = { has: (key) => te(key), t: (key) => t(key) };
const title = (entry) => entryTitle(entry, tr);
const stepName = (entry) => historyStepLabel(entry, tr);
const $q = useQuasar();
const history = useHistoryStore();
const drawer = ref(false);
const now = ref(Date.now());

function bind() {
  history.setScope(props.kind, props.scopeId);
  history.refresh();
}
watch(() => [props.kind, props.scopeId], bind);

function open() {
  now.value = Date.now();
  history.refresh();
  drawer.value = true;
}

// Run one history call; a conflict (rows changed outside the history) lists them and offers to go on.
async function run(call, message) {
  try {
    const data = await call(false);
    emit('restored');
    message?.(data);
    return data;
  } catch (err) {
    if (isHistoryConflict(err)) {
      const list = err.response.data.detail.conflicts.map((c) => `• ${c}`).join('\n');
      $q.dialog({
        title: t('history.conflictTitle'),
        message: `${t('history.conflictMessage')}\n${list}`,
        ok: { label: t('history.anyway'), color: 'warning', noCaps: true, 'data-testid': 'history-force' },
        cancel: { flat: true, noCaps: true },
        persistent: true,
      }).onOk(async () => {
        try {
          const data = await call(true);
          emit('restored');
          message?.(data);
        } catch (e) {
          $q.notify({ type: 'negative', message: apiErrorText(e, t('history.failed')) });
        }
      });
    } else if (isNothingToDo(err)) {
      await history.refresh();
    } else {
      $q.notify({ type: 'negative', message: apiErrorText(err, t('history.failed')) });
    }
    return null;
  }
}

async function doUndo() {
  if (!history.canUndo || history.busy) return;
  const label = title(history.undoEntry);
  await run(
    (force) => history.undo(force),
    () =>
      $q.notify({
        message: t('history.undone', { label }),
        timeout: 5000,
        actions: [{ label: t('history.redo'), color: 'white', handler: () => doRedo() }],
      }),
  );
}
async function doRedo() {
  if (!history.canRedo || history.busy) return;
  const label = title(history.redoEntry);
  await run(
    (force) => history.redo(force),
    () =>
      $q.notify({
        message: t('history.redone', { label }),
        timeout: 5000,
        actions: [{ label: t('history.undo'), color: 'white', handler: () => doUndo() }],
      }),
  );
}

// tapping a version: confirm, then step the whole way there (undo or redo entry by entry)
function confirmRestore(entry) {
  const seq = entry ? entry.seq : 0;
  if (seq === history.cursor) return;
  $q.dialog({
    title: t('history.restoreTitle'),
    message: entry ? t('history.restoreConfirm', { label: title(entry) }) : t('history.restoreConfirmStart'),
    ok: { label: t('history.restore'), color: 'primary', noCaps: true, 'data-testid': 'history-restore-ok' },
    cancel: { flat: true, noCaps: true },
    persistent: true,
  }).onOk(() =>
    run(
      (force) => history.restore(seq, force),
      () => $q.notify({ type: 'positive', message: t('history.restored', { label: entry ? title(entry) : t('history.beforeAll') }) }),
    ),
  );
}

function onKey(event) {
  const action = shortcutAction(event);
  if (!action) return;
  event.preventDefault();
  if (action === 'undo') doUndo();
  else doRedo();
}

onMounted(() => {
  bind();
  window.addEventListener('keydown', onKey);
});
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
defineExpose({ refresh: () => history.refresh() });
</script>

<style scoped>
.history-undone {
  opacity: 0.55;
}
</style>
