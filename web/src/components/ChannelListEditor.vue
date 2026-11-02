<template>
  <div data-testid="channel-list-editor">
    <div class="row items-center q-gutter-sm q-mb-md">
      <q-tabs
        v-model="listId"
        dense
        align="left"
        class="col"
        active-color="primary"
        indicator-color="primary"
        inline-label
        mobile-arrows
      >
        <q-tab
          v-for="entry in graph.channelLists"
          :key="entry.id"
          :name="entry.id"
          :label="entry.name"
          no-caps
          data-testid="list-tab"
        />
      </q-tabs>
      <q-btn
        flat
        no-caps
        icon="playlist_add"
        :label="t('workspace.addList')"
        data-testid="add-list"
        @click="addList"
      />
    </div>

    <div v-if="!list" class="text-grey-6">
      {{ t("workspace.noLists") }}
    </div>

    <template v-else>
      <q-card
        flat
        bordered
        class="q-pa-sm q-mb-sm row items-center q-gutter-sm"
        data-testid="list-mixer"
      >
        <q-icon name="tune" color="primary" size="sm" />
        <div class="col">
          <div class="text-caption text-grey-7">
            {{ t("stockwire.mixerOfList") }}
          </div>
          <div
            v-if="
              list.attributes.mixer_product_name ||
              list.attributes.mixer_inputs != null ||
              list.attributes.mixer_buses != null
            "
          >
            {{ list.attributes.mixer_product_name }}
            <span
              v-if="list.attributes.mixer_inputs != null"
              class="text-grey-7"
            >
              · {{ list.attributes.mixer_inputs }}
              {{ t("stockwire.inputsShort") }}</span
            >
            <span
              v-if="list.attributes.mixer_buses != null"
              class="text-grey-7"
            >
              · {{ list.attributes.mixer_buses }}
              {{ t("stockwire.busesShort") }}</span
            >
          </div>
          <div v-else class="text-grey-7">
            {{ t("stockwire.mixerNotSet") }}
          </div>
        </div>
        <div
          v-if="listMixers.length"
          class="row q-gutter-xs"
          data-testid="list-mixer-devices"
        >
          <q-chip
            v-for="mixer in listMixers"
            :key="mixer.id"
            dense
            clickable
            square
            icon="edit"
            data-testid="chain-device"
            @click="editDevice(mixer)"
          >
            {{ mixer.name }}
            <q-tooltip>{{ t("workspace.editDevice") }}</q-tooltip>
          </q-chip>
        </div>
        <q-btn
          outline
          no-caps
          color="primary"
          icon="edit"
          :label="
            list.attributes.mixer_product_name ||
            list.attributes.mixer_inputs != null
              ? t('stockwire.changeMixer')
              : t('stockwire.setMixer')
          "
          data-testid="set-mixer"
          @click="mixerOpen = true"
        />
        <q-btn
          outline
          no-caps
          color="secondary"
          icon="file_upload"
          :label="t('channels.importWirelessWorkbench')"
          data-testid="import-wwb"
          :loading="wwbImporting || wwbParsing"
          @click="wwbFileInput?.click()"
        />
        <input
          ref="wwbFileInput"
          type="file"
          accept=".shw,application/xml"
          class="hidden"
          data-testid="wwb-file"
          @change="onWwbFile"
        />
      </q-card>
      <div class="row items-center q-gutter-sm q-mb-sm">
        <q-input
          :model-value="list.name"
          dense
          outlined
          class="col-12 col-sm-4"
          :label="t('workspace.listName')"
          @change="(v) => save(list, { name: v })"
        />
        <q-btn
          color="primary"
          no-caps
          icon="add"
          :label="t('workspace.addChannel')"
          data-testid="add-channel"
          @click="addChannels(1)"
        />
        <q-btn
          flat
          no-caps
          icon="playlist_add"
          :label="t('workspace.bulkAdd')"
          data-testid="bulk-channels"
          @click="bulkChannels = true"
        />
        <q-btn
          flat
          no-caps
          icon="cloud_upload"
          :loading="syncing"
          :label="t('workspace.syncStockwire')"
          data-testid="sync-stockwire"
          @click="syncStockwire"
        />
        <q-space />
        <q-btn
          flat
          dense
          no-caps
          color="negative"
          icon="delete"
          :label="t('workspace.deleteList')"
          @click="removeList"
        />
      </div>

      <div class="text-subtitle1 q-mt-md">
        {{ t("workspace.inputs") }}
      </div>
      <!-- On phones every channel is a card with the same editors as the table row: the header
           has the number, name and actions, the summary line says what is set, and "Details"
           opens kind, source, stand, connector, 48V, stereo, wireless and notes. -->
      <div
        v-if="$q.screen.lt.sm"
        class="column q-gutter-sm"
        data-testid="channel-cards"
      >
        <q-card
          v-for="ch in channels"
          :key="ch.id"
          flat
          bordered
          data-testid="channel-card"
        >
          <q-card-section class="q-pa-sm">
            <div class="row items-center no-wrap">
              <div class="text-subtitle2 q-pr-sm">
                {{ ch.attributes.channel_number }}
              </div>
              <q-input
                :model-value="ch.name"
                dense
                borderless
                class="col"
                data-testid="channel-card-label"
                @change="(v) => save(ch, { name: v })"
              />
              <q-btn
                flat
                dense
                round
                icon="route"
                :aria-label="t('workspace.editChain')"
                @click="openChain(ch, 'channel')"
              />
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('workspace.showFlow')"
                @click="openFlow(ch, 'channel')"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                @click="removeNode(ch)"
              />
            </div>
            <div class="text-caption text-grey-6">
              {{ channelSummary(ch) || t("workspace.chainEmpty") }}
            </div>
            <div class="text-caption text-grey-6">
              {{ chain(ch) || t("workspace.chainEmpty") }}
            </div>
          </q-card-section>
          <q-expansion-item
            dense
            :label="t('workspace.details')"
            header-class="text-caption"
            data-testid="channel-card-details"
          >
            <div class="q-pa-sm q-gutter-sm">
              <q-select
                :model-value="ch.attributes.input_type"
                dense
                outlined
                clearable
                emit-value
                map-options
                :options="inputTypes"
                :label="t('workspace.colKind')"
                @update:model-value="(v) => saveAttr(ch, 'input_type', v)"
              />
              <div
                v-if="ch.attributes.input_type === 'wireless'"
                class="row q-col-gutter-sm"
              >
                <q-input
                  :model-value="ch.attributes.wireless_pack"
                  class="col-12 col-sm-6"
                  dense
                  outlined
                  :label="t('channels.fieldWirelessPack')"
                  @change="(v) => saveAttr(ch, 'wireless_pack', v)"
                />
                <q-input
                  :model-value="ch.attributes.wireless_frequency_mhz"
                  class="col-6"
                  dense
                  outlined
                  type="number"
                  step="0.001"
                  :label="t('channels.fieldWirelessFrequencyMhz')"
                  @change="
                    (v) =>
                      saveAttr(
                        ch,
                        'wireless_frequency_mhz',
                        v === '' || v === null ? null : Number(v),
                      )
                  "
                />
                <q-input
                  :model-value="ch.attributes.wireless_group"
                  class="col-3"
                  dense
                  outlined
                  :label="t('channels.fieldWirelessGroup')"
                  @change="(v) => saveAttr(ch, 'wireless_group', v || null)"
                />
                <q-input
                  :model-value="ch.attributes.wireless_channel"
                  class="col-3"
                  dense
                  outlined
                  :label="t('channels.fieldWirelessChannel')"
                  @change="(v) => saveAttr(ch, 'wireless_channel', v || null)"
                />
              </div>
              <StockwireProductPicker
                :model-value="sourceOf(ch)"
                own
                :local-items="gearItems"
                :label="t('channels.fieldDevice')"
                :hint="''"
                @update:model-value="(p) => setSource(ch, p)"
              />
              <q-btn
                v-if="sourceDevice(ch)"
                flat
                dense
                no-caps
                icon="edit"
                :label="t('workspace.editSource')"
                @click="editDevice(sourceDevice(ch))"
              />
              <StockwireProductPicker
                :model-value="standOf(ch)"
                gear-type="stand"
                own
                :label="t('stockwire.selectStand')"
                :hint="''"
                @update:model-value="(p) => setStand(ch, p)"
              />
              <ConnectorSelect
                :model-value="ch.attributes.connector || ''"
                @update:model-value="(v) => saveAttr(ch, 'connector', v)"
              />
              <div class="row items-center">
                <q-checkbox
                  :model-value="!!ch.attributes.phantom_power"
                  label="48V"
                  @update:model-value="(v) => saveAttr(ch, 'phantom_power', v)"
                />
                <q-checkbox
                  :model-value="!!ch.attributes.stereo"
                  :label="t('channels.fieldStereo')"
                  @update:model-value="(v) => setStereo(ch, v)"
                />
                <q-chip
                  v-if="stereoView(ch, channels).linked"
                  dense
                  color="primary"
                  text-color="white"
                  size="sm"
                >
                  {{ stereoView(ch, channels).isL ? "L" : "R" }}
                </q-chip>
              </div>
              <q-input
                :model-value="ch.notes"
                dense
                outlined
                autogrow
                :label="t('workspace.colNotes')"
                @change="(v) => save(ch, { notes: v })"
              />
            </div>
          </q-expansion-item>
        </q-card>
      </div>
      <q-table
        v-else
        flat
        dense
        bordered
        virtual-scroll
        :virtual-scroll-item-size="44"
        :rows="channels"
        :columns="columns"
        row-key="id"
        :rows-per-page-options="[0]"
        hide-bottom
        class="sticky-header-table"
        style="max-height: 70vh"
        data-testid="channel-table"
      >
        <template #body-cell-number="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.attributes.channel_number"
              dense
              borderless
              type="number"
              style="width: 60px"
              @change="(v) => setNumber(slot.row, Number(v))"
            />
          </q-td>
        </template>
        <template #body-cell-name="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.name"
              dense
              borderless
              data-testid="channel-label"
              @change="(v) => save(slot.row, { name: v })"
            />
          </q-td>
        </template>
        <template #body-cell-input_type="slot">
          <q-td :props="slot">
            <q-select
              :model-value="slot.row.attributes.input_type"
              dense
              borderless
              clearable
              emit-value
              map-options
              :options="inputTypes"
              @update:model-value="(v) => saveAttr(slot.row, 'input_type', v)"
            />
            <div
              v-if="slot.row.attributes.input_type === 'wireless'"
              class="row no-wrap q-gutter-xs"
            >
              <q-input
                :model-value="slot.row.attributes.wireless_pack"
                dense
                borderless
                :placeholder="t('channels.fieldWirelessPack')"
                data-testid="wireless-pack"
                @change="(v) => saveAttr(slot.row, 'wireless_pack', v)"
              />
              <q-input
                :model-value="slot.row.attributes.wireless_frequency_mhz"
                dense
                borderless
                type="number"
                step="0.001"
                :placeholder="t('channels.fieldWirelessFrequencyMhz')"
                data-testid="wireless-frequency-mhz"
                @change="
                  (v) =>
                    saveAttr(
                      slot.row,
                      'wireless_frequency_mhz',
                      v === '' || v === null ? null : Number(v),
                    )
                "
              />
              <q-input
                :model-value="slot.row.attributes.wireless_group"
                dense
                borderless
                :placeholder="t('channels.fieldWirelessGroup')"
                data-testid="wireless-group"
                @change="(v) => saveAttr(slot.row, 'wireless_group', v || null)"
              />
              <q-input
                :model-value="slot.row.attributes.wireless_channel"
                dense
                borderless
                :placeholder="t('channels.fieldWirelessChannel')"
                data-testid="wireless-channel"
                @change="
                  (v) => saveAttr(slot.row, 'wireless_channel', v || null)
                "
              />
            </div>
          </q-td>
        </template>
        <template #body-cell-device="slot">
          <q-td :props="slot" style="min-width: 160px; max-width: 200px">
            <StockwireProductPicker
              :model-value="sourceOf(slot.row)"
              own
              :local-items="gearItems"
              :label="t('channels.fieldDevice')"
              :hint="''"
              borderless
              data-testid="source-picker"
              @update:model-value="(p) => setSource(slot.row, p)"
            />
            <q-btn
              v-if="sourceDevice(slot.row)"
              flat
              dense
              no-caps
              size="sm"
              icon="edit"
              :label="t('workspace.editSource')"
              data-testid="open-source-device"
              @click="editDevice(sourceDevice(slot.row))"
            />
          </q-td>
        </template>
        <template #body-cell-stand_type="slot">
          <q-td :props="slot" style="min-width: 150px; max-width: 190px">
            <StockwireProductPicker
              :model-value="standOf(slot.row)"
              gear-type="stand"
              own
              :label="t('stockwire.selectStand')"
              :hint="''"
              borderless
              data-testid="stand-picker"
              @update:model-value="(p) => setStand(slot.row, p)"
            />
          </q-td>
        </template>
        <template #body-cell-connector="slot">
          <q-td :props="slot">
            <ConnectorSelect
              :model-value="slot.row.attributes.connector || ''"
              borderless
              @update:model-value="(v) => saveAttr(slot.row, 'connector', v)"
            />
          </q-td>
        </template>
        <template #body-cell-stereo="slot">
          <q-td :props="slot">
            <q-checkbox
              :model-value="!!slot.row.attributes.stereo"
              dense
              data-testid="channel-stereo"
              @update:model-value="(v) => setStereo(slot.row, v)"
            />
            <q-chip
              v-if="stereoView(slot.row, channels).linked"
              dense
              color="primary"
              text-color="white"
              size="sm"
              data-testid="stereo-side"
            >
              {{ stereoView(slot.row, channels).isL ? "L" : "R" }}
              <q-tooltip>{{
                t("channels.stereoLinkedTo", {
                  ch: slot.row.attributes.stereo_channel,
                })
              }}</q-tooltip>
            </q-chip>
          </q-td>
        </template>
        <template
          v-for="flag in ['phantom_power']"
          #[`body-cell-${flag}`]="slot"
          :key="flag"
        >
          <q-td :props="slot">
            <q-checkbox
              :model-value="!!slot.row.attributes[flag]"
              dense
              @update:model-value="(v) => saveAttr(slot.row, flag, v)"
            />
          </q-td>
        </template>
        <template #body-cell-notes="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.notes"
              dense
              borderless
              @change="(v) => save(slot.row, { notes: v })"
            />
          </q-td>
        </template>
        <template #body-cell-chain="slot">
          <q-td :props="slot" class="chain-cell">
            <q-btn
              flat
              dense
              no-caps
              icon="route"
              :label="chain(slot.row) || t('workspace.chainEmpty')"
              data-testid="edit-chain"
              @click="openChain(slot.row, 'channel')"
            />
            <q-btn
              flat
              dense
              round
              icon="account_tree"
              :aria-label="t('workspace.showFlow')"
              data-testid="show-flow"
              @click="openFlow(slot.row, 'channel')"
            />
          </q-td>
        </template>
        <template #body-cell-actions="slot">
          <q-td :props="slot">
            <q-btn
              flat
              dense
              round
              color="negative"
              icon="delete"
              :aria-label="t('workspace.remove')"
              @click="removeNode(slot.row)"
            />
          </q-td>
        </template>
      </q-table>

      <div class="row items-center q-mt-lg q-mb-sm">
        <div class="text-subtitle1 col">
          {{ t("workspace.outputs") }}
        </div>
        <q-btn
          flat
          no-caps
          icon="add"
          :label="t('workspace.addOutput')"
          data-testid="add-output"
          @click="addOutput"
        />
        <q-btn
          flat
          no-caps
          icon="playlist_add"
          :label="t('workspace.bulkAdd')"
          data-testid="bulk-outputs"
          @click="bulkOutputs = true"
        />
      </div>
      <q-list bordered separator>
        <q-item v-for="out in outputs" :key="out.id" data-testid="output-row">
          <q-item-section>
            <q-input
              :model-value="out.name"
              dense
              borderless
              @change="(v) => save(out, { name: v })"
            />
            <q-item-label caption>
              {{ chain(out) || t("workspace.chainEmpty") }}
            </q-item-label>
          </q-item-section>
          <q-item-section side style="min-width: 150px">
            <q-select
              :model-value="out.attributes.mode || 'mono'"
              :options="modeOptions"
              emit-value
              map-options
              dense
              outlined
              :label="t('channels.outputMode')"
              data-testid="output-mode"
              @update:model-value="(v) => saveAttr(out, 'mode', v)"
            />
          </q-item-section>
          <q-item-section side>
            <div class="row">
              <q-btn
                flat
                dense
                round
                icon="route"
                :aria-label="t('workspace.editChain')"
                @click="openChain(out, 'output')"
              />
              <q-btn
                flat
                dense
                round
                icon="account_tree"
                :aria-label="t('workspace.showFlow')"
                data-testid="show-output-flow"
                @click="openFlow(out, 'output')"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                @click="removeNode(out)"
              />
            </div>
          </q-item-section>
        </q-item>
        <q-item v-if="!outputs.length">
          <q-item-section class="text-grey-6">
            {{ t("workspace.noOutputs") }}
          </q-item-section>
        </q-item>
      </q-list>
    </template>

    <ListBulkDialog
      v-model="bulkChannels"
      :next-number="nextChannelNumber(channels)"
      :busy="bulkBusy"
      :devices="gear"
      @create="(items, opts) => bulkCreate('channels', items, opts)"
    />
    <ListBulkDialog
      v-model="bulkOutputs"
      outputs
      :busy="bulkBusy"
      @create="(items) => bulkCreate('outputs', items)"
    />
    <MixerDialog
      v-model="mixerOpen"
      :list="list"
      :channel-count="channels.length"
      @save="saveMixer"
    />
    <ChainFlowDialog
      v-model="flowOpen"
      :title="`${t('workspace.showFlow')}: ${chainNode?.name || ''}`"
      :steps="flowSteps"
      @edit="editFromFlow"
      @device="(id) => editDevice({ id })"
    />
    <ChainDialog
      v-model="chainOpen"
      :job-id="jobId"
      :title="chainTitle"
      :initial="chainInitial"
      :devices="gear"
      :branching="chainKind === 'output'"
      :bus-channels="
        chainKind === 'output'
          ? busChannelsFor(chainNode?.attributes?.mode)
          : []
      "
      @save="saveChain"
    />

    <!-- Two-step Wireless Workbench import: the parsed rows are shown with a per-row select so
         the user can pick which Stagewire channel each WWB row maps to before importing. -->
    <q-dialog v-model="wwbParseOpen" persistent>
      <q-card style="width: 720px; max-width: 95vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">{{ t("channels.wwbMapTitle") }}</div>
          <q-space />
          <q-btn
            icon="close"
            flat
            round
            dense
            @click="wwbParseOpen = false"
          />
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">
            {{ t("channels.wwbMapHint") }}
          </div>
          <q-banner
            v-if="wwbParseChannels.length === 0"
            dense
            class="bg-grey-2 text-grey-8 q-mb-sm"
          >
            {{ t("channels.wwbMapNoChannels") }}
          </q-banner>
          <q-banner
            v-else-if="wwbParseMatchedBy === 'name'"
            dense
            class="bg-green-1 text-green-9 q-mb-sm"
          >
            {{ t("channels.wwbMapMatchedByName") }}
          </q-banner>
          <q-banner
            v-else-if="wwbParseMatchedBy === 'order'"
            dense
            class="bg-blue-1 text-blue-9 q-mb-sm"
          >
            {{ t("channels.wwbMapMatchedByOrder") }}
          </q-banner>
          <q-banner v-else dense class="bg-grey-2 text-grey-8 q-mb-sm">
            {{ t("channels.wwbMapMatchedNone") }}
          </q-banner>
          <q-list separator>
            <q-item
              v-for="(row, idx) in wwbParseRows"
              :key="row.index"
              data-testid="wwb-map-row"
            >
              <q-item-section>
                <div class="text-subtitle2">
                  {{ row.name || `row ${row.index + 1}` }}
                </div>
                <div class="text-caption text-grey-6">
                  {{ wwbRowHint(row) }}<span
                    v-if="wwbRowGroup(row)"
                    >· {{ wwbRowGroup(row) }}</span
                  >
                </div>
              </q-item-section>
              <q-item-section
                side
                style="min-width: 240px; max-width: 340px"
              >
                <q-select
                  :model-value="wwbMapping[idx]?.channelId"
                  :options="wwbChannelOptions(idx)"
                  :label="t('channels.wwbMapStagewireChannel')"
                  outlined
                  dense
                  clearable
                  emit-value
                  map-options
                  :data-testid="`wwb-map-select-${row.index}`"
                  @update:model-value="(v) => (wwbMapping[idx].channelId = v)"
                />
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            flat
            :label="t('channels.wwbMapCancel')"
            color="primary"
            @click="wwbParseOpen = false"
          />
          <q-btn
            :loading="wwbImporting"
            :label="t('channels.wwbMapConfirm')"
            color="primary"
            unelevated
            data-testid="wwb-map-confirm"
            @click="confirmWwbImport"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup>
