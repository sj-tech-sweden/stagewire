<template>
  <q-dialog
    :model-value="modelValue"
    :maximized="$q.screen.lt.sm"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <q-card class="channel-edit-card">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">
          {{ t('channels.editChannel') }}
        </div>
        <q-space />
        <q-btn
          icon="close"
          flat
          round
          dense
          @click="emit('update:modelValue', false)"
        />
      </q-card-section>

      <q-card-section
        v-if="channel"
        class="q-pt-none q-gutter-sm"
      >
        <div class="row q-col-gutter-sm">
          <q-input
            :model-value="channel.attributes.channel_number"
            type="number"
            class="col-6 col-sm-3"
            dense
            outlined
            :label="t('channels.fieldChannelNumber')"
            data-testid="channel-edit-number"
            @change="(v) => (form.channel_number = v === '' || v == null ? null : Number(v))"
          />
          <q-input
            v-model="form.name"
            class="col-12 col-sm-9"
            dense
            outlined
            :label="t('channels.fieldSource')"
            data-testid="channel-edit-name"
          />
        </div>

        <q-select
          v-model="form.input_type"
          dense
          outlined
          clearable
          emit-value
          map-options
          :options="inputTypes"
          :label="t('workspace.colKind')"
          data-testid="channel-edit-kind"
        />

        <StockwireProductPicker
          :model-value="sourceOfForm"
          own
          :local-items="gearItems"
          :label="t('channels.fieldDevice')"
          :hint="''"
          @update:model-value="onPickSource"
        />

        <StockwireProductPicker
          :model-value="standOfForm"
          gear-type="stand"
          own
          :label="t('stockwire.selectStand')"
          :hint="''"
          @update:model-value="onPickStand"
        />

        <div class="row q-col-gutter-sm">
          <q-select
            v-model="form.instrument_group"
            class="col-12 col-sm-6"
            dense
            outlined
            emit-value
            map-options
            :options="groupOptions"
            :label="t('channels.instrumentGroup')"
            data-testid="channel-edit-group"
          />
          <q-input
            v-model="form.performer_name"
            class="col-12 col-sm-6"
            dense
            outlined
            :label="t('channels.fieldPerformer')"
            data-testid="channel-edit-performer"
          />
        </div>

        <div class="row items-center q-gutter-sm">
          <q-checkbox
            :model-value="!!form.phantom_power"
            :disable="channel.attributes.stereo_link_role === 'secondary'"
            :label="t('channels.fieldPhantom')"
            data-testid="channel-edit-phantom"
            @update:model-value="(v) => (form.phantom_power = v)"
          />
          <q-checkbox
            :model-value="!!form.stereo"
            :label="t('channels.fieldStereo')"
            data-testid="channel-edit-stereo"
            @update:model-value="(v) => (form.stereo = v)"
          />
          <q-chip
            v-if="stereoViewOf(channel).linked"
            dense
            color="primary"
            text-color="white"
            size="sm"
          >
            {{ stereoViewOf(channel).isL ? "L" : "R" }}
          </q-chip>
        </div>

        <div class="row items-center q-gutter-xs">
          <span class="text-caption">{{ t('channels.fieldColor') }}</span>
          <q-btn
            dense
            flat
            no-caps
            round
            size="sm"
            class="channel-edit-swatch"
            :class="{ 'channel-swatch--unset': !form.color_code }"
            :style="swatchStyle(form.color_code)"
            :disable="channel.attributes.stereo_link_role === 'secondary'"
            :aria-label="t('workspace.colourPick')"
          >
            <q-popup-proxy v-if="channel.attributes.stereo_link_role !== 'secondary'">
              <q-card
                class="q-pa-sm"
                style="width: 260px"
              >
                <div class="row q-gutter-xs q-mb-sm">
                  <q-btn
                    v-for="preset in PRESET_COLOURS"
                    :key="preset"
                    dense
                    unelevated
                    round
                    size="sm"
                    :style="{ background: preset }"
                    :aria-label="preset"
                    @click="form.color_code = preset"
                  />
                </div>
                <q-color
                  v-model="form.color_code"
                  format-model="hex"
                  no-header
                  no-footer
                  default-view="spectrum"
                  flat
                />
                <q-btn
                  v-close-popup
                  flat
                  dense
                  no-caps
                  icon="format_color_reset"
                  :label="t('workspace.colourClear')"
                  :disable="!form.color_code"
                  @click="form.color_code = null"
                />
              </q-card>
            </q-popup-proxy>
          </q-btn>
        </div>

        <template v-if="form.input_type === 'wireless'">
          <div class="text-subtitle2 q-mt-sm">
            {{ t('channels.wirelessDetails') }}
          </div>
          <q-input
            v-model="form.wireless_pack"
            dense
            outlined
            :label="t('channels.fieldWirelessPack')"
            data-testid="channel-edit-wireless-pack"
          />
          <div class="row q-col-gutter-sm">
            <q-input
              v-model="form.wireless_frequency_mhz"
              class="col-6"
              dense
              outlined
              type="number"
              step="0.001"
              :label="t('channels.fieldWirelessFrequencyMhz')"
              data-testid="channel-edit-wireless-freq"
            />
            <q-input
              v-model="form.wireless_group"
              class="col-3"
              dense
              outlined
              :label="t('channels.fieldWirelessGroup')"
              data-testid="channel-edit-wireless-group"
            />
            <q-input
              v-model="form.wireless_channel"
              class="col-3"
              dense
              outlined
              :label="t('channels.fieldWirelessChannel')"
              data-testid="channel-edit-wireless-channel"
            />
          </div>
        </template>

        <div class="text-subtitle2 q-mt-sm">
          {{ t('channels.fieldNotes') }}
        </div>
        <div class="row items-start q-gutter-xs">
          <NotesDisplay
            v-if="form.notes"
            class="col"
            :notes="form.notes"
            :rows="4"
          />
          <q-btn
            dense
            flat
            no-caps
            size="sm"
            :icon="form.notes ? 'edit' : 'add'"
            :label="form.notes ? undefined : t('channels.fieldNotes')"
            :aria-label="t('workspace.editNotes')"
            data-testid="channel-edit-notes"
            @click="notesOpen = true"
          />
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          :label="t('workspace.cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          color="primary"
          unelevated
          :label="t('workspace.save')"
          data-testid="channel-edit-save"
          @click="onSave"
        />
      </q-card-actions>

      <MarkdownEditorDialog
        v-model="notesOpen"
        :title="t('channels.fieldNotes')"
        :value="form.notes || ''"
        @save="(text) => (form.notes = text)"
      />
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import StockwireProductPicker from '@/components/StockwireProductPicker.vue';
import NotesDisplay from '@/components/NotesDisplay.vue';
import MarkdownEditorDialog from '@/components/MarkdownEditorDialog.vue';
import { INSTRUMENT_GROUP_KEYS } from '@/utils/instrumentGroups';
import { PRESET_COLOURS, colourToHex, normalizeHex, readableTextColour } from '@/utils/colour';

