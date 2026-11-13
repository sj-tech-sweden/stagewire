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

    <div
      v-if="!list"
      class="text-grey-6"
    >
      {{ t("workspace.noLists") }}
    </div>

    <template v-else>
      <q-card
        flat
        bordered
        class="q-pa-sm q-mb-sm row items-center q-gutter-sm"
        data-testid="list-mixer"
      >
        <q-icon
          v-if="stockwire.isEnabled"
          name="tune"
          color="primary"
          size="sm"
        />
        <div
          v-if="stockwire.isEnabled"
          class="col"
        >
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
              {{ t("stockwire.inputsShort") }}</span>
            <span
              v-if="list.attributes.mixer_buses != null"
              class="text-grey-7"
            >
              · {{ list.attributes.mixer_buses }}
              {{ t("stockwire.busesShort") }}</span>
          </div>
          <div
            v-else
            class="text-grey-7"
          >
            {{ t("stockwire.mixerNotSet") }}
          </div>
        </div>
        <div
          v-if="stockwire.isEnabled && listMixers.length"
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
          v-if="stockwire.isEnabled"
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
        <q-btn
          v-if="jobId"
          outline
          no-caps
          color="primary"
          icon="settings_input_component"
          :label="t('console.openPanel')"
          :aria-pressed="consoleOpen"
          data-testid="open-console"
          @click="toggleConsole"
        />
        <input
          ref="wwbFileInput"
          type="file"
          accept=".shw,application/xml"
          class="hidden"
          data-testid="wwb-file"
          @change="onWwbFile"
        >
      </q-card>

      <ConsolePanel
        v-if="consoleOpen && jobId && !venueId"
        ref="consolePanel"
        :job-id="jobId"
        :list-id="list.id"
        :refresh-key="consoleSignature"
        @changed="graph.fetchGraph(contextId, contextKind)"
      />
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
          v-if="contextKind === 'job' && stockwire.isEnabled"
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
           opens kind, source, stand, mixer input, 48V, stereo, wireless and notes. -->
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
              <q-select
                :model-value="ch.attributes.mixer_input || null"
                dense
                outlined
                emit-value
                map-options
                clearable
                :options="mixerInputChoices(ch, graph.devices, graph.edges)"
                :label="t('workspace.colMixerInput')"
                :hint="t('workspace.colMixerInputHint')"
                data-testid="channel-mixer-input"
                @update:model-value="(v) => saveAttr(ch, 'mixer_input', v || null)"
              />
              <div class="row items-center">
                <q-checkbox
                  :model-value="!!ch.attributes.phantom_power"
                  :disable="ch.attributes.stereo_link_role === 'secondary'"
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
      <AdaptiveTable
        v-else
        table-id="channels"
        test-prefix="channel"
        :columns="columns"
        flat
        dense
        bordered
        virtual-scroll
        :virtual-scroll-item-size="80"
        :rows="channels"
        row-key="id"
        :rows-per-page-options="[0]"
        hide-bottom
        class="sticky-header-table channel-table"
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
            <div class="row items-center q-gutter-x-xs no-wrap">
              <q-select
                :model-value="slot.row.attributes.input_type"
                dense
                borderless
                clearable
                emit-value
                map-options
                :options="inputTypes"
                class="col"
                style="min-width: 0"
                @update:model-value="(v) => saveAttr(slot.row, 'input_type', v)"
              />
              <q-input
                v-if="slot.row.attributes.input_type === 'wireless'"
                :model-value="slot.row.attributes.wireless_pack"
                dense
                borderless
                class="col"
                style="min-width: 0"
                :placeholder="t('channels.fieldWirelessPack')"
                data-testid="wireless-pack"
                @change="(v) => saveAttr(slot.row, 'wireless_pack', v)"
              />
            </div>
            <div
              v-if="slot.row.attributes.input_type === 'wireless'"
              class="row items-start q-gutter-x-xs q-mt-xs"
              style="flex-wrap: wrap"
            >
              <q-input
                :model-value="slot.row.attributes.wireless_frequency_mhz"
                dense
                borderless
                type="number"
                step="0.001"
                class="col"
                style="min-width: 90px"
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
                style="width: 56px; flex: 0 0 56px"
                :placeholder="t('channels.fieldWirelessGroup')"
                data-testid="wireless-group"
                @change="(v) => saveAttr(slot.row, 'wireless_group', v || null)"
              />
              <q-input
                :model-value="slot.row.attributes.wireless_channel"
                dense
                borderless
                style="width: 56px; flex: 0 0 56px"
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
          <q-td :props="slot">
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
          <q-td :props="slot">
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
              <q-tooltip>
                {{
                  t("channels.stereoLinkedTo", {
                    ch: slot.row.attributes.stereo_channel,
                  })
                }}
              </q-tooltip>
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
              :disable="
                flag === 'phantom_power' &&
                  slot.row.attributes.stereo_link_role === 'secondary'
              "
              @update:model-value="(v) => saveAttr(slot.row, flag, v)"
            />
          </q-td>
        </template>
        <template #body-cell-instrument_group="slot">
          <q-td :props="slot">
            <q-select
              :model-value="slot.row.attributes.instrument_group || 'other'"
              :options="groupOptions"
              emit-value
              map-options
              dense
              borderless
              :disable="isSecondaryLeg(slot.row)"
              data-testid="channel-group"
              @update:model-value="(v) => saveAttr(slot.row, 'instrument_group', v)"
            >
              <q-tooltip v-if="isSecondaryLeg(slot.row)">
                {{ t("workspace.colourFollowsPrimary") }}
              </q-tooltip>
            </q-select>
          </q-td>
        </template>
        <template #body-cell-color_code="slot">
          <q-td :props="slot">
            <q-btn
              dense
              flat
              no-caps
              class="channel-swatch"
              :class="{ 'channel-swatch--unset': !slot.row.attributes.color_code }"
              :style="swatchStyle(slot.row.attributes.color_code)"
              :disable="isSecondaryLeg(slot.row)"
              :aria-label="t('workspace.colourPick')"
              data-testid="channel-colour"
            >
              <q-tooltip>
                {{
                  isSecondaryLeg(slot.row)
                    ? t("workspace.colourFollowsPrimary")
                    : slot.row.attributes.color_code || t("workspace.colourUnset")
                }}
              </q-tooltip>
              <q-popup-proxy
                v-if="!isSecondaryLeg(slot.row)"
                @hide="commitColour(slot.row)"
              >
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
                      :data-testid="`channel-colour-preset-${preset.slice(1)}`"
                      @click="pickPreset(slot.row, preset)"
                    />
                  </div>
                  <q-color
                    :model-value="colourDraft(slot.row)"
                    format-model="hex"
                    no-header
                    no-footer
                    default-view="spectrum"
                    flat
                    @update:model-value="(v) => (pendingColour = { id: slot.row.id, value: v })"
                    @change="(v) => setColour(slot.row, v)"
                  />
                  <q-btn
                    v-close-popup
                    flat
                    dense
                    no-caps
                    icon="format_color_reset"
                    :label="t('workspace.colourClear')"
                    :disable="!slot.row.attributes.color_code"
                    data-testid="channel-colour-clear"
                    @click="setColour(slot.row, null)"
                  />
                </q-card>
              </q-popup-proxy>
            </q-btn>
          </q-td>
        </template>
        <template #body-cell-performer_name="slot">
          <q-td :props="slot">
            <q-input
              :model-value="slot.row.attributes.performer_name || ''"
              dense
              borderless
              data-testid="channel-performer"
              @change="(v) => saveAttr(slot.row, 'performer_name', String(v || '').trim() || null)"
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
          <q-td
            :props="slot"
            class="chain-cell"
          >
            <q-btn
              flat
              dense
              no-caps
              icon="route"
              :label="chain(slot.row) || t('workspace.chainEmpty')"
              :title="chain(slot.row)"
              class="chain-main"
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
              icon="open_in_new"
              :aria-label="t('workspace.openDevice')"
              data-testid="open-channel-device"
              @click="editDevice(slot.row)"
            />
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
      </AdaptiveTable>

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
      <!-- The same bus-pool budget the console panel shows: these rows and the panel's Buses tab
           edit the same output records, so the budget is visible wherever they are changed. The
           rows save through the graph, which does not block, so an overflow is only a warning. -->
      <div
        v-if="consoleSummary?.budget?.enabled"
        class="q-mb-sm"
        data-testid="outputs-budget"
      >
        <div class="row items-center q-mb-xs">
          <div class="text-caption col">
            {{ t("console.budget") }}
          </div>
          <div
            class="text-caption"
            data-testid="outputs-budget-text"
          >
            {{ consoleSummary.budget.used_slots }} / {{ consoleSummary.budget.total_slots }}
            {{ t("console.slots") }}
          </div>
        </div>
        <q-linear-progress
          :value="
            consoleSummary.budget.total_slots
              ? Math.min(consoleSummary.budget.used_slots / consoleSummary.budget.total_slots, 1)
              : 0
          "
          size="10px"
          rounded
          :color="consoleSummary.budget.ok ? 'positive' : 'negative'"
        />
        <q-banner
          v-if="!consoleSummary.budget.ok"
          dense
          rounded
          class="bg-warning text-black q-mt-xs"
          data-testid="outputs-budget-warning"
        >
          <div
            v-for="v in consoleSummary.budget.violations"
            :key="v"
          >
            {{ v }}
          </div>
        </q-banner>
      </div>
      <q-list
        bordered
        separator
      >
        <q-item
          v-for="out in outputs"
          :key="out.id"
          data-testid="output-row"
        >
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
          <q-item-section
            side
            style="min-width: 150px"
          >
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
          <q-item-section
            v-if="consoleSummary && !consoleSummary.simple"
            side
            style="min-width: 130px"
          >
            <q-select
              :model-value="out.attributes.role || 'aux'"
              :options="busRoles"
              dense
              outlined
              :label="t('console.role')"
              data-testid="output-role"
              @update:model-value="(v) => saveAttr(out, 'role', v)"
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
      :job-id="venueId ? '' : jobId"
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
      :venue-id="venueId"
      :title="chainTitle"
      :initial="chainInitial"
      :lock="chainKind === 'channel' ? softPatchInfo(liveChainNode, graph.devices) : null"
      :direct="chainNode ? directLines(chainNode) : []"
      :devices="gear"
      :branching="chainKind === 'output'"
      :bus-channels="
        chainKind === 'output'
          ? busChannelsFor(chainNode?.attributes?.mode)
          : []
      "
      @save="saveChain"
      @open-soft-patch="openSoftPatch"
    />

    <!-- Two-step Wireless Workbench import: the parsed rows are shown with a per-row select so
         the user can pick which Stagewire channel each WWB row maps to before importing. -->
    <q-dialog
      v-model="wwbParseOpen"
      persistent
    >
      <q-card style="width: 720px; max-width: 95vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">
            {{ t("channels.wwbMapTitle") }}
          </div>
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
          <q-banner
            v-else
            dense
            class="bg-grey-2 text-grey-8 q-mb-sm"
          >
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
                  >· {{ wwbRowGroup(row) }}</span>
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
import {
  consoleSignatureOf,
  deviceCreateBody,
  deviceForm,
  fillFormFromSpecs,
  mixerGraphPorts,
  mixerImportPlan,
} from "@/utils/workspace";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { useGraphStore } from "@/stores/graph";
import { useStockwireStore } from "@/stores/stockwire";
import ChainDialog from "@/components/ChainDialog.vue";
import StockwireProductPicker from "@/components/StockwireProductPicker.vue";
import { api } from "@/boot/api";
import { CHANNEL_COLUMNS } from "@/utils/columnLayout";
import { INSTRUMENT_GROUP_KEYS } from "@/utils/instrumentGroups";
import { PRESET_COLOURS, colourToHex, normalizeHex, readableTextColour } from "@/utils/colour";
import AdaptiveTable from "@/components/AdaptiveTable.vue";
import ListBulkDialog from "@/components/ListBulkDialog.vue";
import MixerDialog from "@/components/MixerDialog.vue";
import ConsolePanel from "@/components/ConsolePanel.vue";
import ChainFlowDialog from "@/components/ChainFlowDialog.vue";
import {
  chainForm,
  chainStepsWithLock,
  softPatchInfo,
  busChannelsFor,
  chainDevices,
  directConnections,
  patchSummary,
  flowTree,
  channelFlowTree,
  OUTPUT_MODES,
  channelsOf,
  isPlotElement,
  isOrphanedBySource,
  isVirtual,
  mixerInputChoices,
  nextChannelNumber,
  outputsOf,
  stereoPairPlan,
  stereoView,
} from "@/utils/workspace";