import { apiErrorText } from "@/utils/errors";
import { isRevisionConflict } from "@/utils/graph";
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { useGraphStore } from "@/stores/graph";
import ChainDialog from "@/components/ChainDialog.vue";
import StockwireProductPicker from "@/components/StockwireProductPicker.vue";
import { api } from "@/boot/api";
import ListBulkDialog from "@/components/ListBulkDialog.vue";
import MixerDialog from "@/components/MixerDialog.vue";
import ChainFlowDialog from "@/components/ChainFlowDialog.vue";
import ConnectorSelect from "@/components/ConnectorSelect.vue";
import {
  chainForm,
  busChannelsFor,
  chainDevices,
  chainSteps,
  flowTree,
  OUTPUT_MODES,
  channelsOf,
  isPlotElement,
  isOrphanedBySource,
  isVirtual,
  mixerSlotsToAdd,
  nextChannelNumber,
  outputsOf,
  stereoPairPlan,
  stereoView,
} from "@/utils/workspace";

const props = defineProps({ jobId: { type: String, required: true } });
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const listId = ref(null);
const chainOpen = ref(false);
const chainNode = ref(null);
const chainKind = ref("channel");
const chainInitial = ref([]);
const wwbFileInput = ref(null);
const wwbImporting = ref(false);