// A consolidated editor for one sound channel-list row: it exposes the channel's full attribute set
// (kind, source mic/stand, instrument group, performer, 48V, stereo, colour, wireless block and
// notes) in one modal instead of the cramped inline card expansion. It emits a diff that the parent
// applies through the same graph save / stereo-link paths, so realtime sync is unchanged.
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  channel: { type: Object, default: null },
  gearItems: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue', 'save', 'set-stereo']);
const { t } = useI18n();
const $q = useQuasar();

const inputTypes = ['microphone', 'di', 'wireless', 'fxReturn'].map((v) => ({
  value: v,
  label: t(`channels.type.${v}`),
}));
const groupOptions = INSTRUMENT_GROUP_KEYS.map((v) => ({
  value: v,
  label: t(`channels.instrumentGroups.${v}`),
}));

const notesOpen = ref(false);
const form = ref(channelForm());

function channelForm() {
  const ch = props.channel;
  const a = ch?.attributes || {};
  return {
    name: ch?.name ?? '',
    channel_number: a.channel_number ?? null,
    input_type: a.input_type ?? null,
    source_label: a.source_label ?? null,
    stockwire_product_id: a.stockwire_product_id ?? null,
    stockwire_product_name: a.stockwire_product_name ?? null,
    stand_product_id: a.stand_product_id ?? null,
    stand_product_name: a.stand_product_name ?? null,
    instrument_group: a.instrument_group ?? 'other',
    performer_name: a.performer_name ?? null,
    phantom_power: !!a.phantom_power,
    stereo: !!a.stereo,
    color_code: a.color_code ?? null,
    wireless_pack: a.wireless_pack ?? null,
    wireless_frequency_mhz: a.wireless_frequency_mhz ?? null,
    wireless_group: a.wireless_group ?? null,
    wireless_channel: a.wireless_channel ?? null,
    notes: ch?.notes ?? '',
  };
}