const props = defineProps({
  // A job owns its own graph; a venue's Standard Base Rig reuses the same editor. When `venueId`
  // is set the editor talks to the venue graph routes instead of the job ones (see graph store
  // scope). `jobId` stays as the fallback so job callers are unaffected.
  jobId: { type: String, default: '' },
  venueId: { type: String, default: '' },
});
// The id the graph store should scope to: a venue id when present, otherwise the job id.
const contextId = computed(() => props.venueId || props.jobId);
const contextKind = computed(() => (props.venueId ? 'venue' : 'job'));
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const stockwire = useStockwireStore();
const listId = ref(null);
const chainOpen = ref(false);
const chainNode = ref(null);
const chainKind = ref("channel");
const chainInitial = ref([]);
const wwbFileInput = ref(null);
const wwbImporting = ref(false);
const consoleOpen = ref(false);
const consolePanel = ref(null);
// "Change in Soft patch" from the chain editor: close it and show the console panel's soft patch tab.
async function openSoftPatch() {
  chainOpen.value = false;
  consoleOpen.value = true;
  await nextTick();
  consolePanel.value?.openTab("patch");
}
// Closing the console panel first lets a pending (debounced) edit land: nothing needs saving.
async function toggleConsole() {
  if (consoleOpen.value && consolePanel.value) await consolePanel.value.settle();
  consoleOpen.value = !consoleOpen.value;
}

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