const list = computed(
  () => graph.channelLists.find((l) => l.id === listId.value) || null,
);
const channels = computed(() => channelsOf(graph.devices, listId.value));
const outputs = computed(() => outputsOf(graph.devices, listId.value));
const gear = computed(() =>
  graph.devices.filter((d) => !isVirtual(d) && !isPlotElement(d)),
);
const chainTitle = computed(
  () => `${t("workspace.editChain")}: ${chainNode.value?.name || ""}`,
);
const inputTypes = ["microphone", "di", "wireless", "fxReturn"].map((v) => ({
  value: v,
  label: t(`channels.type.${v}`),
}));

const columns = computed(() => [
  { name: "number", label: "#", field: () => "", align: "left" },
  { name: "name", label: t("workspace.colName"), field: "name", align: "left" },
  {
    name: "input_type",
    label: t("workspace.colKind"),
    field: () => "",
    align: "left",
  },
  {
    name: "device",
    label: t("workspace.colDevice"),
    field: () => "",
    align: "left",
  },
  {
    name: "stand_type",
    label: t("workspace.colStand"),
    field: () => "",
    align: "left",
  },
  {
    name: "connector",
    label: t("workspace.stepConnector"),
    field: () => "",
    align: "left",
  },
  { name: "phantom_power", label: "48V", field: () => "", align: "center" },
  { name: "stereo", label: "ST", field: () => "", align: "center" },
  {
    name: "notes",
    label: t("workspace.colNotes"),
    field: "notes",
    align: "left",
  },
  {
    name: "chain",
    label: t("workspace.chain"),
    field: () => "",
    align: "left",
  },
  { name: "actions", label: "", field: () => "", align: "right" },
]);