watch(
  () => props.modelValue,
  (open) => {
    if (open && props.channel) Object.assign(form.value, channelForm());
  },
  { immediate: true },
);

const sourceOfForm = () =>
  form.value.stockwire_product_name
    ? { id: form.value.stockwire_product_id, name: form.value.stockwire_product_name }
    : null;
const standOfForm = () =>
  form.value.stand_product_name
    ? { id: form.value.stand_product_id, name: form.value.stand_product_name }
    : null;

function onPickSource(pick) {
  form.value.stockwire_product_id = pick?.id ? String(pick.id) : null;
  form.value.stockwire_product_name = pick?.name || null;
  if (pick?.name && !form.value.source_label) form.value.source_label = pick.name;
}
function onPickStand(pick) {
  form.value.stand_product_id = pick?.id ? String(pick.id) : null;
  form.value.stand_product_name = pick?.name || null;
}

function swatchStyle(value) {
  if (!value) return {};
  const hex = colourToHex(value);
  return hex
    ? { background: hex, color: readableTextColour(hex) }
    : { background: '#9e9e9e', color: '#000' };
}

// The server mirrors the secondary leg's name/colour/group, so a secondary row cannot drive those
// here; the parent still renders the chip via the same helper it uses everywhere.
function stereoViewOf(channel) {
  const a = channel?.attributes || {};
  const linked = a.stereo_link_role === 'primary' || a.stereo_link_role === 'secondary';
  const isPrimary = a.stereo_link_role === 'primary';
  return { linked, isL: isPrimary };
}

// Normalise a form value the way the node stores it so an unchanged field is not needlessly written.
function norm(value, type) {
  if (type === 'number') {
    if (value === '' || value == null) return null;
    const n = Number(value);
    return Number.isNaN(n) ? null : n;
  }
  if (type === 'bool') return !!value;
  if (value === '' || value == null) return null;
  return value;
}

const ATTRIBUTE_KEYS = {
  input_type: 'string',
  stockwire_product_id: 'string',
  stockwire_product_name: 'string',
  stand_product_id: 'string',
  stand_product_name: 'string',
  source_label: 'string',
  instrument_group: 'string',
  performer_name: 'string',
  phantom_power: 'bool',
  color_code: 'string',
  wireless_pack: 'string',
  wireless_frequency_mhz: 'number',
  wireless_group: 'string',
  wireless_channel: 'string',
};

function onSave() {
  const ch = props.channel;
  if (!ch) return;
  const changes = {};
  if (form.value.name !== ch.name) changes.name = form.value.name;

  const attributes = {};
  for (const [key, type] of Object.entries(ATTRIBUTE_KEYS)) {
    const next = norm(form.value[key], type);
    const current = norm(ch.attributes?.[key], type);
    if (next !== current) attributes[key] = next;
  }
  if (Object.keys(attributes).length) changes.attributes = attributes;

  const number = norm(form.value.channel_number, 'number');
  if (number !== norm(ch.attributes?.channel_number, 'number')) {
    changes.attributes = { ...(changes.attributes || {}), channel_number: number };
    changes.position = number;
  }

  const stereoChanged = form.value.stereo !== !!ch.attributes?.stereo;
  if (Object.keys(changes).length) emit('save', changes);
  if (stereoChanged) emit('set-stereo', form.value.stereo);
  if (Object.keys(changes).length || stereoChanged) emit('update:modelValue', false);
}
</script>

<style scoped>
.channel-edit-card {
  width: 720px;
  max-width: 100vw;
}
</style>