// --- table columns ---------------------------------------------------------------------------------
// The layout (computed widths, hidden columns, dragged widths, floating header) is AdaptiveTable's;
// this only says what the columns are. The descriptors with their widths live in utils/columnLayout.js.
const columnLabels = computed(() => ({
  number: "#",
  name: t("workspace.colName"),
  input_type: t("workspace.colKind"),
  device: t("workspace.colDevice"),
  stand_type: t("workspace.colStand"),
  phantom_power: "48V",
  stereo: "ST",
  instrument_group: t("workspace.colInstrumentGroup"),
  color_code: t("workspace.colColour"),
  performer_name: t("workspace.colPerformer"),
  notes: t("workspace.colNotes"),
  chain: t("workspace.chain"),
  actions: "",
}));
const ALIGN = { phantom_power: "center", stereo: "center", color_code: "center", actions: "right" };
const columns = computed(() =>
  CHANNEL_COLUMNS.map((c) => ({
    ...c,
    label: columnLabels.value[c.name],
    field: c.name === "name" || c.name === "notes" ? c.name : () => "",
    align: ALIGN[c.name] || "left",
  })),
);

watch(
  () => graph.channelLists.map((l) => l.id).join(),
  () => {
    if (!graph.channelLists.some((l) => l.id === listId.value)) {
      listId.value = graph.channelLists[0]?.id || null;
    }
  },
  { immediate: true },
);