watch(
  () => graph.channelLists.map((l) => l.id).join(),
  () => {
    if (!graph.channelLists.some((l) => l.id === listId.value)) {
      listId.value = graph.channelLists[0]?.id || null;
    }
  },
  { immediate: true },
);

// One line saying what a channel has set, for the phone card: kind, source, stand, connector, 48V
// and stereo, so the card shows the state without opening "Details".
const channelSummary = (ch) => {
  const a = ch.attributes;
  const side = stereoView(ch, channels.value);
  return [
    a.input_type ? t(`channels.type.${a.input_type}`) : "",
    sourceOf(ch)?.name,
    a.stand_type,
    a.connector,
    a.phantom_power ? "48V" : "",
    side.linked ? `${t("channels.fieldStereo")} ${side.isL ? "L" : "R"}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
};
const chain = (node) =>
  chainSteps(node, graph.edges, graph.devices).join(" → ");
const failed = (err) =>
  $q.notify({ type: "negative", message: apiErrorText(err) });

async function save(node, changes) {
  try {
    await graph.updateDevice(props.jobId, node.id, changes);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const saveAttr = (node, key, value) =>
  save(node, { attributes: { [key]: value } });

// Import a Shure Wireless Workbench .shw show file onto the current list's wireless
// channels. Two steps: first the file is parsed and the backend suggests a channel
// per row, then the user confirms (and can change) the mapping in a dialog. The
// confirmed mapping (or an empty one) is sent to the import endpoint, which also
// stores the file so it can be re-exported as a round-trip later.
const wwbParsing = ref(false);
const wwbParseOpen = ref(false);
const wwbParseRows = ref([]);
const wwbParseChannels = ref([]);
const wwbParseMatchedBy = ref("none");
const wwbParseFile = ref(null);
const wwbMapping = ref([]);

async function onWwbFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  wwbParsing.value = true;
  try {
    const body = new FormData();
    body.append("file", file);
    const { data } = await api.post(
      `/jobs/${props.jobId}/graph/lists/${listId.value}/wireless-workbench/parse`,
      body,
    );
    wwbParseRows.value = data.rows;
    wwbParseChannels.value = data.channels;
    wwbParseMatchedBy.value = data.matched_by || "none";
    wwbParseFile.value = file;
    // Start each row on the backend's suggested channel; the user can change it.
    wwbMapping.value = data.rows.map((r) => ({
      row: r.index,
      channelId: r.suggested_channel_id || null,
    }));
    wwbParseOpen.value = true;
  } catch (err) {
    $q.notify({
      type: "negative",
      message: t("channels.wwbParseFailed"),
    });
  } finally {
    wwbParsing.value = false;
    event.target.value = "";
  }
}

// The Stagewire channel options for a row's select, hiding any channel already picked by
// another row so a single channel is never mapped from two Wireless Workbench rows.
function wwbChannelOptions(rowIndex) {
  const taken = new Set(
    wwbMapping.value
      .filter((m, i) => i !== rowIndex && m.channelId)
      .map((m) => m.channelId),
  );
  return wwbParseChannels.value.map((c) => ({
    value: c.id,
    label: `#${c.channel_number} ${c.source_label || c.wireless_pack || t("channels.channel")}`,
    disable: taken.has(c.id),
  }));
}

const wwbRowHint = (row) =>
  row.wireless_frequency_mhz != null
    ? `${t("channels.wwbMapFrequency")} ${row.wireless_frequency_mhz} MHz`
    : "";
const wwbRowGroup = (row) =>
  row.wireless_group && row.wireless_channel
    ? `${row.wireless_group}/${row.wireless_channel}`
    : "";

async function confirmWwbImport() {
  if (!wwbParseFile.value) return;
  wwbImporting.value = true;
  try {
    const mapping = wwbMapping.value
      .filter((m) => m.channelId)
      .map((m) => ({ row: m.row, channel_id: m.channelId }));
    const body = new FormData();
    body.append("file", wwbParseFile.value);
    body.append("mapping", JSON.stringify(mapping));
    const { data } = await api.post(
      `/jobs/${props.jobId}/graph/lists/${listId.value}/wireless-workbench/import`,
      body,
    );
    const parts = [
      t("channels.wwbImportedUpdated", {
        count: data.updated,
        total: data.rows,
      }),
    ];
    if (data.unmatched?.length) {
      parts.push(
        t("channels.wwbImportUnmatched", { count: data.unmatched.length }),
      );
    }
    $q.notify({ type: "positive", message: parts.join(" · ") });
    wwbParseOpen.value = false;
  } catch (err) {
    $q.notify({ type: "negative", message: apiErrorText(err) });
  } finally {
    wwbImporting.value = false;
    wwbParseFile.value = null;
  }
}
// Ticking "stereo" pairs the channel with its odd/even neighbour (see stereoPairPlan); unticking
// releases both. The partner is made first so the main row never points at a channel that is not
// there yet.
async function setStereo(node, on) {
  const plan = stereoPairPlan(node, channels.value, on);
  try {
    if (plan.partnerCreate) {
      await graph.createChannels(props.jobId, listId.value, [
        plan.partnerCreate,
      ]);
    } else if (plan.partner && plan.partnerChanges) {
      await graph.updateDevice(
        props.jobId,
        plan.partner.id,
        plan.partnerChanges,
      );
    }
    await graph.updateDevice(props.jobId, node.id, plan.main);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const setNumber = (node, value) =>
  save(node, { position: value, attributes: { channel_number: value } });

async function addList() {
  try {
    const created = await graph.createList(props.jobId, {
      name: t("workspace.newList"),
    });
    listId.value = created.id;
  } catch (err) {
    failed(err);
  }
}

async function addChannels(count) {
  try {
    await graph.createChannels(
      props.jobId,
      list.value.id,
      Array.from({ length: count }, () => ({})),
    );
  } catch (err) {
    failed(err);
  }
}

// The gear in a chain is edited from the signal flow or the chain dialog (an edit button on each
// device); the mixer card lists the mixers (consoles) the list's channels are patched into.
function editDevice(device) {
  flowOpen.value = false;
  graph.selectedDeviceId = device.id;
}
const listMixers = computed(() => {
  const seen = new Map();
  for (const channel of channels.value) {
    for (const device of chainDevices(channel, graph.edges, graph.devices)) {
      if (device.kind === "mixer") seen.set(device.id, device);
    }
  }
  return [...seen.values()];
});

const mixerOpen = ref(false);
// The mixer is stored on the list, which the server mirrors to the legacy list the Stockwire sync
// reads. The list is then padded with empty inputs and outputs up to the mixer's size.
async function saveMixer({ product, inputs, buses }) {
  const wantInputs = Number(inputs) || 0;
  const wantBuses = Number(buses) || 0;
  try {
    await graph.updateDevice(props.jobId, list.value.id, {
      attributes: {
        mixer_product_id: product?.id || null,
        mixer_product_name: product?.name || null,
        mixer_inputs: inputs ?? null,
        mixer_buses: buses ?? null,
      },
    });
    const add = mixerSlotsToAdd(
      channels.value,
      outputs.value,
      wantInputs,
      wantBuses,
    );
    if (add.channels.length)
      await graph.createChannels(props.jobId, list.value.id, add.channels);
    if (add.outputs.length)
      await graph.createOutputs(props.jobId, list.value.id, add.outputs);
    if (add.channels.length || add.outputs.length) {
      $q.notify({
        type: "positive",
        message: t("stockwire.mixerFilled", {
          inputs: add.channels.length,
          buses: add.outputs.length,
        }),
      });
    }
    mixerOpen.value = false;
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}

const bulkChannels = ref(false);
const bulkOutputs = ref(false);
const bulkBusy = ref(false);

async function bulkCreate(kind, items, opts = {}) {
  bulkBusy.value = true;
  try {
    if (kind === "channels") {
      const created = await graph.createChannels(
        props.jobId,
        list.value.id,
        items,
      );
      if (opts.deviceId) {
        await graph.setChannelChains(
          props.jobId,
          created.map((c) => c.id),
          [{ device_id: opts.deviceId }],
        );
      }
    } else await graph.createOutputs(props.jobId, list.value.id, items);
    bulkChannels.value = false;
    bulkOutputs.value = false;
  } catch (err) {
    failed(err);
  } finally {
    bulkBusy.value = false;
  }
}

// A stand is a Stockwire product (or a name typed in for something not in the catalog). The
// product is stored on the channel; stand_type keeps the name for lists and exports. "Sync to
// Stockwire" then adds the stands, mixers and gear to the linked Stockwire job.
const standOf = (node) =>
  node.attributes.stand_product_name || node.attributes.stand_type
    ? {
        id: node.attributes.stand_product_id || null,
        name: node.attributes.stand_product_name || node.attributes.stand_type,
      }
    : null;
const setStand = (node, product) =>
  save(node, {
    attributes: {
      stand_product_id: product?.id ? String(product.id) : null,
      stand_product_name: product?.name || null,
      stand_type: product?.name || "",
    },
  });

// The source of a channel (the device or microphone it comes from) is something already in the
// job, one of the company's own Stockwire products, or a name typed in.
const gearItems = computed(() =>
  graph.devices
    .filter((d) => !isVirtual(d) && !isPlotElement(d))
    .map((d) => ({
      id: d.id,
      name: d.name,
      stockwire_product_id: d.stockwire_product_id,
    })),
);
// The source of a channel (the microphone, DI or other gear it comes from) is a real device in the
// job: picking a job device links it, picking one of the company's own Stockwire products makes a
// device from it (connectors and power from the product) and links that, and typed text is just a
// label. The link is `attributes.source_device_id`; `attributes.device` keeps the name for lists
// and exports. A linked device carries the Stockwire product (it counts once in the sync), so the
// channel's own product is cleared then; an unlinked own product stays on the channel as before.
const sourceDevice = (node) =>
  graph.devices.find((d) => d.id === node.attributes.source_device_id) || null;
const sourceOf = (node) => {
  const linked = sourceDevice(node);
  const name =
    linked?.name || node.attributes.device || node.stockwire_product_name;
  return name
    ? {
        id: linked ? null : node.stockwire_product_id || null,
        name,
        job_device_id: linked?.id || null,
      }
    : null;
};
async function setSource(node, pick) {
  const previous = sourceDevice(node);
  let nextId = null;
  try {
    if (!pick) {
      await graph.updateDevice(props.jobId, node.id, {
        attributes: { device: "", source_device_id: null },
        stockwire_product_id: null,
        stockwire_product_name: null,
      });
    } else {
      let device = pick.job_device_id
        ? graph.devices.find((d) => d.id === pick.job_device_id)
        : null;
      if (!device && pick.id)
        device = await graph.createDeviceFromProduct(props.jobId, pick);
      nextId = device?.id || null;
      await graph.updateDevice(props.jobId, node.id, {
        attributes: {
          device: device?.name || pick.name,
          source_device_id: device?.id || null,
        },
        stockwire_product_id: !device && pick.id ? String(pick.id) : null,
        stockwire_product_name: !device && pick.id ? pick.name : null,
      });
    }
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
    return;
  }
  await removeOrphanedSource(node, previous, nextId);
}

// The channel no longer points at its old source device, so that device goes too unless something
// else uses it (see isOrphanedBySource). The channel is updated first, so the link never dangles;
// a delete the server refuses (a patched device is a 409) just leaves the device in place.
async function removeOrphanedSource(node, previous, nextId) {
  if (!previous || previous.id === nextId) return;
  if (!isOrphanedBySource(previous.id, node.id, graph.devices, graph.edges))
    return;
  try {
    await graph.deleteDevice(props.jobId, previous.id);
    $q.notify({
      type: "info",
      message: t("workspace.sourceDeviceRemoved", { name: previous.name }),
    });
  } catch (err) {
    if (err.response?.status !== 409 && !isRevisionConflict(err)) failed(err);
  }
}

const syncing = ref(false);
async function syncStockwire() {
  syncing.value = true;
  try {
    const { data } = await api.post(`/jobs/${props.jobId}/sync-stockwire`);
    $q.notify({
      type: data.errors?.length ? "warning" : "positive",
      message: data.errors?.length
        ? `${t("workspace.stockwireSynced", { added: data.added.length, updated: data.updated.length, removed: data.removed.length })}. ${t("workspace.syncErrors", { n: data.errors.length })}: ${data.errors.slice(0, 3).join("; ")}`
        : t("workspace.stockwireSynced", {
            added: data.added.length,
            updated: data.updated.length,
            removed: data.removed.length,
          }),
    });
  } catch (err) {
    failed(err);
  } finally {
    syncing.value = false;
  }
}

async function addOutput() {
  try {
    await graph.createOutput(props.jobId, list.value.id, {
      name: `${t("workspace.output")} ${outputs.value.length + 1}`,
    });
  } catch (err) {
    failed(err);
  }
}

const modeOptions = computed(() =>
  OUTPUT_MODES.map((m) => ({
    value: m.value,
    label: t(`workspace.busMode.${m.value.replace(/[._]/g, "")}`),
  })),
);

const flowOpen = ref(false);
const flowSteps = ref([]);

// The chain as a diagram; its branches follow the parent of each step (outputs branch).
function openFlow(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  flowSteps.value = flowTree(
    node.name,
    chainForm(node, graph.edges, graph.devices),
    graph.devices,
  );
  flowOpen.value = true;
}
function editFromFlow() {
  flowOpen.value = false;
  openChain(chainNode.value, chainKind.value);
}

function openChain(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  chainInitial.value = chainForm(node, graph.edges, graph.devices);
  chainOpen.value = true;
}

async function saveChain(steps) {
  try {
    await graph.replaceChain(
      props.jobId,
      chainKind.value,
      chainNode.value.id,
      steps,
    );
    chainOpen.value = false;
  } catch (err) {
    failed(err);
  }
}

function removeNode(node) {
  $q.dialog({
    title: t("workspace.remove"),
    message: node.name,
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await graph.deleteDevice(props.jobId, node.id);
    } catch (err) {
      if (!isRevisionConflict(err)) failed(err);
    }
  });
}

const removeList = () => removeNode(list.value);
</script>

<style scoped>
/* The chain button shows the whole chain and sits next to the flow button, so the cell must be
   wide enough for both or the next column would cover the flow button. */
.chain-cell {
  min-width: 240px;
  white-space: nowrap;
}
</style>