// Keep the graph store scoped to the right context. The page that mounts us usually fetches first,
// but we re-fetch only if the scope changed (job <-> venue) so we never clobber another view's data.
function ensureGraph() {
  if (graph.scopeId !== contextId.value || graph.scopeKind !== contextKind.value) {
    graph.fetchGraph(contextId.value, contextKind.value);
  }
}
watch([contextId, contextKind], ensureGraph, { immediate: true });

// One line saying what a channel has set, for the phone card: kind, source, stand, 48V and stereo,
// so the card shows the state without opening "Details". The connector is the device's, not the
// channel's, so it is not repeated here.
const channelSummary = (ch) => {
  const a = ch.attributes;
  const side = stereoView(ch, channels.value);
  return [
    a.input_type ? t(`channels.type.${a.input_type}`) : "",
    sourceOf(ch)?.name,
    a.stand_type,
    a.phantom_power ? "48V" : "",
    side.linked ? `${t("channels.fieldStereo")} ${side.isL ? "L" : "R"}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
};
// The Patch column: the patch chain plus any cables made in the inspector (see patchSummary).
const chain = (node) => patchSummary(node, graph.edges, graph.devices);
// Cables to and from the node that are not in its patch chain, shown read-only in the chain dialog.
const directLines = (node) =>
  directConnections(node, graph.edges, graph.devices).map((d) => d.text);
const failed = (err) =>
  $q.notify({ type: "negative", message: apiErrorText(err) });

// What a stereo link binds (console.py SHARED_FIELDS): a change to one of these on the primary is
// copied onto the secondary by the server's graph sync.
const LINK_SHARED = ["phantom_power", "color_code", "instrument_group", "source_label"];
async function save(node, changes) {
  try {
    await graph.updateDevice(contextId.value, node.id, changes);
    // The secondary is changed by the server as a side effect and that change is not pushed to
    // this client, so re-read the graph to show it (48V, name, colour and group of the other leg).
    const touched = [...Object.keys(changes.attributes || {}), ...("name" in changes ? ["source_label"] : [])];
    if (node.attributes?.stereo_link_role === "primary" && touched.some((k) => LINK_SHARED.includes(k)))
      await graph.fetchGraph(contextId.value, contextKind.value);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
const saveAttr = (node, key, value) =>
  save(node, { attributes: { [key]: value } });

// --- optional columns: instrument group, colour, performer ----------------------------------------
const groupOptions = computed(() =>
  INSTRUMENT_GROUP_KEYS.map((v) => ({
    value: v,
    label: t(`channels.instrumentGroups.${v}`),
  })),
);
// The second leg of a stereo pair takes its name, colour and group from the first (the server
// mirrors them), so those editors are read-only there.
const isSecondaryLeg = (row) => row.attributes?.stereo_link_role === "secondary";
// A stored colour may be an old plain name ("red"): the swatch shows it best-effort, an unknown name
// gets a neutral swatch (the tooltip shows the text), and nothing is rewritten until the user picks.
function swatchStyle(value) {
  if (!value) return {};
  const hex = colourToHex(value);
  return hex
    ? { background: hex, color: readableTextColour(hex) }
    : { background: "#9e9e9e", color: "#000" };
}
// The picker's value follows the drag live, but is only saved once the user lets go (`change`) or
// closes the popup, so dragging does not write on every tick.
const pendingColour = ref(null);
const colourDraft = (row) =>
  (pendingColour.value?.id === row.id && normalizeHex(pendingColour.value.value)) ||
  colourToHex(row.attributes.color_code) ||
  "#ffffff";
function setColour(row, value) {
  pendingColour.value = null;
  const hex = value == null ? null : normalizeHex(value);
  if (value != null && !hex) return;
  if ((row.attributes.color_code || null) === hex) return;
  return saveAttr(row, "color_code", hex);
}
const pickPreset = (row, hex) => setColour(row, hex);
// closing the popup saves a drag that never got its release event (e.g. dismissed mid-drag)
function commitColour(row) {
  if (pendingColour.value?.id === row.id) setColour(row, pendingColour.value.value);
}

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
      `${graph.graphBase}/lists/${listId.value}/wireless-workbench/parse`,
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
      `${graph.graphBase}/lists/${listId.value}/wireless-workbench/import`,
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
  if (!props.venueId && props.jobId) return setStereoLink(node, on);
  const plan = stereoPairPlan(node, channels.value, on);
  try {
    if (plan.partnerCreate) {
      await graph.createChannels(contextId.value, listId.value, [
        plan.partnerCreate,
      ]);
    } else if (plan.partner && plan.partnerChanges) {
      await graph.updateDevice(
        contextId.value,
        plan.partner.id,
        plan.partnerChanges,
      );
    }
    await graph.updateDevice(contextId.value, node.id, plan.main);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}
// Job lists: the Stereo toggle and the digital console's stereo link are one concept, so the toggle
// goes through the validating link/unlink endpoints (pairing rules, DSP limits, 409 messages).
// The odd/even partner is created first when missing. A link binds the strip's name, colour, group
// and +48V: the server makes the secondary follow the primary (its name keeps its side, "Ch 1 L" ->
// "Ch 1 R"). Patch, socket, input type and mic stay per leg, so nothing of those is copied.
async function setStereoLink(node, on) {
  const base = `/jobs/${props.jobId}/channel-lists/${listId.value}/console`;
  try {
    if (!on) {
      await api.post(`${base}/unlink`, { primary_channel_id: node.id });
    } else {
      const plan = stereoPairPlan(node, channels.value, true);
      let partner = plan.partner;
      if (plan.partnerCreate) {
        const [created] = await graph.createChannels(contextId.value, listId.value, [
          { channel_number: plan.partnerNumber, source_label: plan.partnerCreate.source_label },
        ]);
        partner = created;
      }
      const lowerIsNode = Number(node.attributes.channel_number) < plan.partnerNumber;
      // the primary (lower number) carries the " L"; the server derives the secondary's " R"
      const primary = lowerIsNode ? node : partner;
      const primaryName = lowerIsNode
        ? plan.main.name
        : plan.partnerChanges?.name || plan.partnerCreate?.source_label;
      if (primaryName && primary?.id) {
        await graph.updateDevice(contextId.value, primary.id, { name: primaryName });
      }
      await api.post(`${base}/link`, {
        primary_channel_id: lowerIsNode ? node.id : partner.id,
        secondary_channel_id: lowerIsNode ? partner.id : node.id,
      });
    }
  } catch (err) {
    $q.notify({ type: "negative", message: apiErrorText(err, t("console.failed")) });
  }
  await graph.fetchGraph(graph.scopeId, graph.scopeKind);
}
const setNumber = (node, value) =>
  save(node, { position: value, attributes: { channel_number: value } });

async function addList() {
  try {
    const created = await graph.createList(contextId.value, {
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
      contextId.value,
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
  // The list's own auto-minted mixer device (linked by sound_list_id) is shown here even before any
  // channel is actually patched into it.
  const own = graph.devices.find(
    (d) => (d.kind === "mixer" || d.device_type === "mixer") && d.sound_list_id === list.value.id,
  );
  if (own) seen.set(own.id, own);
  for (const channel of channels.value) {
    for (const device of chainDevices(channel, graph.edges, graph.devices)) {
      if (device.kind === "mixer" || device.device_type === "mixer") seen.set(device.id, device);
    }
  }
  return [...seen.values()];
});

const mixerOpen = ref(false);
// The mixer is stored on the list, which the server mirrors to the legacy list the Stockwire sync
// reads. The list is then padded with empty inputs and outputs up to the mixer's size.
//
// We also keep a real, placeable mixer device in sync with that selection: setting a mixer mints one
// (linked back to the list via `sound_list_id`) so it shows up in the gear list and can be dragged
// onto the stage plot; clearing the mixer removes it again unless something is already patched to it.
async function saveMixer({ product, inputs, buses }) {
  const wantInputs = Number(inputs) || 0;
  const wantBuses = Number(buses) || 0;
  try {
    await graph.updateDevice(contextId.value, list.value.id, {
      attributes: {
        mixer_product_id: product?.id || null,
        mixer_product_name: product?.name || null,
        mixer_inputs: inputs ?? null,
        mixer_buses: buses ?? null,
      },
    });
    // A job list tries to read the product's specs.mixer into the console profile first (a 422
    // just means the product has none, and the old flat padding applies). Venue lists have no
    // console routes and always use the flat padding.
    let summary = null;
    if (!props.venueId && product?.id && props.jobId) {
      try {
        summary = (
          await api.put(
            `/jobs/${props.jobId}/channel-lists/${list.value.id}/console-profile`,
            { from_stockwire: true },
          )
        ).data;
      } catch {
        summary = null;
      }
    }
    const add = mixerImportPlan(
      channels.value,
      outputs.value,
      { inputs: wantInputs, buses: wantBuses },
      summary,
    );
    if (add.channels.length)
      await graph.createChannels(contextId.value, list.value.id, add.channels);
    if (add.outputs.length)
      await graph.createOutputs(contextId.value, list.value.id, add.outputs);
    if (add.busPool) {
      $q.notify({
        type: "positive",
        message: t("stockwire.mixerFilledPool", {
          inputs: add.channels.length,
          slots: add.slots,
        }),
      });
    } else if (add.channels.length || add.outputs.length) {
      $q.notify({
        type: "positive",
        message: t("stockwire.mixerFilled", {
          inputs: add.channels.length,
          buses: add.outputs.length,
        }),
      });
    }

    const existing = graph.devices.find(
      (d) =>
        (d.kind === "mixer" || d.device_type === "mixer") &&
        d.sound_list_id === list.value.id,
    );
    if (product) {
      const name = product?.name || `${list.value.name} · Mixer`;
      // The mixer device carries the product's inputs/outputs as ports so the stage plot shows
      // its I/O; if the product spec says nothing we leave it empty (the list still reflects the
      // channels/buses the user entered).
      let ports = [];
      if (product.id) {
        try {
          const { data: specs } = await api.get(`/stockwire/products/${product.id}/device-specs`);
          const form = deviceForm(null);
          form.device_type = "mixer";
          fillFormFromSpecs(form, product, specs || {});
          ports = form.ports;
        } catch {
          ports = [];
        }
      }
      if (existing) {
        const changes = { name };
        // `ports` are editor connector groups (direction in/out/both); the graph PATCH takes real
        // ports (an id and in|out only), so a 'both' group such as the GLD-80's etherCON must be
        // expanded the way the device dialog does, keeping the device's own generic ports.
        const graphPorts = mixerGraphPorts(ports, existing.ports);
        if (graphPorts.length) changes.ports = graphPorts;
        if (
          existing.name !== name ||
          (graphPorts.length && JSON.stringify(existing.ports) !== JSON.stringify(graphPorts))
        )
          await graph.updateDevice(contextId.value, existing.id, changes);
      } else {
        await graph.createAudioDevice(
          contextId.value,
          deviceCreateBody({
            name,
            device_type: "mixer",
            notes: "",
            ports,
            sound_list_id: list.value.id,
          }),
        );
      }
    } else if (existing) {
      const inUse = graph.edges.some(
        (e) => e.src_device_id === existing.id || e.dst_device_id === existing.id,
      );
      if (!inUse) await graph.deleteDevice(contextId.value, existing.id);
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
        contextId.value,
        list.value.id,
        items,
      );
      if (opts.deviceId) {
        await graph.setChannelChains(
          contextId.value,
          created.map((c) => c.id),
          [{ device_id: opts.deviceId }],
        );
      }
    } else await graph.createOutputs(contextId.value, list.value.id, items);
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
// device from it (connectors and power from the product) and links that, and a name typed in that
// is not in the library makes a device with exactly that name (a plain source with the usual single
// XLR output) and links it - so the signal flow, patch chain and gear list all show the name the
// engineer typed. The link is `attributes.source_device_id`; `attributes.device` keeps the name for
// lists and exports. A linked device carries the Stockwire product (it counts once in the sync), so the
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
      await graph.updateDevice(contextId.value, node.id, {
        attributes: { device: "", source_device_id: null },
        stockwire_product_id: null,
        stockwire_product_name: null,
      });
    } else {
      let device = pick.job_device_id
        ? graph.devices.find((d) => d.id === pick.job_device_id)
        : null;
      // Venues don't mint Stockwire product devices (that's a job-rental concern), so when only a
      // product is picked we keep the source name but don't create a graph device.
      if (!device && pick.id && contextKind.value !== 'venue')
        device = await graph.createDeviceFromProduct(contextId.value, pick);
      // A typed name that is not in the library: make the device (one per channel, like picking a
      // catalog product does, since each channel has its own physical mic).
      if (!device && !pick.id && String(pick.name || '').trim())
        device = await graph.createDeviceFromProduct(contextId.value, {
          name: String(pick.name).trim(),
          id: null,
        });
      nextId = device?.id || null;
      await graph.updateDevice(contextId.value, node.id, {
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
  if (previous && previous.id !== nextId) {
    await clearSourceEdge(node, previous);
  }
  await removeOrphanedSource(node, previous, nextId);
}

// Remove only a legacy frontend-owned source edge; current source edges are mirrored from the
// channel's source attribute and are reconciled by backend graph sync.
async function clearSourceEdge(channel, previous) {
  const stale = graph.edges.find(
    (e) =>
      e.signal === 'audio' &&
      e.src_device_id === previous.id &&
      e.dst_device_id === channel.id &&
      !(e.attributes || {}).legacy_ref,
  );
  if (!stale) return;
  try {
    await graph.deleteEdge(contextId.value, stale.id);
  } catch (err) {
    if (!isRevisionConflict(err)) failed(err);
  }
}

// The channel no longer points at its old source device, so that device goes too unless something
// else uses it (see isOrphanedBySource). The channel is updated first, so the link never dangles;
// a delete the server refuses (a patched device is a 409) just leaves the device in place.
async function removeOrphanedSource(node, previous, nextId) {
  if (!previous || previous.id === nextId) return;
  if (!isOrphanedBySource(previous.id, node.id, graph.devices, graph.edges))
    return;
  try {
    await graph.deleteDevice(contextId.value, previous.id);
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
  // Stockwire sync is a job-only operation (it reconciles a job's rig against the rental
  // library); a venue base rig has no Stockwire job to sync against, so the button is hidden.
  if (contextKind.value === 'venue') return;
  syncing.value = true;
  try {
    const { data } = await api.post(`/jobs/${contextId.value}/sync-stockwire`);
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
    await graph.createOutput(contextId.value, list.value.id, {
      name: `${t("workspace.output")} ${outputs.value.length + 1}`,
    });
  } catch (err) {
    failed(err);
  }
}

// Digital-console state for the list (job lists only): the bus-pool budget and the roles the
// console allows, shown next to the output rows. It is re-read whenever the list's outputs or
// channels change in the graph store, wherever the change was made (these rows or the panel).
const consoleSummary = ref(null);
const busRoles = computed(
  () =>
    consoleSummary.value?.profile?.bus_pool?.allowed_roles || [
      "aux",
      "group",
      "matrix",
      "main",
      "fx_send",
    ],
);
// Changes made in another browser arrive through the realtime graph events, which update the store;
// this signature makes the console panel (and its summary) reload when anything it shows changed.
const consoleSignature = computed(() =>
  consoleSignatureOf(list.value, channels.value, outputs.value, graph.devices),
);
let summaryTimer = null;
async function loadConsoleSummary() {
  if (props.venueId || !props.jobId || !list.value) {
    consoleSummary.value = null;
    return;
  }
  try {
    consoleSummary.value = (
      await api.get(`/jobs/${props.jobId}/channel-lists/${list.value.id}/console`)
    ).data;
  } catch {
    consoleSummary.value = null;
  }
}
watch([consoleSignature, () => list.value?.id], () => {
  clearTimeout(summaryTimer);
  summaryTimer = setTimeout(loadConsoleSummary, 300);
});
onMounted(loadConsoleSummary);

const modeOptions = computed(() =>
  OUTPUT_MODES.map((m) => ({
    value: m.value,
    label: t(`workspace.busMode.${m.value.replace(/[._]/g, "")}`),
  })),
);

const flowOpen = ref(false);
// The chain as a diagram; its branches follow the parent of each step (outputs branch). Computed
// from the live graph store, so a soft patch or chain change made while the diagram is open (or
// arriving over the websocket) redraws it instead of leaving a stale copy.
const liveChainNode = computed(
  () => graph.devices.find((d) => d.id === chainNode.value?.id) || chainNode.value,
);
const flowSteps = computed(() => {
  const node = liveChainNode.value;
  if (!flowOpen.value || !node) return [];
  const steps = chainForm(node, graph.edges, graph.devices);
  // A channel's flow also shows what feeds it and the direct cables it was connected with in the
  // inspector, so the diagram matches the connections; outputs keep the patch chain only.
  return chainKind.value === "channel"
    ? channelFlowTree(node, graph.edges, graph.devices, node.name, steps)
    : flowTree(node.name, steps, graph.devices);
});
function openFlow(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  flowOpen.value = true;
}
function editFromFlow() {
  flowOpen.value = false;
  openChain(chainNode.value, chainKind.value);
}

function openChain(node, kind) {
  chainNode.value = node;
  chainKind.value = kind;
  const steps = chainForm(node, graph.edges, graph.devices);
  // a soft-patched channel's chain shows that hop locked at the strip end (see ChainDialog)
  chainInitial.value =
    kind === "channel" ? chainStepsWithLock(node, steps, graph.devices) : steps;
  chainOpen.value = true;
}

async function saveChain(steps) {
  try {
    await graph.replaceChain(
      contextId.value,
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
      await graph.deleteDevice(contextId.value, node.id);
    } catch (err) {
      if (!isRevisionConflict(err)) failed(err);
    }
  });
}

const removeList = () => removeNode(list.value);
</script>

<style scoped>
/* the colour column: a round swatch, dashed and empty while no colour is set */
.channel-swatch {
  width: 28px;
  height: 28px;
  min-height: 28px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid rgba(128, 128, 128, 0.6);
}
.channel-swatch--unset {
  border-style: dashed;
}
/* The chain button shows the whole chain and sits next to the flow button, so the cell must be
   wide enough for both or the next column would cover the flow button. */
.chain-cell {
  white-space: nowrap;
  overflow: hidden;
}
/* the patch summary shortens with an ellipsis; the flow button next to it keeps its place */
.chain-cell .chain-main {
  max-width: calc(100% - 40px);
  overflow: hidden;
}
.chain-cell .chain-main :deep(.q-btn__content) {
  flex-wrap: nowrap;
  min-width: 0;
}
.chain-cell .chain-main :deep(.q-btn__content > .block) {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
