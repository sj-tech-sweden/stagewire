<template>
  <q-card
    flat
    bordered
    class="q-mb-md"
    data-testid="console-panel"
  >
    <!-- one small save indicator for the whole panel: everything saves by itself -->
    <div
      class="row items-center justify-end q-px-sm q-pt-xs text-caption"
      style="min-height: 24px"
      data-testid="console-save-status"
      :data-status="saveStatus"
    >
      <template v-if="saveStatus === 'saving'">
        <q-spinner
          size="12px"
          class="q-mr-xs"
        />{{ t("console.statusSaving") }}
      </template>
      <template v-else-if="saveStatus === 'saved'">
        <q-icon
          name="check"
          color="positive"
          size="14px"
          class="q-mr-xs"
        />{{ t("console.statusSaved") }}
      </template>
      <template v-else-if="saveStatus === 'error'">
        <q-icon
          name="error_outline"
          color="negative"
          size="14px"
          class="q-mr-xs"
        />
        <span class="text-negative">{{ t("console.statusError") }}</span>
        <q-btn
          flat
          dense
          no-caps
          size="sm"
          color="primary"
          :label="t('console.statusRetry')"
          data-testid="console-save-retry"
          @click="retrySaves"
        />
      </template>
    </div>
    <q-tabs
      :model-value="tab"
      dense
      align="left"
      active-color="primary"
      indicator-color="primary"
      inline-label
      mobile-arrows
      @update:model-value="requestTab"
    >
      <q-tab
        name="profile"
        icon="tune"
        :label="t('console.tabProfile')"
        no-caps
        data-testid="console-tab-profile"
      />
      <q-tab
        name="buses"
        icon="account_tree"
        :label="t('console.tabBuses')"
        no-caps
        data-testid="console-tab-buses"
      />
      <q-tab
        name="links"
        icon="link"
        :label="t('console.tabLinks')"
        no-caps
        data-testid="console-tab-links"
      />
      <q-tab
        name="patch"
        icon="cable"
        :label="t('console.tabPatch')"
        no-caps
        data-testid="console-tab-patch"
      />
      <q-tab
        v-if="!simple"
        name="faders"
        icon="grid_view"
        :label="t('console.tabFaders')"
        no-caps
        data-testid="console-tab-faders"
      />
      <q-tab
        v-if="!simple && summary?.dca_count > 0"
        name="dca"
        icon="workspaces"
        :label="t('console.tabDca')"
        no-caps
        data-testid="console-tab-dca"
      />
      <q-tab
        v-if="!simple"
        name="fx"
        icon="graphic_eq"
        :label="t('console.tabFx')"
        no-caps
        data-testid="console-tab-fx"
      />
    </q-tabs>
    <q-separator />

    <q-tab-panels
      v-model="tab"
      animated
      keep-alive
    >
      <!-- Profile ------------------------------------------------------------------------->
      <q-tab-panel name="profile">
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-chip
            square
            :color="simple ? 'grey-7' : 'primary'"
            text-color="white"
            data-testid="console-source"
          >
            {{ simple ? t("console.sourceNone") : t(`console.source.${summary?.source}`) }}
          </q-chip>
          <span
            v-if="summary?.profile?.name"
            class="text-subtitle2"
          >{{ summary.profile.name }}</span>
        </div>
        <div
          v-if="simple"
          class="text-grey-6 q-mb-sm"
          data-testid="console-simple-note"
        >
          {{ t("console.simpleNote") }}
        </div>
        <div
          v-else
          class="text-caption text-grey-6 q-mb-sm"
        >
          {{ profileFacts }}
        </div>

        <div class="row q-col-gutter-sm items-center q-mb-md">
          <div class="col-12 col-sm-5">
            <q-select
              v-model="presetKey"
              :options="presets"
              option-value="key"
              option-label="name"
              emit-value
              map-options
              dense
              outlined
              :label="t('console.preset')"
              data-testid="console-preset"
            />
          </div>
          <div class="col-auto">
            <q-btn
              color="primary"
              no-caps
              :label="t('console.applyPreset')"
              :disable="!presetKey"
              data-testid="console-apply-preset"
              @click="setProfile({ preset: presetKey })"
            />
          </div>
          <div class="col-auto">
            <q-btn
              outline
              no-caps
              icon="cloud_download"
              :label="t('console.fromStockwire')"
              data-testid="console-from-stockwire"
              @click="setProfile({ from_stockwire: true })"
            />
          </div>
          <div class="col-auto">
            <q-btn
              outline
              no-caps
              icon="edit"
              :label="t('console.manual')"
              data-testid="console-manual"
              @click="openManual"
            />
          </div>
          <div class="col-auto">
            <q-btn
              flat
              no-caps
              color="negative"
              icon="close"
              :label="t('console.clear')"
              :disable="simple"
              data-testid="console-clear"
              @click="setProfile({ clear: true })"
            />
          </div>
        </div>

        <div class="text-subtitle2">
          {{ t("console.accessories") }}
        </div>
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t("console.accessoriesHelp") }}
        </div>
        <q-btn
          v-if="!accLoaded"
          flat
          no-caps
          icon="search"
          :label="t('console.loadSuggestions')"
          data-testid="console-load-accessories"
          @click="loadAccessories"
        />
        <div
          v-else-if="!accessoryRows.length"
          class="text-grey-6"
        >
          {{ t("console.noSuggestions") }}
        </div>
        <q-list
          v-else
          dense
          separator
          bordered
          data-testid="console-accessories"
        >
          <q-item
            v-for="row in accessoryRows"
            :key="row.product_id"
          >
            <q-item-section side>
              <q-checkbox
                v-model="row.picked"
                dense
                @update:model-value="accSaver.flush()"
              />
            </q-item-section>
            <q-item-section>
              {{ row.name || row.product_id }}
              <q-item-label
                v-if="row.required"
                caption
                class="text-warning"
              >
                {{ t("console.required") }}
              </q-item-label>
            </q-item-section>
            <q-item-section
              side
              style="width: 90px"
            >
              <q-input
                v-model.number="row.quantity"
                type="number"
                min="1"
                dense
                outlined
                :disable="!row.picked"
                @update:model-value="accSaver.schedule()"
              />
            </q-item-section>
          </q-item>
        </q-list>

        <!-- Expansion cards / ports ---------------------------------------------------------->
        <q-separator class="q-my-md" />
        <div class="text-subtitle2">
          {{ t("console.expansion") }}
        </div>
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t("console.expansionHelp") }}
        </div>
        <div
          v-if="!expansion.available.length"
          class="text-grey-6"
          data-testid="console-expansion-none"
        >
          {{ t("console.expansionNone") }}
        </div>
        <template v-else>
          <q-card
            v-for="port in expansion.available"
            :key="port.protocol"
            flat
            bordered
            class="q-pa-sm q-mb-sm"
            data-testid="console-expansion-port"
          >
            <div class="row items-center q-gutter-sm">
              <b>{{ port.protocol }}</b>
              <span class="text-caption text-grey-6">{{ expansionFacts(port) }}</span>
              <q-space />
              <q-btn
                dense
                outline
                no-caps
                icon="add"
                :label="t('console.expansionFit')"
                :disable="cardsOf(port).length >= (port.slots || 1)"
                data-testid="console-expansion-fit"
                @click="fitCard(port)"
              />
            </div>
            <div
              v-for="card in cardsOf(port)"
              :key="card.key"
              class="row q-col-gutter-sm items-start q-mt-xs"
              data-testid="console-expansion-card"
            >
              <div class="col-5 col-sm-3">
                <q-input
                  v-model.number="card.channels_in"
                  type="number"
                  min="0"
                  :max="expansionLimit(port, 'in') ?? undefined"
                  dense
                  outlined
                  :label="t('console.channelsIn')"
                  :hint="limitHint(port, 'in')"
                  data-testid="console-expansion-in"
                  @update:model-value="expSaver.schedule()"
                />
              </div>
              <div class="col-5 col-sm-3">
                <q-input
                  v-model.number="card.channels_out"
                  type="number"
                  min="0"
                  :max="expansionLimit(port, 'out') ?? undefined"
                  dense
                  outlined
                  :label="t('console.channelsOut')"
                  :hint="limitHint(port, 'out')"
                  data-testid="console-expansion-out"
                  @update:model-value="expSaver.schedule()"
                />
              </div>
              <div class="col-auto text-caption q-pt-sm">
                {{ t("console.expansionSockets", { n: (Number(card.channels_in) || 0) + (Number(card.channels_out) || 0) }) }}
              </div>
              <div class="col-auto">
                <q-btn
                  flat
                  round
                  dense
                  color="negative"
                  icon="delete"
                  :aria-label="t('workspace.remove')"
                  data-testid="console-expansion-remove"
                  @click="removeCard(card)"
                />
              </div>
            </div>
          </q-card>
        </template>
      </q-tab-panel>

      <!-- Buses --------------------------------------------------------------------------->
      <q-tab-panel name="buses">
        <div
          v-if="budget?.enabled"
          data-testid="console-budget"
        >
          <div class="row items-center q-mb-xs">
            <div class="text-subtitle2 col">
              {{ t("console.budget") }}
            </div>
            <div data-testid="console-budget-text">
              {{ budget.used_slots }} / {{ budget.total_slots }} {{ t("console.slots") }}
            </div>
            <div
              v-if="budget.fx_send_slots"
              class="text-caption text-grey-7 full-width"
              data-testid="console-budget-fx"
            >
              {{ t("console.fxPoolNote") }} ({{ budget.fx_send_slots }})
            </div>
          </div>
          <q-linear-progress
            :value="budget.total_slots ? Math.min(budget.used_slots / budget.total_slots, 1) : 0"
            size="14px"
            rounded
            :color="budget.ok ? 'positive' : 'negative'"
            class="q-mb-sm"
          />
          <q-banner
            v-if="!budget.ok"
            dense
            rounded
            class="bg-warning text-black q-mb-sm"
            data-testid="console-budget-warning"
          >
            <div
              v-for="v in budget.violations"
              :key="v"
            >
              {{ v }}
            </div>
          </q-banner>
        </div>
        <div
          v-else
          class="text-grey-6 q-mb-sm"
          data-testid="console-no-budget"
        >
          {{ t("console.noBudget") }}
        </div>

        <q-list
          bordered
          separator
          class="q-mb-sm"
        >
          <q-item
            v-for="bus in buses"
            :key="bus.id"
            data-testid="console-bus"
          >
            <q-item-section>
              <q-input
                :model-value="bus.name"
                dense
                borderless
                @change="(v) => updateBus(bus, { name: v })"
              />
              <q-item-label
                v-if="slotLabel(bus)"
                caption
              >
                {{ slotLabel(bus) }}
              </q-item-label>
            </q-item-section>
            <q-item-section
              side
              style="min-width: 110px"
            >
              <q-select
                :model-value="bus.mode"
                :options="busModes"
                dense
                outlined
                emit-value
                map-options
                :label="t('console.mode')"
                data-testid="console-bus-mode"
                @update:model-value="(v) => updateBus(bus, { mode: v })"
              />
            </q-item-section>
            <q-item-section
              v-if="!simple"
              side
              style="min-width: 120px"
            >
              <q-select
                :model-value="bus.role"
                :options="roles"
                dense
                outlined
                :label="t('console.role')"
                data-testid="console-bus-role"
                @update:model-value="(v) => updateBus(bus, { role: v })"
              />
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                @click="removeBus(bus)"
              />
            </q-item-section>
          </q-item>
          <q-item v-if="!buses.length">
            <q-item-section class="text-grey-6">
              {{ t("workspace.noOutputs") }}
            </q-item-section>
          </q-item>
        </q-list>

        <div class="row q-col-gutter-sm items-center">
          <div class="col-12 col-sm">
            <q-input
              v-model="newBus.name"
              dense
              outlined
              :label="t('console.busName')"
              data-testid="console-new-bus-name"
            />
          </div>
          <div class="col-6 col-sm-2">
            <q-select
              v-model="newBus.mode"
              :options="busModes"
              dense
              outlined
              emit-value
              map-options
              :label="t('console.mode')"
              data-testid="console-new-bus-mode"
            />
          </div>
          <div
            v-if="!simple"
            class="col-6 col-sm-2"
          >
            <q-select
              v-model="newBus.role"
              :options="roles"
              dense
              outlined
              :label="t('console.role')"
            />
          </div>
          <div class="col-12 col-sm-auto">
            <q-btn
              color="primary"
              no-caps
              icon="add"
              :label="t('console.addBus')"
              data-testid="console-add-bus"
              @click="addBus"
            />
          </div>
        </div>
      </q-tab-panel>

      <!-- Stereo links -------------------------------------------------------------------->
      <q-tab-panel name="links">
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t("console.linksHelp") }}
        </div>
        <!-- Pair tiles: link or unlink from here; the Inputs page's Stereo toggle does the same thing
             and both always show the same state (the server keeps one pair, two views of it). -->
        <div
          class="row items-center q-gutter-sm q-mb-sm"
          data-testid="console-pair-tools"
        >
          <q-input
            v-model="pairRange"
            dense
            outlined
            class="col-12 col-sm-5"
            :label="t('console.pairRange')"
            data-testid="console-pair-range"
            @keyup.enter="linkRange"
          />
          <q-btn
            dense
            outline
            no-caps
            icon="link"
            :label="t('console.linkRange')"
            :disable="pairBusy || !pairRange"
            data-testid="console-pair-link-range"
            @click="linkRange"
          />
          <q-btn
            dense
            outline
            no-caps
            icon="link_off"
            :label="t('console.unlinkRange')"
            :disable="pairBusy || !pairRange"
            data-testid="console-pair-unlink-range"
            @click="unlinkRange"
          />
        </div>
        <div
          class="row q-gutter-xs q-mb-md"
          data-testid="console-pair-grid"
        >
          <q-btn
            v-for="tile in pairTiles"
            :key="tile.low"
            no-caps
            dense
            unelevated
            class="pair-tile"
            :color="tile.state === 'linked' ? 'primary' : tile.state === 'blocked' ? 'negative' : undefined"
            :outline="tile.state !== 'linked'"
            :disable="pairBusy || tile.state === 'blocked'"
            :icon="tile.state === 'linked' ? 'link' : tile.missing.length ? 'add' : undefined"
            :label="tile.label"
            data-testid="console-pair-tile"
            :data-state="tile.state"
            @click="onTile(tile)"
          >
            <q-tooltip>
              {{
                tile.state === "linked"
                  ? t("console.pairLinked")
                  : tile.state === "blocked"
                    ? t("console.pairBlocked")
                    : tile.missing.length
                      ? t("console.pairCreates", { n: tile.missing.join(", ") })
                      : t("console.pairFree")
              }}
            </q-tooltip>
          </q-btn>
          <div
            v-if="!pairTiles.length"
            class="text-grey-6"
          >
            {{ t("console.noChannels") }}
          </div>
        </div>
        <q-list
          bordered
          separator
        >
          <q-item
            v-for="ch in strips"
            :key="ch.id"
            data-testid="console-strip"
          >
            <q-item-section>
              <q-item-label>
                <b>{{ stripNumber(ch) }}</b> {{ ch.source_label }}
                <q-chip
                  v-if="ch.is_stereo_linked"
                  dense
                  square
                  color="primary"
                  text-color="white"
                  data-testid="console-ganged"
                >
                  {{ t("console.stereo") }}
                </q-chip>
              </q-item-label>
            </q-item-section>
            <q-item-section
              v-if="ch.is_stereo_linked"
              side
            >
              <q-btn
                outline
                no-caps
                dense
                icon="link_off"
                :label="t('console.unlink')"
                data-testid="console-unlink"
                @click="unlink(ch)"
              />
            </q-item-section>
          </q-item>
          <q-item v-if="!strips.length">
            <q-item-section class="text-grey-6">
              {{ t("console.noChannels") }}
            </q-item-section>
          </q-item>
        </q-list>
      </q-tab-panel>

      <!-- Soft patch ---------------------------------------------------------------------->
      <q-tab-panel name="patch">
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t("console.patchHelp") }}
        </div>
        <div
          v-if="!soft"
          class="text-grey-6"
        >
          …
        </div>
        <template v-else>
          <div class="row items-center q-gutter-sm q-mb-sm">
            <q-btn-toggle
              v-model="patchMode"
              no-caps
              dense
              unelevated
              toggle-color="primary"
              :options="[
                { label: t('console.inputSocket'), value: 'in' },
                { label: t('console.directOut'), value: 'out' },
                { label: t('console.busOutputs'), value: 'bus' },
              ]"
              data-testid="console-patch-mode"
              @update:model-value="onModeChange"
            />
            <q-btn
              outline
              no-caps
              dense
              icon="auto_fix_high"
              :label="t('console.autoPatch')"
              data-testid="console-auto-patch"
              @click="openAuto(selIds)"
            />
            <q-btn
              flat
              no-caps
              dense
              color="negative"
              icon="layers_clear"
              :label="t('console.bulkClear')"
              data-testid="console-bulk-clear"
              @click="openBulkClear"
            />
          </div>
          <div class="text-caption text-grey-6 q-mb-sm">
            {{ patchMode === "out" ? t("console.directOutHint") : patchMode === "bus" ? t("console.busOutHint") : t("console.patchSyncNote") }}
          </div>
          <div
            v-if="patchMode === 'in'"
            class="text-caption text-grey-6 q-mb-sm"
            data-testid="console-split-tab-hint"
          >
            {{ t("console.splitTabHint") }}
          </div>

          <div class="row q-col-gutter-md">
            <!-- ports: one entry per source port, however many sockets it has -->
            <div class="col-12 col-md-4">
              <q-list
                v-if="portGroups.length"
                bordered
                separator
                dense
                data-testid="console-port-list"
              >
                <template
                  v-for="g in portGroups"
                  :key="g.device_id"
                >
                  <q-item-label
                    header
                    class="text-weight-medium"
                  >
                    {{ g.device_name }}
                  </q-item-label>
                  <q-item
                    v-for="p in g.ports"
                    :key="p.port_id"
                    clickable
                    :active="selPortKey === portKey(p)"
                    active-class="bg-primary text-white"
                    data-testid="console-port"
                    @click="selectPort(p)"
                  >
                    <q-item-section>
                      <q-item-label>{{ p.connector || p.port_id }}</q-item-label>
                      <q-item-label caption>
                        {{ p.port_id }}
                      </q-item-label>
                    </q-item-section>
                    <q-item-section side>
                      <q-badge
                        :color="portUsed(p) >= p.channels ? 'negative' : 'grey-7'"
                        text-color="white"
                      >
                        {{ portUsed(p) }} / {{ p.channels }}
                      </q-badge>
                    </q-item-section>
                  </q-item>
                </template>
              </q-list>
              <div
                v-else
                class="text-grey-6"
                data-testid="console-no-ports"
              >
                {{ t("console.noPorts") }}
              </div>
            </div>

            <div class="col-12 col-md-8">
              <q-select
                v-model="selChannelId"
                :options="channelOptions"
                use-input
                input-debounce="0"
                emit-value
                map-options
                clearable
                dense
                outlined
                :label="t('console.patchChannel')"
                data-testid="console-patch-channel"
                @filter="filterChannels"
              />
              <div
                v-if="selChannel"
                class="row items-center q-gutter-sm q-mt-xs"
              >
                <q-chip
                  dense
                  square
                  :color="selRef ? 'primary' : 'grey-7'"
                  text-color="white"
                  data-testid="console-patch-current"
                >
                  {{ selRef ? refLabel(selRef) : t("console.unpatched") }}
                </q-chip>
                <span
                  v-if="selOrphaned"
                  class="text-negative text-caption"
                >{{ t("console.orphaned") }}</span>
                <q-btn
                  v-if="selRef"
                  flat
                  dense
                  no-caps
                  color="negative"
                  icon="link_off"
                  :label="t('console.clearSocket')"
                  data-testid="console-patch-clear"
                  @click="assignSocket(selChannel, null)"
                />
              </div>

              <!-- a bus can leave from several places: one chip per endpoint (a stereo one has L and R) -->
              <div
                v-if="patchMode === 'bus' && selChannel"
                class="q-mt-xs"
                data-testid="console-bus-endpoints"
              >
                <div class="text-caption text-grey-6">
                  {{ t("console.busEndpoints") }} · {{ selChannel.mode }}
                </div>
                <div class="row items-center q-gutter-xs">
                  <q-chip
                    v-for="ep in selChannel.out_endpoints"
                    :key="ep.id"
                    dense
                    square
                    removable
                    color="primary"
                    text-color="white"
                    data-testid="console-bus-endpoint"
                    @remove="removeEndpoint(selChannel, ep)"
                  >
                    {{ endpointText(selChannel, ep) }}
                  </q-chip>
                  <span
                    v-if="!selChannel.out_endpoints.length"
                    class="text-grey-6 text-caption"
                  >{{ t("console.busNoEndpoints") }}</span>
                  <q-chip
                    v-for="(sh, i) in selShortages"
                    :key="`short-${i}`"
                    dense
                    square
                    color="warning"
                    text-color="black"
                    icon="warning"
                    data-testid="console-endpoint-shortage"
                  >
                    {{ t("console.endpointNeeds", { need: sh.need, have: sh.have }) }}
                  </q-chip>
                </div>
                <q-toggle
                  v-model="addEndpoint"
                  dense
                  :label="t('console.addEndpoint')"
                  data-testid="console-add-endpoint"
                />
                <div
                  v-if="addEndpoint"
                  class="text-caption text-grey-6"
                >
                  {{ t("console.addEndpointHint") }}
                </div>
              </div>

              <div
                v-if="selPort"
                class="q-mt-sm"
              >
                <div class="row items-center q-gutter-sm q-mb-xs">
                  <span class="text-subtitle2">{{ selPort.device_name }} · {{ selPort.connector || selPort.port_id }}</span>
                  <q-space />
                  <q-pagination
                    v-if="socketPages > 1"
                    v-model="gridPage"
                    :max="socketPages"
                    :max-pages="5"
                    boundary-numbers
                    direction-links
                    dense
                    data-testid="console-socket-pager"
                  />
                </div>
                <div
                  class="socket-grid"
                  data-testid="console-socket-grid"
                >
                  <q-btn
                    v-for="sk in pagedSockets"
                    :key="sk.key"
                    dense
                    no-caps
                    unelevated
                    size="sm"
                    class="socket-btn"
                    :outline="!sk.owner"
                    :color="sk.owner ? ((sk.owners || [sk.owner]).includes(selChannelId) ? 'primary' : 'grey-8') : undefined"
                    :data-testid="`console-socket-${sk.socket}`"
                    @click="clickSocket(sk)"
                  >
                    <div class="column items-center no-wrap">
                      <span>{{ sk.socket }}</span>
                      <span
                        v-if="sk.owner"
                        class="text-caption"
                      >{{ sk.ownerLabel || "?" }}</span>
                    </div>
                    <q-badge
                      v-if="sk.shared"
                      floating
                      color="warning"
                      text-color="black"
                      data-testid="console-socket-shared"
                    >
                      {{ t("console.splitBadge", { n: sk.owners.length }) }}
                    </q-badge>
                  </q-btn>
                </div>
                <div class="text-caption text-grey-6 q-mt-xs">
                  {{ t("console.socketHint") }}
                </div>
                <!-- the per-channel picker only exists while open and lists just this port -->
                <q-expansion-item
                  dense
                  class="q-mt-sm"
                  :label="t('console.quickPick')"
                  @show="quickOpen = true"
                  @hide="quickOpen = false"
                >
                  <q-select
                    v-if="quickOpen && selChannel"
                    :model-value="selRef ? refKey(selRef) : null"
                    :options="quickOptions"
                    emit-value
                    map-options
                    clearable
                    dense
                    outlined
                    :label="t('console.socketOf', { ch: selChannel.channel_number })"
                    data-testid="console-quick-pick"
                    @update:model-value="quickAssign"
                  />
                </q-expansion-item>
              </div>
              <div
                v-else
                class="text-grey-6 q-mt-sm"
              >
                {{ t("console.pickPort") }}
              </div>
            </div>
          </div>

          <!-- overview: which socket each channel is on, with multi-select for auto patch -->
          <div class="row items-center q-gutter-sm q-mt-md">
            <div class="text-subtitle2">
              {{ t("console.channelsOverview") }}
            </div>
            <q-chip
              dense
              :color="selIds.length ? 'primary' : 'grey-7'"
              text-color="white"
              data-testid="console-select-count"
            >
              {{ t("console.nSelected", { n: selIds.length }) }}
            </q-chip>
          </div>
          <div class="row items-center q-col-gutter-xs q-mb-xs">
            <div class="col-12 col-sm-4">
              <q-input
                v-model="overviewQuery"
                dense
                outlined
                clearable
                :label="t('common.search')"
                data-testid="console-overview-search"
              />
            </div>
            <div class="col-12 col-sm-4">
              <q-input
                v-model="rangeText"
                dense
                outlined
                :label="t('console.rangeLabel')"
                data-testid="console-select-range"
                @keyup.enter="applyRange"
              >
                <template #append>
                  <q-btn
                    flat
                    dense
                    no-caps
                    :label="t('console.rangeApply')"
                    data-testid="console-select-range-apply"
                    @click="applyRange"
                  />
                </template>
              </q-input>
            </div>
            <div class="col-12 col-sm-4 row q-gutter-xs">
              <q-btn
                flat
                dense
                no-caps
                :label="t('console.selAll')"
                data-testid="console-select-all"
                @click="selectAllVisible"
              />
              <q-btn
                flat
                dense
                no-caps
                :label="t('console.selNone')"
                data-testid="console-select-none"
                @click="selectNoneVisible"
              />
              <q-btn
                flat
                dense
                no-caps
                :label="t('console.selInvert')"
                data-testid="console-select-invert"
                @click="selectInvertVisible"
              />
            </div>
          </div>
          <div
            v-if="selIds.length"
            class="row items-center q-gutter-sm q-mb-xs"
            data-testid="console-select-bar"
          >
            <q-btn
              color="primary"
              dense
              no-caps
              icon="auto_fix_high"
              :label="t('console.autoPatchSel', { n: selIds.length })"
              data-testid="console-select-auto"
              @click="openAuto(selIds)"
            />
            <q-btn
              flat
              dense
              no-caps
              color="negative"
              icon="link_off"
              :label="t('console.clearSel', { n: selPatched.length })"
              :disable="!selPatched.length"
              data-testid="console-select-clear"
              @click="clearSelected"
            />
            <q-btn
              flat
              dense
              no-caps
              icon="close"
              :label="t('console.deselect')"
              data-testid="console-select-deselect"
              @click="selIds = []"
            />
            <span
              v-if="selIds.length > 1"
              class="text-caption text-grey-6"
            >{{ t("console.multiTapHint", { n: selIds.length }) }}</span>
          </div>
          <q-virtual-scroll
            v-if="visibleStrips.length"
            :items="visibleStrips"
            :virtual-scroll-item-size="36"
            separator
            style="max-height: 30vh"
            class="rounded-borders"
            data-testid="console-patch-overview"
          >
            <template #default="{ item: ch }">
              <q-item
                :key="ch.id"
                dense
                clickable
                :active="ch.id === selChannelId"
                active-class="bg-primary text-white"
                data-testid="console-patch-card"
                @click="selChannelId = ch.id"
              >
                <q-item-section avatar>
                  <q-checkbox
                    :model-value="selIds.includes(ch.id)"
                    dense
                    data-testid="console-patch-check"
                    @click.stop
                    @update:model-value="(v, evt) => onCheck(ch.id, evt)"
                  />
                </q-item-section>
                <q-item-section>
                  {{ numberedLabel(targetPrefix, ch.channel_number, ch.source_label) }}
                  <q-chip
                    v-if="patchMode === 'in' && ch.shared_with && ch.shared_with.length"
                    dense
                    square
                    color="warning"
                    text-color="black"
                    data-testid="console-shares-chip"
                  >
                    {{ t("console.sharesSocket", { who: sharedChannelsText(ch.shared_with) }) }}
                  </q-chip>
                  <q-chip
                    v-if="patchMode === 'bus' && endpointShortages(ch).length"
                    dense
                    square
                    color="warning"
                    text-color="black"
                    icon="warning"
                  >
                    {{ t("console.endpointNeeds", { need: endpointShortages(ch)[0].need, have: endpointShortages(ch)[0].have }) }}
                  </q-chip>
                  <q-chip
                    v-if="ch.is_stereo_linked"
                    dense
                    square
                    color="primary"
                    text-color="white"
                  >
                    {{ t("console.stereo") }} {{ ch.stereo_link_role === "primary" ? "L" : "R" }}
                  </q-chip>
                </q-item-section>
                <q-item-section side>
                  <span :class="{ 'text-negative': ch[`${modeField}_orphaned`] }">
                    {{ patchMode === "bus" ? (ch.out_endpoints.length ? ch.out_endpoints.map((e) => endpointText(ch, e)).join("  ·  ") : "—") : ch[modeField] ? refLabel(ch[modeField]) : "—" }}
                  </span>
                </q-item-section>
              </q-item>
            </template>
          </q-virtual-scroll>
          <div
            v-else
            class="text-grey-6"
          >
            {{ targetStrips.length ? t("console.noMatch") : patchMode === "bus" ? t("console.noBuses") : t("console.noChannels") }}
          </div>
        </template>
      </q-tab-panel>

      <!-- Fader map ----------------------------------------------------------------------->
      <q-tab-panel name="faders">
        <div
          v-if="!fader?.enabled"
          class="text-grey-6"
          data-testid="console-no-faders"
        >
          {{ t("console.noSurface") }}
        </div>
        <template v-else>
          <div class="text-caption text-grey-6 q-mb-sm">
            {{ t("console.faderNote") }} {{ t("console.faderAutoFill") }}
          </div>
          <div class="row items-center q-gutter-sm q-mb-sm">
            <!-- starting point (follows the console) until the first edit; then it is the engineer's -->
            <q-chip
              dense
              :color="fader.custom ? 'primary' : undefined"
              :text-color="fader.custom ? 'white' : undefined"
              :outline="!fader.custom"
              :icon="fader.custom ? 'push_pin' : 'auto_awesome'"
              :data-testid="fader.custom ? 'console-fader-custom' : 'console-fader-start'"
            >
              {{ fader.custom ? t("console.faderCustom") : t("console.faderStart") }}
            </q-chip>
            <q-chip
              v-if="unplacedCount > 0"
              dense
              clickable
              color="warning"
              text-color="black"
              icon="inventory_2"
              data-testid="console-fader-unplaced"
              @click="showUnplaced"
            >
              {{ t("console.faderUnplacedN", { n: unplacedCount }) }}
            </q-chip>
            <!-- edits save the moment they are made; this only turns dragging / choosing on -->
            <q-btn
              :outline="!editingFaders"
              :color="editingFaders ? 'primary' : undefined"
              no-caps
              dense
              :icon="editingFaders ? 'check' : 'edit'"
              :label="editingFaders ? t('console.faderDone') : t('console.faderEdit')"
              data-testid="console-fader-edit"
              @click="editingFaders ? (editingFaders = false) : startFaderEdit()"
            />
            <span
              v-if="editingFaders"
              class="text-caption text-grey-6"
            >{{ t("console.faderAutosaveNote") }}</span>
            <q-btn
              flat
              no-caps
              dense
              icon="auto_fix_high"
              :label="t('console.faderAutoFillBtn')"
              data-testid="console-fader-autofill"
              @click="autoFillFaders"
            />
            <q-btn
              flat
              no-caps
              dense
              icon="playlist_add"
              :disable="!(unplacedCount > 0)"
              :label="t('console.faderPlaceUnplaced', { n: unplacedCount })"
              data-testid="console-fader-place-unplaced"
              @click="placeUnplaced"
            />
          </div>
          <q-banner
            v-if="fader.overflow"
            dense
            rounded
            class="bg-warning text-black q-mb-sm"
          >
            {{ t("console.faderOverflow", { n: fader.overflow }) }}
          </q-banner>
          <!-- built-in FX nobody has set up are not on the faders by default; add them here -->
          <div
            v-if="hiddenFx.length"
            class="q-mb-sm q-pa-sm hidden-fx"
            data-testid="console-hidden-fx"
          >
            <div class="row items-center q-gutter-sm q-mb-xs">
              <q-icon
                name="visibility_off"
                size="18px"
              />
              <span class="text-subtitle2">{{ t("console.hiddenFx") }} ({{ hiddenFx.length }})</span>
              <q-space />
              <q-btn
                dense
                outline
                no-caps
                icon="playlist_add"
                :label="t('console.addAllFx')"
                data-testid="console-add-all-fx"
                @click="addToFaders(hiddenFx.map((x) => x.id))"
              />
            </div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="st in hiddenFx"
                :key="st.id"
                dense
                square
                clickable
                :class="`kind-${st.kind}`"
                :icon="stripKindIcon(st.kind)"
                :data-testid="`console-hidden-fx-strip`"
                @click="addToFaders([st.id])"
              >
                {{ st.label }}
                <q-tooltip>{{ t("console.addToFaders") }}</q-tooltip>
                <q-icon
                  name="add"
                  size="14px"
                  class="q-ml-xs"
                />
              </q-chip>
            </div>
          </div>
          <q-tabs
            v-model="layerNo"
            dense
            align="left"
            active-color="primary"
            indicator-color="primary"
            no-caps
          >
            <q-tab
              v-for="l in fader.layers"
              :key="l.layer"
              :name="l.layer"
              :label="t('console.layer', { n: l.layer })"
            />
          </q-tabs>
          <div
            class="row q-col-gutter-md q-mt-xs"
            data-testid="console-fader-grid"
          >
            <div
              v-for="bank in currentLayer?.banks || []"
              :key="bank.id"
              class="col-12 col-md"
            >
              <div class="text-subtitle2 q-mb-xs">
                {{ bank.label || bank.id }}
              </div>
              <div class="fader-bank">
                <div
                  v-for="s in bank.strips"
                  :key="s.fader"
                  class="fader-strip"
                  :class="[
                    `kind-${s.kind}`,
                    { 'fader-editable': editingFaders, 'fader-over': overSlot === s.slot },
                  ]"
                  :draggable="editingFaders && !!s.id"
                  data-testid="console-fader"
                  @click="editingFaders && openCell(s)"
                  @dragstart="editingFaders && onDragStart($event, { slot: s.slot })"
                  @dragend="onDragEnd"
                  @dragover.prevent="editingFaders && (overSlot = s.slot)"
                  @dragleave="overSlot === s.slot && (overSlot = null)"
                  @drop.prevent="editingFaders && onDropCell(s.slot, $event)"
                >
                  <div class="text-caption text-grey-5 row items-center no-wrap">
                    {{ s.fader }}
                    <q-icon
                      v-if="s.kind !== 'empty'"
                      :name="stripKindIcon(s.kind)"
                      size="12px"
                      class="q-ml-xs"
                    />
                    <q-icon
                      v-if="draftPinned(s)"
                      name="push_pin"
                      size="12px"
                      class="q-ml-xs"
                      data-testid="console-fader-pin"
                    />
                    <q-badge
                      v-if="s.id && placementCount(s) > 1"
                      color="primary"
                      class="q-ml-xs"
                      data-testid="console-fader-dup"
                    >
                      ×{{ placementCount(s) }}
                    </q-badge>
                  </div>
                  <div class="ellipsis text-weight-medium">
                    {{ s.label || "—" }}
                  </div>
                  <div class="text-caption">
                    {{ s.kind === "empty" ? "" : s.number }}<span v-if="s.stereo"> · ST</span>
                    <span v-if="s.kind === 'dca' && s.members"> · {{ s.members }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Strip tray: drag a strip onto a fader to pin it there, drop a strip here to unpin it.
               Tapping a fader still opens the chooser, which is the touch / keyboard path. -->
          <div
            v-if="editingFaders"
            class="fader-tray q-mt-md"
            :class="{ 'fader-over': overTray }"
            data-testid="console-fader-tray"
            @dragover.prevent="overTray = true"
            @dragleave="overTray = false"
            @drop.prevent="onDropTray"
          >
            <div class="text-caption text-grey-6 q-mb-xs">
              {{ t("console.faderTray") }}
            </div>
            <div class="row items-center q-gutter-xs q-mb-xs">
              <q-chip
                dense
                clickable
                :outline="!trayUnplacedOnly"
                color="warning"
                text-color="black"
                icon="inventory_2"
                data-testid="console-fader-tray-unplaced"
                @click="trayUnplacedOnly = !trayUnplacedOnly"
              >
                {{ t("console.faderTrayUnplaced") }}
              </q-chip>
              <q-input
                v-model="trayQuery"
                dense
                outlined
                clearable
                class="col"
                :label="t('common.search')"
                data-testid="console-fader-tray-search"
              />
              <q-chip
                v-for="k in trayKinds"
                :key="k.kind"
                dense
                clickable
                :outline="!trayKindsOn.includes(k.kind)"
                color="primary"
                text-color="white"
                :icon="stripKindIcon(k.kind)"
                :data-testid="`console-fader-tray-kind-${k.kind}`"
                @click="toggleTrayKind(k.kind)"
              >
                {{ t(`console.stripKind.${k.kind}`) }} {{ k.n }}
              </q-chip>
            </div>
            <div class="row q-gutter-xs">
              <q-chip
                v-for="st in trayStrips"
                :key="st.id"
                dense
                square
                draggable="true"
                :class="`kind-${st.kind}`"
                :icon="stripKindIcon(st.kind)"
                :outline="stripState(st.id) === 'unplaced'"
                :color="stripState(st.id) === 'unplaced' ? 'warning' : undefined"
                data-testid="console-fader-tray-strip"
                @dragstart="onDragStart($event, { strip: st.id })"
                @dragend="onDragEnd"
              >
                {{ st.number }} {{ st.label }}
                <q-badge
                  v-if="trayPlacements(st.id) > 0"
                  class="q-ml-xs"
                  color="grey-7"
                  data-testid="console-fader-tray-placed"
                >
                  {{ t("console.placedN", { n: trayPlacements(st.id) }) }}
                </q-badge>
              </q-chip>
            </div>
          </div>
        </template>
      </q-tab-panel>

      <!-- DCAs ---------------------------------------------------------------------------->
      <q-tab-panel name="dca">
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t("console.dcaHelp") }}
        </div>
        <div class="row q-col-gutter-sm">
          <div
            v-for="n in dcaNumbers"
            :key="n"
            class="col-12 col-md-6"
          >
            <q-card
              v-if="dcaDraft[n]"
              flat
              bordered
              class="q-pa-sm"
              data-testid="console-dca"
            >
              <div class="row items-center q-gutter-sm no-wrap q-mb-sm">
                <q-badge
                  color="amber-9"
                  text-color="black"
                >
                  DCA {{ n }}
                </q-badge>
                <q-input
                  v-model="dcaDraft[n].name"
                  dense
                  outlined
                  class="col"
                  :label="t('console.dcaName')"
                  data-testid="console-dca-name"
                  @update:model-value="dcaSaver.schedule()"
                />
              </div>
              <StripPicker
                v-model="dcaDraft[n].members"
                :items="dcaItems"
                :label="t('console.dcaMembers')"
                :title="t('console.dcaPickTitle', { n })"
                data-testid="console-dca-members"
                @update:model-value="dcaSaver.flush()"
              />
              <div class="text-caption text-grey-6 q-mt-xs">
                {{ t("console.dcaCount", { n: dcaDraft[n].members.length }) }}
              </div>
            </q-card>
          </div>
        </div>
      </q-tab-panel>

      <!-- Built-in FX -------------------------------------------------------------------->
      <q-tab-panel name="fx">
        <div class="text-caption text-grey-6 q-mb-sm">
          {{ t("console.fxHelp") }}
        </div>
        <div class="row items-center q-gutter-sm q-mb-sm">
          <div data-testid="console-fx-count">
            {{ fxConfigured }}{{ summary?.fx_capacity ? ` / ${summary.fx_capacity}` : "" }}
            {{ t("console.fxSetUp") }}
          </div>
          <q-btn
            v-if="!fxBuiltIn"
            outline
            no-caps
            dense
            icon="add"
            :label="t('console.fxAdd')"
            data-testid="console-fx-add"
            @click="addFx"
          />
          <span
            v-else
            class="text-caption text-grey-6"
          >{{ t("console.fxBuiltInNote", { n: summary.fx_capacity }) }}</span>
        </div>
        <div
          v-if="!fxDraft.length"
          class="text-grey-6"
        >
          {{ t("console.fxNone") }}
        </div>
        <q-card
          v-for="(engine, i) in fxDraft"
          :key="engine.id"
          flat
          bordered
          class="q-pa-sm q-mb-sm"
          :class="{ 'fx-placeholder': !fxIsConfigured(engine) }"
          data-testid="console-fx"
        >
          <div class="row q-col-gutter-sm items-center">
            <div class="col-12 col-sm-4">
              <q-input
                v-model="engine.name"
                dense
                outlined
                :label="t('console.fxName')"
                data-testid="console-fx-name"
                @update:model-value="fxSaver.schedule()"
              />
            </div>
            <div class="col-6 col-sm-3">
              <q-select
                v-model="engine.type"
                :options="fxTypes"
                emit-value
                map-options
                dense
                outlined
                :label="t('console.fxType')"
                data-testid="console-fx-type"
                @update:model-value="fxSaver.flush()"
              />
            </div>
            <div class="col-6 col-sm-3">
              <q-toggle
                v-model="engine.stereo_return"
                :label="t('console.fxStereoReturn')"
                data-testid="console-fx-stereo"
                @update:model-value="fxSaver.flush()"
              />
            </div>
            <div
              v-if="summary?.budget?.enabled"
              class="col-6 col-sm-2"
            >
              <q-toggle
                :model-value="engine.send_mode === 'stereo'"
                :label="t('console.fxSendStereo')"
                data-testid="console-fx-send-stereo"
                @update:model-value="(v) => { engine.send_mode = v ? 'stereo' : 'mono'; fxSaver.flush(); }"
              />
            </div>
            <div class="col-12 col-sm-2 text-right">
              <q-chip
                v-if="!fxIsConfigured(engine)"
                dense
                square
                outline
                data-testid="console-fx-placeholder"
              >
                {{ t("console.fxBuiltInChip") }}
              </q-chip>
              <q-toggle
                v-if="fader?.enabled"
                :model-value="fxOnFaders(engine)"
                dense
                :label="t('console.fxOnFaders')"
                :data-testid="`console-fx-on-faders`"
                @update:model-value="(v) => setFxOnFaders(engine, v)"
              />
              <q-btn
                v-if="fxBuiltIn"
                flat
                dense
                no-caps
                icon="restart_alt"
                :label="t('console.fxReset')"
                :disable="!fxIsConfigured(engine)"
                data-testid="console-fx-reset"
                @click="resetFx(i)"
              />
              <q-btn
                v-else
                flat
                round
                dense
                color="negative"
                icon="delete"
                :aria-label="t('workspace.remove')"
                data-testid="console-fx-remove"
                @click="removeFx(i)"
              />
            </div>
          </div>
          <StripPicker
            v-model="engine.sends"
            :items="sendItems"
            class="q-mt-sm"
            :label="t('console.fxSends')"
            :title="t('console.fxPickTitle', { name: engine.name })"
            data-testid="console-fx-sends"
            @update:model-value="fxSaver.flush()"
          />
          <div class="text-caption text-grey-6 q-mt-xs">
            {{ t("console.fxSendCount", { n: engine.sends.length }) }}
          </div>
        </q-card>
      </q-tab-panel>
    </q-tab-panels>

    <!-- fader cell chooser -->
    <q-dialog
      v-model="cellOpen"
      :maximized="$q.screen.lt.sm"
    >
      <q-card style="min-width: 320px; max-width: 520px; width: 100%">
        <q-card-section class="text-h6">
          {{ t("console.faderCellTitle", { fader: cell?.fader }) }}
        </q-card-section>
        <q-card-section class="q-py-none">
          <q-input
            v-model="chooserQuery"
            dense
            outlined
            clearable
            :label="t('common.search')"
            data-testid="console-fader-chooser-search"
          />
        </q-card-section>
        <q-list
          separator
          style="max-height: 60vh; overflow: auto"
        >
          <q-item
            v-if="cell?.id"
            v-close-popup
            clickable
            data-testid="console-fader-remove"
            @click="removeCell()"
          >
            <q-item-section>{{ t("console.faderRemoveHere") }}</q-item-section>
          </q-item>
          <q-item
            v-if="cell?.id"
            v-close-popup
            clickable
            data-testid="console-fader-duplicate"
            @click="duplicateCell()"
          >
            <q-item-section>{{ t("console.faderDuplicate") }}</q-item-section>
          </q-item>
          <q-item
            v-close-popup
            clickable
            data-testid="console-fader-auto"
            @click="chooseCell(null)"
          >
            <q-item-section>{{ t("console.faderAuto") }}</q-item-section>
          </q-item>
          <q-item
            v-close-popup
            clickable
            data-testid="console-fader-empty"
            @click="chooseCell('empty')"
          >
            <q-item-section>{{ t("console.faderEmpty") }}</q-item-section>
          </q-item>
          <q-item
            v-for="st in chooserStrips"
            :key="st.id"
            v-close-popup
            clickable
            data-testid="console-fader-choice"
            @click="chooseCell(st.id)"
          >
            <q-item-section avatar>
              <q-icon
                :name="stripKindIcon(st.kind)"
                size="18px"
              />
            </q-item-section>
            <q-item-section>
              <q-item-label>
                <b>{{ st.number }}</b> {{ st.label }}<span v-if="st.stereo"> · ST</span>
              </q-item-label>
              <q-item-label
                v-if="stripWhere(st.id)"
                caption
              >
                {{ t("console.faderAlsoOn", { where: stripWhere(st.id) }) }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </q-dialog>

    <!-- auto patch: channels, in order, onto consecutive sockets of one port -->
    <q-dialog
      v-model="autoOpen"
      :maximized="$q.screen.lt.sm"
    >
      <q-card
        style="min-width: 320px; max-width: 640px; width: 100%"
        data-testid="console-auto-dialog"
      >
        <q-card-section class="text-h6">
          {{ t("console.autoPatch") }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="text-caption text-grey-6">
            {{ t("console.autoHelp") }}
          </div>
          <q-btn-toggle
            v-model="auto.field"
            no-caps
            dense
            unelevated
            toggle-color="primary"
            :options="autoTargets"
            data-testid="console-auto-target"
            @update:model-value="onAutoField"
          />
          <StripPicker
            v-model="auto.channels"
            :items="autoItems"
            :label="t('console.autoChannels')"
            :title="t('console.autoChannels')"
            data-testid="console-auto-channels"
            @update:model-value="auto.plan = null"
          />
          <q-select
            v-model="auto.port"
            :options="autoPortOptions"
            emit-value
            map-options
            dense
            outlined
            :label="t('console.autoPort')"
            data-testid="console-auto-port"
            @update:model-value="onAutoPort"
          />
          <div class="row q-col-gutter-sm items-center">
            <div class="col-6">
              <q-input
                v-model.number="auto.start"
                type="number"
                min="1"
                dense
                outlined
                :label="t('console.autoStart')"
                data-testid="console-auto-start"
                @update:model-value="auto.plan = null"
              />
            </div>
            <div class="col-6">
              <q-toggle
                v-model="auto.skip"
                :label="t('console.autoSkip')"
                @update:model-value="auto.plan = null"
              />
            </div>
            <div
              v-if="auto.field === 'out_socket'"
              class="col-12"
            >
              <q-toggle
                v-model="auto.append"
                :label="t('console.autoAppend')"
                data-testid="console-auto-append"
                @update:model-value="auto.plan = null"
              />
              <div class="text-caption text-grey-6">
                {{ t("console.busRunHint") }}
              </div>
            </div>
            <div
              v-if="auto.field === 'dsp_source'"
              class="col-12"
            >
              <q-toggle
                v-model="auto.shared"
                :label="t('console.autoShared')"
                data-testid="console-auto-shared"
                @update:model-value="auto.plan = null"
              />
            </div>
          </div>
          <q-banner
            v-if="auto.error"
            dense
            rounded
            class="bg-negative text-white"
            data-testid="console-auto-error"
          >
            {{ auto.error }}
          </q-banner>
          <div
            v-if="auto.plan"
            data-testid="console-auto-plan"
          >
            <div class="text-subtitle2">
              {{ t("console.autoPlan", { n: auto.plan.length }) }}
            </div>
            <q-list
              dense
              bordered
              separator
              style="max-height: 28vh; overflow: auto"
            >
              <q-item
                v-for="row in auto.plan"
                :key="row.channel_id || row.bus_id"
              >
                <q-item-section data-testid="console-auto-plan-row">
                  {{ planRowText(row, auto.field === "out_socket" ? t("console.mixShort") : "Ch") }}
                </q-item-section>
              </q-item>
            </q-list>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            no-caps
            :label="t('common.cancel')"
          />
          <q-btn
            outline
            no-caps
            icon="visibility"
            :label="t('console.autoPreview')"
            :disable="!auto.channels.length || !auto.port"
            data-testid="console-auto-preview"
            @click="runAuto(true)"
          />
          <q-btn
            color="primary"
            no-caps
            icon="check"
            :label="t('console.autoApply')"
            :disable="!auto.channels.length || !auto.port"
            data-testid="console-auto-apply"
            @click="runAuto(false)"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- bulk clear -->
    <q-dialog
      v-model="bulkOpen"
      :maximized="$q.screen.lt.sm"
    >
      <q-card
        style="min-width: 320px; max-width: 640px; width: 100%"
        data-testid="console-bulk-dialog"
      >
        <q-card-section class="text-h6">
          {{ t("console.bulkClear") }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div class="text-caption text-grey-6">
            {{ t("console.bulkHelp") }}
          </div>
          <StripPicker
            v-model="bulkIds"
            :items="patchedItems"
            :label="t('console.autoChannels')"
            :title="t('console.bulkClear')"
            data-testid="console-bulk-channels"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            no-caps
            :label="t('common.cancel')"
          />
          <q-btn
            color="negative"
            no-caps
            icon="link_off"
            :label="t('console.bulkApply', { n: bulkIds.length })"
            :disable="!bulkIds.length"
            data-testid="console-bulk-apply"
            @click="runBulkClear"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- manual profile -->
    <q-dialog
      v-model="manualOpen"
      :maximized="$q.screen.lt.sm"
    >
      <q-card style="min-width: 320px; max-width: 640px; width: 100%">
        <q-card-section class="text-h6">
          {{ t("console.manual") }}
        </q-card-section>
        <q-card-section
          class="q-gutter-sm"
          data-testid="console-manual-form"
        >
          <q-input
            v-model="form.name"
            dense
            outlined
            :label="t('console.consoleName')"
          />
          <div class="row q-col-gutter-sm">
            <div class="col-6">
              <q-input
                v-model.number="form.total_slots"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.totalSlots')"
                :hint="t('console.totalSlotsHint')"
                data-testid="console-form-slots"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.max_mixes"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.maxMixes')"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.stereo_slot_cost"
                type="number"
                min="1"
                dense
                outlined
                :label="t('console.stereoCost')"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.lcr_slot_cost"
                type="number"
                min="1"
                dense
                outlined
                :label="t('console.lcrCost')"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.mono"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.monoInputs')"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.dcas"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.dcas')"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.fx_returns"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.fxReturns')"
                :hint="t('console.fxReturnsHint')"
                data-testid="console-form-fx"
              />
            </div>
            <div class="col-6">
              <q-input
                v-model.number="form.layers"
                type="number"
                min="1"
                dense
                outlined
                :label="t('console.layers')"
              />
            </div>
          </div>
          <q-toggle
            v-model="form.odd_even"
            :label="t('console.oddEven')"
          />
          <q-toggle
            v-model="form.adjacent"
            :label="t('console.adjacentPairing')"
          />
          <div class="text-subtitle2">
            {{ t("console.banks") }}
          </div>
          <div
            v-for="(b, i) in form.banks"
            :key="i"
            class="row q-col-gutter-sm items-center"
          >
            <div class="col-3">
              <q-input
                v-model="b.id"
                dense
                outlined
                label="ID"
              />
            </div>
            <div class="col-5">
              <q-input
                v-model="b.label"
                dense
                outlined
                :label="t('console.bankLabel')"
              />
            </div>
            <div class="col-3">
              <q-input
                v-model.number="b.faders"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.faders')"
              />
            </div>
            <div class="col-1">
              <q-btn
                flat
                dense
                round
                icon="close"
                :aria-label="t('workspace.remove')"
                @click="form.banks.splice(i, 1)"
              />
            </div>
          </div>
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('console.addBank')"
            @click="form.banks.push({ id: String.fromCharCode(65 + form.banks.length), label: '', faders: 12 })"
          />
          <div class="text-subtitle2 q-mt-sm">
            {{ t("console.expansionPorts") }}
          </div>
          <div class="text-caption text-grey-6">
            {{ t("console.expansionPortsHint") }}
          </div>
          <div
            v-for="(x, i) in form.expansion"
            :key="i"
            class="row q-col-gutter-sm items-center"
            data-testid="console-form-expansion"
          >
            <div class="col-12 col-sm-3">
              <q-input
                v-model="x.protocol"
                dense
                outlined
                :label="t('console.protocol')"
                placeholder="dante"
                data-testid="console-form-exp-protocol"
              />
            </div>
            <div class="col-3 col-sm-2">
              <q-input
                v-model.number="x.slots"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.slotsShort')"
              />
            </div>
            <div class="col-3 col-sm-2">
              <q-input
                v-model.number="x.max_channels"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.maxTotal')"
                data-testid="console-form-exp-max"
              />
            </div>
            <div class="col-3 col-sm-2">
              <q-input
                v-model.number="x.max_channels_in"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.maxIn')"
              />
            </div>
            <div class="col-3 col-sm-2">
              <q-input
                v-model.number="x.max_channels_out"
                type="number"
                min="0"
                dense
                outlined
                :label="t('console.maxOut')"
              />
            </div>
            <div class="col-auto">
              <q-btn
                flat
                dense
                round
                icon="close"
                :aria-label="t('workspace.remove')"
                @click="form.expansion.splice(i, 1)"
              />
            </div>
          </div>
          <q-btn
            flat
            no-caps
            icon="add"
            :label="t('console.addExpansionPort')"
            data-testid="console-form-exp-add"
            @click="form.expansion.push({ protocol: '', slots: 1, max_channels: null, max_channels_in: null, max_channels_out: null })"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            no-caps
            :label="t('common.cancel')"
          />
          <q-btn
            color="primary"
            no-caps
            :label="t('console.save')"
            data-testid="console-form-save"
            @click="saveManual"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-card>
</template>

<script setup>
// The digital-console tools of one channel list: profile (preset / Stockwire / manual), bus-pool
// budget, stereo links, soft patch + direct outs and the fader map. It talks to the audio console
// API (/jobs/:id/channel-lists/:listId/...), never the generic graph routes, because that API is
// what enforces the bus budget and the pairing rules. After every write it emits `changed` so the
// editor can refresh the graph it shows. Jobs only (venues have no console routes).
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useQuasar } from "quasar";
import { api } from "@/boot/api";
import { apiErrorText } from "@/utils/errors";
import StripPicker from "@/components/StripPicker.vue";
import { combineStatus, createAutosaver } from "@/utils/autosave";
import {
  applyFaderChoice,
  autoPatchBody,
  bulkClearBody,
  deselectIds,
  expansionFormRows,
  expansionFromForm,
  expansionLimit,
  expansionPayload,
  fieldOfMode,
  busRunAt,
  busWidth,
  endpointLabel,
  endpointShortages,
  endpointSides,
  numberedLabel,
  planRowText,
  sharedChannelsText,
  faderDraftFromMap,
  unplacedStrips,
  filterStripItems,
  firstFreeSocket,
  fxConfiguredCount,
  fxIsConfigured,
  fxResetEngine,
  groupPortsByDevice,
  idsInRanges,
  invertIds,
  moveFaderStrip,
  stereoPairTiles,
  stripStereoSuffix,
  tilesInRange,
  removeFaderPlacement,
  stripPlacements,
  orderByNumber,
  pageOf,
  portSockets,
  portSocketsOut,
  softFieldInfo,
  selectIds,
  stripKindIcon,
  toggleRowSelection,
  unpinFaderStrip,
} from "@/utils/workspace";

const props = defineProps({
  jobId: { type: String, required: true },
  listId: { type: String, required: true },
  // Changes whenever the list's outputs or channels change in the graph store (any editor, any
  // tab): the panel then re-reads its summary and maps, so a bus mode changed on the Inputs page
  // shows here without a reload and the other way round.
  refreshKey: { type: String, default: "" },
});
const emit = defineEmits(["changed"]);
const { t } = useI18n();
const $q = useQuasar();

const tab = ref("profile");
const summary = ref(null);
const listData = ref(null);
const presets = ref([]);
const presetKey = ref(null);
const soft = ref(null);
const fader = ref(null);
const layerNo = ref(1);
// Fader layout editing: a local draft ({slot: stripId | 'empty'}) until saved.
const editingFaders = ref(false);
const draft = ref({});
const cellOpen = ref(false);
const cell = ref(null);
const overSlot = ref(null);
const overTray = ref(false);
const dragFrom = ref(null);
// DCA and FX drafts: edited locally and saved by their autosaver; the server summary only replaces
// them while no edit is pending (so typing is never overwritten).
const dcaDraft = ref({});
const fxDraft = ref([]);
const accessoryRows = ref([]);
const accLoaded = ref(false);
const manualOpen = ref(false);
// fader tray / chooser filters
const trayQuery = ref("");
const trayKindsOn = ref([]);
const chooserQuery = ref("");
// soft patch (port-centred)
const patchMode = ref("in");
const selPortKey = ref(null);
const selChannelId = ref(null);
const gridPage = ref(1);
const quickOpen = ref(false);
const channelFilter = ref("");
const autoOpen = ref(false);
const auto = reactive({ field: "dsp_source", channels: [], port: null, start: 1, skip: true, append: false, shared: false, plan: null, error: "" });
const bulkOpen = ref(false);
const bulkIds = ref([]);
const overviewQuery = ref("");
const rangeText = ref("");
const selIds = ref([]);
let selAnchor = null;
// expansion cards: the saved ones from the server and the editable draft
const expansion = ref({ available: [], installed: [] });
const expCards = ref([]);
let cardKey = 0;
const newBus = reactive({ name: "", mode: "mono", role: "aux" });

// --- autosave ---------------------------------------------------------------------------------
// Nothing in this panel has a Save button: each editable resource has a saver that persists the
// latest draft (debounced for typing, at once for toggles / pickers / drops), one request at a time
// per resource. `saveStatus` is the single indicator in the header.
const saverStates = reactive({});
function makeSaver(name, save, delay = 600) {
  saverStates[name] = { dirty: false, saving: false, error: null, everSaved: false };
  return createAutosaver(save, { delay, onStatus: (st) => Object.assign(saverStates[name], st) });
}
const dcaSaver = makeSaver("dca", persistDcas);
const fxSaver = makeSaver("fx", persistFx, 400);
const accSaver = makeSaver("acc", persistAccessories);
const expSaver = makeSaver("exp", persistExpansion);
const faderSaver = makeSaver("fader", persistFader, 0);
const dcaDirty = computed(() => !!saverStates.dca?.dirty);
const fxDirty = computed(() => !!saverStates.fx?.dirty);
const accDirty = computed(() => !!saverStates.acc?.dirty);
const expDirty = computed(() => !!saverStates.exp?.dirty);
const saveStatus = computed(() => combineStatus(saverStates));
const savers = [dcaSaver, fxSaver, accSaver, expSaver, faderSaver];
const settleAll = () => Promise.all(savers.map((x) => x.settle()));
const retrySaves = () => savers.filter((x) => x.state.error).forEach((x) => x.retry());
// a 4xx is the server refusing the draft (a rule, not an outage): show why, then fall back to the
// server's state so the screen never keeps a value that was not accepted
const isRefusal = (err) => err?.response?.status >= 400 && err?.response?.status < 500;

const lb = computed(() => `/jobs/${props.jobId}/channel-lists/${props.listId}`);
const simple = computed(() => !summary.value || summary.value.simple);
const budget = computed(() => summary.value?.budget);
const buses = computed(() => (listData.value?.outputs || []).map((o) => ({ ...o, mode: o.mode || "mono", role: o.role || "aux" })));
const roles = computed(() => summary.value?.profile?.bus_pool?.allowed_roles || ["aux", "group", "matrix", "main", "fx_send"]);
const busModes = computed(() => ["mono", "stereo", "lcr"].map((m) => ({ value: m, label: t(`console.busMode.${m}`) })));
// A linked pair is ONE ganged strip: the secondary is hidden everywhere in this panel.
const strips = computed(() =>
  (listData.value?.channels || []).filter((c) => c.stereo_link_role !== "secondary").sort((a, b) => a.channel_number - b.channel_number),
);
const softStrips = computed(() => {
  const byId = new Map((soft.value?.channels || []).map((c) => [c.id, c]));
  // every channel, including the second leg of a stereo pair: each leg is its own preamp and is
  // patched on its own (to any socket, on any stagebox)
  return [...(listData.value?.channels || [])]
    .sort((a, b) => a.channel_number - b.channel_number)
    .map((c) => ({ ...c, ...(byId.get(c.id) || {}) }));
});
// Every strip of the console. The API lists them in `strips`; if that is ever absent the cells of
// the map are the fallback, so the tray and the chooser can never silently omit a kind (inputs, FX
// returns, mixes, FX sends and DCAs all show).
const allStrips = computed(() => {
  const listed = fader.value?.strips;
  if (listed?.length) return listed;
  const seen = new Map();
  for (const layer of fader.value?.layers || [])
    for (const bank of layer.banks) for (const c of bank.strips) if (c.id && !seen.has(c.id)) seen.set(c.id, c);
  return [...seen.values()];
});
const trayKinds = computed(() => {
  const counts = new Map();
  for (const st of allStrips.value) counts.set(st.kind, (counts.get(st.kind) || 0) + 1);
  return [...counts.entries()].map(([kind, n]) => ({ kind, n }));
});
const trayStrips = computed(() => {
  const found = filterStripItems(allStrips.value, { query: trayQuery.value || "", kinds: trayKindsOn.value });
  return trayUnplacedOnly.value ? found.filter((st) => !trayPlacements(st.id)) : found;
});
const chooserStrips = computed(() => filterStripItems(allStrips.value, { query: chooserQuery.value || "" }));
function toggleTrayKind(k) {
  trayKindsOn.value = trayKindsOn.value.includes(k) ? trayKindsOn.value.filter((x) => x !== k) : [...trayKindsOn.value, k];
}
const baseLayer = computed(() => fader.value?.layers?.find((l) => l.layer === layerNo.value) || fader.value?.layers?.[0]);
// While editing, the grid shows the draft: it is the whole layout (started from the map as it was
// when editing began), so a fader that is not in the draft is blank.
const currentLayer = computed(() => {
  const layer = baseLayer.value;
  if (!layer || !editingFaders.value) return layer;
  const byId = new Map(allStrips.value.map((x) => [x.id, x]));
  return {
    ...layer,
    banks: layer.banks.map((b) => ({
      ...b,
      strips: b.strips.map((c) => {
        const v = draft.value[c.slot];
        const st = !v || v === "empty" ? null : byId.get(v);
        return { ...c, ...(st || { id: null, kind: "empty", label: "", number: "", stereo: false }) };
      }),
    })),
  };
});
const profileFacts = computed(() => {
  const p = summary.value?.profile;
  if (!p) return "";
  const pool = p.bus_pool;
  return [
    p.dsp_inputs?.mono ? `${p.dsp_inputs.mono} ${t("console.monoShort")}` : "",
    pool ? `${pool.total_slots} ${t("console.slots")}` : "",
    p.dcas ? `${p.dcas} DCA` : "",
    p.surface?.banks?.length ? `${p.surface.banks.length} ${t("console.banks").toLowerCase()} × ${p.surface.layers} ${t("console.layers").toLowerCase()}` : "",
  ].filter(Boolean).join(" · ");
});

const stripNumber = (ch) => (ch.is_stereo_linked ? `Ch ${ch.channel_number}-${ch.channel_number + 1}` : `Ch ${ch.channel_number}`);
const slotLabel = (bus) => {
  const e = budget.value?.entries?.find((x) => x.id === bus.id);
  return e ? `${t("console.slots")} ${e.slot_start}${e.slot_end > e.slot_start ? `–${e.slot_end}` : ""}` : "";
};

function failed(err) {
  $q.notify({ type: "negative", message: apiErrorText(err, t("console.failed")) });
}
// Every action that is sent at once (no Save button) confirms the same way.
const applied = () => $q.notify({ type: "positive", message: t("console.applied"), timeout: 1200 });

async function load() {
  try {
    const [s, lists] = await Promise.all([api.get(`${lb.value}/console`), api.get(`/jobs/${props.jobId}/channel-lists`)]);
    summary.value = s.data;
    listData.value = lists.data.find((l) => l.id === props.listId) || null;
    if (!simple.value) {
      fader.value = (await api.get(`${lb.value}/fader-map`)).data;
    } else {
      fader.value = null;
      if (["faders", "dca", "fx"].includes(tab.value)) tab.value = "profile";
    }
    if (tab.value === "dca" && !summary.value.dca_count) tab.value = "profile";
    soft.value = (await api.get(`${lb.value}/soft-patch`)).data;
    await loadExpansion();
  } catch (err) {
    failed(err);
  }
}

async function changed() {
  await load();
  emit("changed");
}

onMounted(async () => {
  try {
    presets.value = (await api.get(`/jobs/${props.jobId}/console-presets`)).data;
  } catch {
    presets.value = [];
  }
  await load();
});
watch(() => props.listId, () => { accLoaded.value = false; accessoryRows.value = []; load(); });
// Debounced, and not while a layout is being edited (a reload would not touch the draft, but the
// grid underneath should not jump around while the user drags).
let refreshTimer = null;
watch(() => props.refreshKey, () => {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => { if (!editingFaders.value || tab.value !== "faders") load(); }, 300);
});

// --- profile ---------------------------------------------------------------------------------
async function setProfile(body) {
  try {
    await api.put(`${lb.value}/console-profile`, body);
    applied();
    await changed();
  } catch (err) {
    failed(err);
  }
}

const form = reactive({ name: "", total_slots: null, max_mixes: null, stereo_slot_cost: 2, lcr_slot_cost: 3, mono: 0, fx_returns: 0, dcas: 0, layers: 1, odd_even: false, adjacent: false, banks: [], expansion: [] });
function openManual() {
  const p = summary.value?.profile;
  Object.assign(form, {
    name: p?.name || "",
    total_slots: p?.bus_pool?.total_slots ?? null,
    max_mixes: p?.bus_pool?.max_mixes ?? null,
    stereo_slot_cost: p?.bus_pool?.stereo_slot_cost ?? 2,
    lcr_slot_cost: p?.bus_pool?.lcr_slot_cost ?? 3,
    mono: p?.dsp_inputs?.mono ?? 0,
    fx_returns: p?.dsp_inputs?.fx_returns ?? 0,
    dcas: p?.dcas ?? 0,
    layers: p?.surface?.layers ?? 1,
    odd_even: !!p?.bus_pool?.odd_even_stereo_pairing,
    adjacent: p?.input_pairing === "adjacent",
    banks: (p?.surface?.banks || []).map((b) => ({ ...b })),
    expansion: expansionFormRows(p?.expansion_ports),
  });
  manualOpen.value = true;
}
const num = (v) => (v === "" || v == null || Number.isNaN(Number(v)) ? null : Number(v));
async function saveManual() {
  const hasPool = num(form.total_slots) != null;
  const previous = summary.value?.profile;
  const profile = {
    architecture: hasPool ? "digital_bus_pool" : "simple",
    name: form.name || null,
    // keep what the form has no field for (stereo inputs) instead of resetting it
    dsp_inputs: { ...(previous?.dsp_inputs || {}), mono: num(form.mono) || 0, fx_returns: num(form.fx_returns) || 0 },
    expansion_ports: expansionFromForm(form.expansion),
    dcas: num(form.dcas) || 0,
    input_pairing: form.adjacent ? "adjacent" : "odd_even",
    bus_pool: hasPool
      ? {
          total_slots: num(form.total_slots),
          max_mixes: num(form.max_mixes),
          stereo_slot_cost: num(form.stereo_slot_cost) || 2,
          lcr_slot_cost: num(form.lcr_slot_cost) || 3,
          odd_even_stereo_pairing: form.odd_even,
        }
      : null,
    surface: form.banks.length ? { banks: form.banks.map((b) => ({ id: String(b.id), label: b.label || "", faders: num(b.faders) || 0 })), layers: num(form.layers) || 1 } : null,
  };
  manualOpen.value = false;
  await setProfile({ profile });
}

// --- accessories -----------------------------------------------------------------------------
async function loadAccessories() {
  try {
    const { data } = await api.get(`${lb.value}/accessories`);
    const bundled = new Map((data.bundled || []).map((b) => [b.product_id, b]));
    accessoryRows.value = data.suggestions.map((s) => ({ ...s, picked: bundled.has(s.product_id) || s.bundled, quantity: bundled.get(s.product_id)?.quantity || s.quantity }));
    accLoaded.value = true;
  } catch (err) {
    failed(err);
  }
}
async function persistAccessories() {
  try {
    await api.put(
      `${lb.value}/accessories`,
      accessoryRows.value.filter((r) => r.picked).map((r) => ({ product_id: r.product_id, name: r.name, quantity: Math.max(1, Number(r.quantity) || 1) })),
    );
    emit("changed");
    return true;
  } catch (err) {
    failed(err);
    if (!isRefusal(err)) return false;
    accSaver.reset();
    await loadAccessories();
    return true;
  }
}

// --- buses -----------------------------------------------------------------------------------
// A 409 with a budget means the write would overflow the pool: offer "Add anyway", which repeats
// the same request with ?force=true. Any other error is just shown.
async function withForce(send) {
  try {
    await send({});
    applied();
    await changed();
  } catch (err) {
    if (err?.response?.status === 409 && err.response.data?.detail?.budget) {
      $q.dialog({
        title: t("console.overBudget"),
        message: err.response.data.detail.message,
        ok: { label: t("console.addAnyway"), color: "warning", "data-testid": "console-add-anyway", noCaps: true },
        cancel: { label: t("common.cancel"), flat: true, noCaps: true },
        persistent: true,
      }).onOk(async () => {
        try {
          await send({ force: true });
          applied();
          await changed();
        } catch (e2) {
          failed(e2);
        }
      });
      await load();
    } else {
      failed(err);
      await load();
    }
  }
}
const addBus = () =>
  withForce((params) =>
    api.post(`${lb.value}/outputs`, { name: newBus.name || `${t("workspace.output")} ${buses.value.length + 1}`, mode: newBus.mode, role: newBus.role }, { params }),
  ).then(() => { newBus.name = ""; });
const updateBus = (bus, changes) =>
  withForce((params) => api.patch(`${lb.value}/outputs/${bus.id}`, { ...changes, expected_revision: bus.revision }, { params }));
async function removeBus(bus) {
  try {
    await api.delete(`${lb.value}/outputs/${bus.id}`, { params: { expected_revision: bus.revision } });
    await changed();
  } catch (err) {
    failed(err);
  }
}

// --- DCAs and FX -----------------------------------------------------------------------------
const dcaNumbers = computed(() => Array.from({ length: summary.value?.dca_count || 0 }, (_, i) => i + 1));
function dcaFrom(s) {
  const out = {};
  for (let n = 1; n <= (s.dca_count || 0); n += 1) {
    const d = s.dcas?.[String(n)] || {};
    out[n] = { name: d.name || "", members: [...(d.members || [])] };
  }
  return out;
}
const fxFrom = (s) => (s?.fx || []).map((e) => ({ ...e, sends: [...(e.sends || [])] }));
watch(summary, (s) => {
  if (!s) return;
  if (!dcaDirty.value) dcaDraft.value = dcaFrom(s);
  if (!fxDirty.value) fxDraft.value = fxFrom(s);
});
// What a DCA can hold: input strips (a linked pair is its primary), FX returns, mixes and FX sends,
// in the same order as the fader map. Built from the local drafts so a new engine is pickable
// before it is saved; saveDcas then saves the FX first so the DCA never names an engine the server
// does not know yet.
const inputItems = computed(() =>
  strips.value.map((c) => ({
    id: c.id,
    kind: "input",
    label: c.source_label || "",
    number: c.is_stereo_linked ? `${c.channel_number}-${c.channel_number + 1}` : String(c.channel_number),
    stereo: !!c.is_stereo_linked,
    group: c.instrument_group,
  })),
);
const dcaItems = computed(() => [
  ...inputItems.value,
  ...fxDraft.value.map((e) => ({ id: `fx-${e.id}`, kind: "fx", label: e.name || e.id, number: "FX", stereo: !!e.stereo_return })),
  ...buses.value.map((b) => ({ id: b.id, kind: "mix", label: b.name, number: b.role || "aux", stereo: b.mode !== "mono" })),
  ...fxDraft.value.map((e) => ({ id: `fxs-${e.id}`, kind: "fxsend", label: `${e.name || e.id} send`, number: "FX send" })),
]);
// FX sends come from input channels only.
const sendItems = inputItems;
async function persistDcas() {
  // A DCA may hold an engine that only exists in the FX draft: let any FX save finish (or run) first
  // so the DCA never names an engine the server does not know yet.
  if (fxDirty.value) await fxSaver.flush();
  const dcas = {};
  for (const n of dcaNumbers.value) {
    const d = dcaDraft.value[n];
    if (d && (d.name.trim() || d.members.length)) dcas[n] = { name: d.name.trim(), members: d.members };
  }
  try {
    const { data } = await api.put(`${lb.value}/dcas`, { dcas });
    summary.value = data;
    await changed();
    return true;
  } catch (err) {
    failed(err);
    if (!isRefusal(err)) return false;
    dcaSaver.reset();
    await load();
    dcaDraft.value = dcaFrom(summary.value || {});
    return true;
  }
}

const fxTypes = computed(() => ["reverb", "delay", "chorus", "other"].map((v) => ({ value: v, label: t(`console.fxTypes.${v}`) })));
// A console that states its FX count has that many built-in engines (they always exist; an engine
// that has not been set up is a placeholder). Only a console without a fixed count adds / deletes.
const fxBuiltIn = computed(() => !!summary.value?.fx_capacity);
const fxConfigured = computed(() => fxConfiguredCount(fxDraft.value));
function resetFx(i) {
  fxDraft.value = fxDraft.value.map((e, j) => (j === i ? fxResetEngine(e, i + 1) : e));
  fxSaver.flush();
}
function addFx() {
  const used = new Set(fxDraft.value.map((e) => e.id));
  let n = 1;
  while (used.has(`fx${n}`)) n += 1;
  fxDraft.value = [...fxDraft.value, { id: `fx${n}`, name: `FX ${fxDraft.value.length + 1}`, type: "reverb", stereo_return: true, send_mode: "mono", sends: [] }];
  fxSaver.flush();
}
function removeFx(i) {
  const gone = fxDraft.value[i];
  fxDraft.value = fxDraft.value.filter((_, j) => j !== i);
  fxSaver.flush();
  if (!gone) return;
  // the engine's return and send leave every DCA draft too (the server prunes them on save as well)
  const dead = new Set([`fx-${gone.id}`, `fxs-${gone.id}`]);
  for (const n of Object.keys(dcaDraft.value)) {
    const d = dcaDraft.value[n];
    if (d.members.some((m) => dead.has(m))) {
      d.members = d.members.filter((m) => !dead.has(m));
      dcaSaver.flush();
    }
  }
}
// Persist the FX draft. A 409 from the bus-pool budget (the engines' sends do not fit) asks whether
// to save anyway and retries with force; declining puts the server's FX back. Resolves true when the
// draft is stored or was refused (and the screen re-synced), false on an outage (Retry resends).
async function persistFx() {
  for (const force of [false, true]) {
    try {
      const { data } = await api.put(`${lb.value}/fx`, { fx: fxDraft.value }, { params: force ? { force: true } : {} });
      summary.value = data;
      await changed();
      return true;
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (!force && err?.response?.status === 409 && detail?.budget) {
        const ok = await new Promise((resolve) =>
          $q.dialog({ title: t("console.fxBudgetTitle"), message: detail.message, cancel: true, persistent: true })
            .onOk(() => resolve(true))
            .onCancel(() => resolve(false))
            .onDismiss(() => resolve(false)),
        );
        if (ok) continue;
        fxSaver.reset();
        await load();
        fxDraft.value = fxFrom(summary.value);
        return true;
      }
      failed(err);
      if (!isRefusal(err)) return false;
      fxSaver.reset();
      await load();
      fxDraft.value = fxFrom(summary.value);
      return true;
    }
  }
  return false;
}

// --- fader layout ----------------------------------------------------------------------------
// Drag and drop on top of the tap-to-choose dialog (which stays the touch and keyboard path).
function onDragStart(ev, from) {
  dragFrom.value = from;
  // a tray strip is ADDED to the faders, a fader's strip MOVES; Alt/Option or Ctrl/Cmd copies it
  ev.dataTransfer.effectAllowed = "copyMove";
  ev.dataTransfer.setData("text/plain", JSON.stringify(from));
}
function onDragEnd() {
  dragFrom.value = null;
  overSlot.value = null;
  overTray.value = false;
}
// every drop / choice is saved at once: the draft is the layout we have sent or are sending
function commitLayout(next) {
  draft.value = next;
  faderSaver.flush();
}
function onDropCell(slot, ev) {
  const copy = !!(ev && (ev.altKey || ev.ctrlKey || ev.metaKey));
  if (dragFrom.value) commitLayout(moveFaderStrip(draft.value, fader.value, dragFrom.value, slot, { copy }));
  onDragEnd();
}
function onDropTray() {
  if (dragFrom.value) commitLayout(unpinFaderStrip(draft.value, fader.value, dragFrom.value));
  onDragEnd();
}
// on at least one fader, or unplaced (waiting in the tray)
function stripState(id) {
  return trayPlacements(id) ? "placed" : "unplaced";
}
// how many faders a strip sits on (tray chip "placed ×N", cell badge "×N"): the draft's view while
// editing, the saved map's own otherwise.
const trayPlacements = (id) => stripPlacements(editingFaders.value ? draft.value : null, fader.value, id).length;
const placementCount = (cell) => (editingFaders.value ? trayPlacements(cell.id) : cell.duplicate ? fader.value?.strips?.find((x) => x.id === cell.id)?.placements || 2 : 1);
function startFaderEdit() {
  draft.value = faderDraftFromMap(fader.value);
  editingFaders.value = true;
}
// A cell shows a pin once the layout is the engineer's: a stored layout, or while taking over.
const draftPinned = (s) => (editingFaders.value ? !!draft.value[s.slot] : s.pinned);
// Where a strip already sits ("Layer 2 · Left Bank · 5, Layer 3 · …"), for the chooser's caption;
// the fader being edited is left out. Choosing it adds one more placement, nothing moves.
function stripWhere(id) {
  return stripPlacements(draft.value, fader.value, id)
    .filter((p) => p.slot !== cell.value?.slot)
    .map((p) => `${t("console.layer", { n: p.layer })} · ${p.bank} · ${p.fader}`)
    .join(", ");
}
function openCell(s) {
  chooserQuery.value = "";
  cell.value = s;
  cellOpen.value = true;
}
function chooseCell(choice) {
  commitLayout(applyFaderChoice(draft.value, cell.value.slot, choice, fader.value));
}
// "Remove from this fader": just this placement; the strip's other faders stay
function removeCell() {
  commitLayout(removeFaderPlacement(draft.value, fader.value, cell.value.slot));
}
// "Duplicate to next free fader": the server picks the fader (everything already placed stays)
async function duplicateCell() {
  const id = cell.value?.id;
  if (!id) return;
  try {
    await faderSaver.flush(); // pending drops first, so the server adds to the layout we see
    const { data } = await api.post(`${lb.value}/fader-layout/add`, { strip_ids: [id], duplicate: true });
    fader.value = data;
    draft.value = faderDraftFromMap(data);
    applied();
    emit("changed");
  } catch (err) {
    failed(err);
  }
}
async function persistFader() {
  try {
    const { data } = await api.put(`${lb.value}/fader-layout`, { layout: draft.value });
    fader.value = data;
    return true;
  } catch (err) {
    failed(err);
    if (!isRefusal(err)) return false;
    faderSaver.reset();
    await load();
    draft.value = faderDraftFromMap(fader.value);
    return true;
  }
}
// "Auto fill (start over)": store the default fill (from the top) as the layout, so from then on it
// is the engineer's. It replaces a stored layout, so that asks first; the live starting point has
// nothing to lose.
function autoFillFaders() {
  const run = async () => {
    try {
      await faderSaver.flush();
      const { data } = await api.post(`${lb.value}/fader-layout/autofill`, { mode: "all" });
      fader.value = data;
      if (editingFaders.value) draft.value = faderDraftFromMap(data);
      applied();
      emit("changed");
    } catch (err) {
      failed(err);
    }
  };
  if (!fader.value?.custom) return run();
  return $q.dialog({ title: t("console.faderAutoFillTitle"), message: t("console.faderAutoFillConfirm"), cancel: true }).onOk(run);
}
// "Place unplaced strips": everything already placed stays; each unplaced strip goes on the next
// free fader (the server says so when the surface is full)
async function placeUnplaced() {
  try {
    await faderSaver.flush();
    const { data } = await api.post(`${lb.value}/fader-layout/autofill`, { mode: "missing" });
    fader.value = data;
    if (editingFaders.value) draft.value = faderDraftFromMap(data);
    applied();
    emit("changed");
  } catch (err) {
    failed(err);
  }
}
// strips on no fader: from the draft while editing, else the saved map; shown as a warning chip
const unplacedCount = computed(() => (fader.value?.custom ? unplacedStrips(editingFaders.value ? draft.value : null, fader.value).length : 0));
const trayUnplacedOnly = ref(false);
function showUnplaced() {
  trayUnplacedOnly.value = true;
  if (!editingFaders.value) startFaderEdit();
}

// --- hidden built-in FX ----------------------------------------------------------------------------
// Built-in engines nobody has set up are `hidden` in the map's strip list and are not placed by
// default. They are offered here and added to the first free faders with one tap.
const placedIds = computed(() => {
  const ids = new Set();
  for (const layer of fader.value?.layers || []) for (const bank of layer.banks) for (const c of bank.strips) if (c.id) ids.add(c.id);
  return ids;
});
const hiddenFx = computed(() => allStrips.value.filter((x) => x.hidden && (x.kind === "fx" || x.kind === "fxsend") && !placedIds.value.has(x.id)));
async function addToFaders(ids) {
  if (!ids.length) return;
  try {
    const { data } = await api.post(`${lb.value}/fader-layout/add`, { strip_ids: ids });
    fader.value = data;
    if (editingFaders.value) draft.value = faderDraftFromMap(data);
    applied();
    emit("changed");
  } catch (err) {
    failed(err);
  }
}
const fxStripIds = (engine) => [`fx-${engine.id}`, `fxs-${engine.id}`];
const fxOnFaders = (engine) => fxStripIds(engine).every((id) => placedIds.value.has(id));
// on = add its return and send to the faders; off = take them off (the whole current map is stored
// without them, so they stay off until added again or the faders are auto filled)
async function setFxOnFaders(engine, on) {
  const ids = fxStripIds(engine);
  if (on) return addToFaders(ids.filter((id) => !placedIds.value.has(id)));
  const layout = Object.fromEntries(Object.entries(faderDraftFromMap(fader.value)).filter(([, v]) => !ids.includes(v)));
  try {
    const { data } = await api.put(`${lb.value}/fader-layout`, { layout });
    fader.value = data;
    if (editingFaders.value) draft.value = faderDraftFromMap(data);
  } catch (err) {
    failed(err);
  }
  return null;
}

// --- links -----------------------------------------------------------------------------------
// Pair tiles over ALL the list's channels (the strips list hides secondaries). Linking from here and
// from the Inputs page's Stereo toggle use the same endpoints, so both views agree.
const pairRange = ref("");
const pairBusy = ref(false);
const pairTiles = computed(() =>
  stereoPairTiles(listData.value?.channels || [], summary.value?.profile, listData.value?.mixer_inputs),
);
// Link one pair: create the channels that do not exist yet, name the primary "<base> L" (the server
// derives the secondary's " R"), then link. Same steps as the Inputs page toggle.
async function linkOne(tile) {
  let a = tile.a;
  let b = tile.b;
  const make = async (n, label) => (await api.post(`${lb.value}/channels`, { channel_number: n, source_label: label })).data;
  const base = stripStereoSuffix(a?.source_label) || `Ch ${tile.low}`;
  const primaryName = `${base} L`;
  if (!a) a = await make(tile.low, primaryName);
  else if (a.source_label !== primaryName) {
    a = (await api.patch(`/jobs/${props.jobId}/channels/${a.id}`, { source_label: primaryName, expected_revision: a.revision })).data;
  }
  if (!b) b = await make(tile.high, `${base} R`);
  await api.post(`${lb.value}/console/link`, { primary_channel_id: a.id, secondary_channel_id: b.id });
}
async function onTile(tile) {
  if (pairBusy.value || tile.state === "blocked") return;
  if (tile.state === "linked") {
    $q.dialog({ title: t("console.unlink"), message: t("console.unlinkConfirm", { pair: tile.label }), cancel: true }).onOk(() => unlinkTiles([tile]));
    return;
  }
  await linkTiles([tile]);
}
// Several pairs one after another; the 409 messages of the ones that fail are gathered into ONE
// notification so a long range does not spam, and the pairs that worked stay linked.
async function linkTiles(tiles) {
  pairBusy.value = true;
  const failedPairs = [];
  let done = 0;
  for (const tile of tiles) {
    try {
      await linkOne(tile);
      done += 1;
    } catch (err) {
      failedPairs.push(`${tile.label}: ${apiErrorText(err, t("console.failed"))}`);
    }
  }
  pairBusy.value = false;
  reportPairs(done, failedPairs, "console.linksDone");
  await changed();
}
async function unlinkTiles(tiles) {
  pairBusy.value = true;
  const failedPairs = [];
  let done = 0;
  for (const tile of tiles) {
    try {
      await api.post(`${lb.value}/console/unlink`, { primary_channel_id: tile.a.id });
      done += 1;
    } catch (err) {
      failedPairs.push(`${tile.label}: ${apiErrorText(err, t("console.failed"))}`);
    }
  }
  pairBusy.value = false;
  reportPairs(done, failedPairs, "console.unlinksDone");
  await changed();
}
function reportPairs(done, failedPairs, key) {
  if (failedPairs.length) {
    $q.notify({ type: "warning", multiLine: true, message: `${t(key, { n: done })} ${failedPairs.slice(0, 4).join("; ")}${failedPairs.length > 4 ? ` …(+${failedPairs.length - 4})` : ""}` });
  } else if (done) {
    $q.notify({ type: "positive", message: t(key, { n: done }) });
  }
}
function linkRange() {
  const tiles = tilesInRange(pairTiles.value, pairRange.value).filter((x) => x.state === "free");
  if (!tiles.length) return $q.notify({ type: "info", message: t("console.pairNone") });
  return linkTiles(tiles);
}
function unlinkRange() {
  const tiles = tilesInRange(pairTiles.value, pairRange.value).filter((x) => x.state === "linked");
  if (!tiles.length) return $q.notify({ type: "info", message: t("console.pairNone") });
  $q.dialog({ title: t("console.unlinkRange"), message: t("console.unlinkRangeConfirm", { n: tiles.length }), cancel: true }).onOk(() => unlinkTiles(tiles));
  return null;
}
async function unlink(ch) {
  try {
    await api.post(`${lb.value}/console/unlink`, { primary_channel_id: ch.id });
    applied();
    await changed();
  } catch (err) {
    failed(err);
  }
}

// --- soft patch ------------------------------------------------------------------------------
// Port-centred: pick a source port, see its sockets as a grid (paged, so a 128-channel Dante card is
// fine), tap a free socket to patch the selected channel. Auto patch and bulk clear cover the
// many-channels case. Inputs and direct outs share the model (`modeField`).
const refKey = (ref) => (ref ? `${ref.device_id}:${ref.port_id}:${ref.socket || 1}` : null);
const portKey = (p) => `${p.device_id}:${p.port_id}`;
// Three kinds of target share this tab: channel inputs ('in'), channel direct outs ('out') and bus
// outputs ('bus'). `modeField` is the API's field name for the current one.
const modeField = computed(() => fieldOfMode(patchMode.value));
const isOutMode = computed(() => patchMode.value !== "in");
const targetPrefix = computed(() => (patchMode.value === "bus" ? t("console.mixShort") : "Ch"));
const portGroups = computed(() => groupPortsByDevice(soft.value?.ports, isOutMode.value ? "out" : "in"));
const allPorts = computed(() => portGroups.value.flatMap((g) => g.ports));
const selPort = computed(() => allPorts.value.find((p) => portKey(p) === selPortKey.value) || null);
const channelNumbers = computed(() => new Map(softStrips.value.map((c) => [c.id, c.channel_number])));
// buses look like channels to the shared list code: a number (their order), a name, their socket
const softBusStrips = computed(() =>
  (soft.value?.buses || []).map((b, i) => ({ id: b.id, channel_number: i + 1, source_label: b.name, out_socket: b.out_endpoints?.length ? b.out_socket : null, out_endpoints: b.out_endpoints || [], mode: b.mode })),
);
// "add another output" mode for the selected bus: a tap adds an endpoint instead of replacing them
const addEndpoint = ref(false);
const outWord = computed(() => t("console.outWord"));
const endpointText = (bus, ep) => `${endpointLabel(ep, deviceNames.value, { out: outWord.value })}${(ep.refs || []).length > 1 ? ` (${endpointSides(ep, bus.mode)})` : ""}`;
const selShortages = computed(() => (patchMode.value === "bus" && selChannel.value ? endpointShortages(selChannel.value) : []));
const busNumbers = computed(() => new Map(softBusStrips.value.map((b) => [b.id, b.channel_number])));
const targetStrips = computed(() => (patchMode.value === "bus" ? softBusStrips.value : softStrips.value));
const targetNumbers = computed(() => new Map(targetStrips.value.map((c) => [c.id, c.channel_number])));
const socketRows = computed(() =>
  isOutMode.value
    ? portSocketsOut(soft.value?.sockets, selPort.value, channelNumbers.value, busNumbers.value, { mix: t("console.mixShort") })
    : portSockets(soft.value?.sockets, selPort.value, "dsp_source", channelNumbers.value),
);
const socketPages = computed(() => Math.max(1, Math.ceil(socketRows.value.length / 64)));
const pagedSockets = computed(() => pageOf(socketRows.value, gridPage.value));
// sockets in use per port: an output socket is used by a direct out OR a bus, so both count
function useMap(field) {
  const keys = field === "dsp_source" ? ["dsp_source_channel_id"] : ["direct_out_channel_id", "out_socket_bus_id"];
  const map = new Map();
  for (const sk of soft.value?.sockets || []) {
    if (keys.some((k) => sk[k])) map.set(`${sk.device_id}:${sk.port_id}`, (map.get(`${sk.device_id}:${sk.port_id}`) || 0) + 1);
  }
  return map;
}
const usedByPort = computed(() => useMap(modeField.value));
const portUsed = (p) => usedByPort.value.get(portKey(p)) || 0;
const deviceNames = computed(() => new Map((soft.value?.ports || []).map((p) => [p.device_id, p.device_name])));
const refLabel = (ref) => `${deviceNames.value.get(ref.device_id) || t("console.missingDevice")} · ${ref.port_id} #${ref.socket}`;
const selChannel = computed(() => targetStrips.value.find((c) => c.id === selChannelId.value) || null);
const selRef = computed(() => selChannel.value?.[modeField.value] || null);
const selOrphaned = computed(() => !!selChannel.value?.[`${modeField.value}_orphaned`]);
const channelOptions = computed(() =>
  targetStrips.value
    .map((c) => ({ value: c.id, label: `${numberedLabel(targetPrefix.value, c.channel_number, c.source_label)}${c[modeField.value] ? ` · ${refLabel(c[modeField.value])}` : ""}`.trim() }))
    .filter((o) => !channelFilter.value || o.label.toLowerCase().includes(channelFilter.value)),
);
function filterChannels(val, update) {
  update(() => { channelFilter.value = (val || "").toLowerCase(); });
}
function selectPort(p) {
  selPortKey.value = portKey(p);
  gridPage.value = 1;
}
// keep a port selected: the first one when none is, or when the mode switch removed the old one
watch(allPorts, (ports) => {
  if (!ports.length) selPortKey.value = null;
  else if (!ports.some((p) => portKey(p) === selPortKey.value)) selectPort(ports[0]);
}, { immediate: true });
const quickOptions = computed(() =>
  socketRows.value.map((sk) => ({
    value: sk.key,
    label: `#${sk.socket}`,
    // an input socket may be shared (split source); outputs stay exclusive
    disable: !!sk.owner && sk.owner !== selChannelId.value && patchMode.value !== "in",
  })),
);

// A non-blocking hint when an input socket is taken by other channels too (a split source).
function splitHint(sharedWith) {
  if (!sharedWith?.length) return;
  $q.notify({ type: "info", timeout: 8000, message: t("console.splitHint", { who: sharedChannelsText(sharedWith) }), "data-testid": "console-split-hint" });
}
async function assignSocket(ch, ref, { append = false } = {}) {
  const url =
    patchMode.value === "bus"
      ? `/jobs/${props.jobId}/outputs/${ch.id}/soft-patch`
      : `/jobs/${props.jobId}/channels/${ch.id}/${patchMode.value === "in" ? "soft-patch" : "direct-out"}`;
  // a bus: a bare ref replaces its endpoints (the server claims the following sockets of a stereo
  // bus); with `append` the tap adds one more endpoint
  const body = patchMode.value === "bus" && ref && append ? { endpoints: [{ refs: [ref] }], append: true } : ref;
  try {
    const { data } = await api.put(url, body);
    applied();
    splitHint(data?.shared_with);
    await changed();
  } catch (err) {
    failed(err);
    await load();
  }
}
async function removeEndpoint(bus, ep) {
  try {
    await api.delete(`/jobs/${props.jobId}/outputs/${bus.id}/soft-patch/${ep.id}`);
    applied();
    await changed();
  } catch (err) {
    failed(err);
    await load();
  }
}
function clickSocket(sk) {
  if (!sk.owner && selIds.value.length >= 2) {
    // several selected: offer to patch them all from this socket on
    patchSelectedFrom(sk);
    return;
  }
  if (sk.owner) {
    const own = (sk.owners || [sk.owner]).includes(selChannelId.value);
    // an input socket another channel takes: with a channel picked that is not on it, patching to it
    // is a split source (allowed, with a hint); otherwise say who shares it
    if (patchMode.value === "in" && selChannel.value && !own) {
      assignSocket(selChannel.value, { device_id: sk.device_id, port_id: sk.port_id, socket: sk.socket });
      return;
    }
    if (sk.shared) {
      $q.notify({ type: "info", message: t("console.splitSocketInfo", { n: sk.socket, who: sk.owners.map((o) => `Ch ${channelNumbers.value.get(o) ?? "?"}`).join(", ") }) });
    }
    // your own socket clears it; another target's selects it; a socket held by the other kind of
    // thing (a bus on a direct-out socket and the reverse) just says who has it
    if (own && !addEndpoint.value && patchMode.value !== "bus") assignSocket(selChannel.value, null);
    else if (targetNumbers.value.has(sk.owner)) selChannelId.value = sk.owner;
    else $q.notify({ type: "info", message: t("console.takenBy", { who: sk.ownerLabel }) });
    return;
  }
  if (!selChannel.value) {
    $q.notify({ type: "info", message: t("console.pickChannelFirst") });
    return;
  }
  if (patchMode.value === "bus") {
    // a stereo / LCR bus claims a run of adjacent sockets: tell the user when it does not fit
    const width = busWidth(selChannel.value.mode);
    if (width > 1 && !busRunAt(socketRows.value, sk.socket, width, selChannel.value.id)) {
      $q.notify({ type: "warning", message: t("console.endpointNoFit", { n: width }) });
      return;
    }
    assignSocket(selChannel.value, { device_id: sk.device_id, port_id: sk.port_id, socket: sk.socket }, { append: addEndpoint.value });
    return;
  }
  assignSocket(selChannel.value, { device_id: sk.device_id, port_id: sk.port_id, socket: sk.socket });
}
function quickAssign(key) {
  const sk = socketRows.value.find((x) => x.key === key);
  assignSocket(selChannel.value, sk ? { device_id: sk.device_id, port_id: sk.port_id, socket: sk.socket } : null);
}

// multi-select over the overview ----------------------------------------------------------------
const overviewItems = computed(() =>
  targetStrips.value.map((c) => ({ id: c.id, kind: patchMode.value === "bus" ? "mix" : "input", number: String(c.channel_number), label: c.source_label || "" })),
);
const visibleItems = computed(() => filterStripItems(overviewItems.value, { query: overviewQuery.value || "" }));
const visibleIds = computed(() => visibleItems.value.map((i) => i.id));
const visibleStrips = computed(() => {
  const keep = new Set(visibleIds.value);
  return targetStrips.value.filter((c) => keep.has(c.id));
});
// with exactly one channel selected the grid keeps its single-assign behaviour on that channel
function syncSingle() {
  if (selIds.value.length === 1) selChannelId.value = selIds.value[0];
}
function onCheck(id, evt) {
  const next = toggleRowSelection(selIds.value, { id, shift: !!evt?.shiftKey, anchor: selAnchor, visibleIds: visibleIds.value });
  selIds.value = next.selected;
  selAnchor = next.anchor;
  syncSingle();
}
function applyRange() {
  selIds.value = selectIds(selIds.value, idsInRanges(visibleItems.value, rangeText.value));
  syncSingle();
}
const selectAllVisible = () => { selIds.value = selectIds(selIds.value, visibleIds.value); syncSingle(); };
const selectNoneVisible = () => { selIds.value = deselectIds(selIds.value, visibleIds.value); };
const selectInvertVisible = () => { selIds.value = invertIds(selIds.value, visibleIds.value); syncSingle(); };
// a deleted channel leaves the selection
watch(targetStrips, (list) => {
  const live = new Set(list.map((c) => c.id));
  if (selIds.value.some((id) => !live.has(id))) selIds.value = selIds.value.filter((id) => live.has(id));
});
// the other kind of target has other ids: switching the mode starts a fresh selection
// (the port stays selected: the allPorts watcher re-picks one when the direction changed)
function onModeChange() {
  selIds.value = [];
  selChannelId.value = null;
  selAnchor = null;
  addEndpoint.value = false;
}
const selPatched = computed(() => selIds.value.filter((id) => targetStrips.value.find((c) => c.id === id)?.[modeField.value]));
function clearSelected() {
  const ids = selPatched.value;
  $q.dialog({ title: t("console.bulkClear"), message: t("console.clearSelConfirm", { n: ids.length }), cancel: true, persistent: true }).onOk(async () => {
    try {
      await api.put(`${lb.value}/soft-patch/bulk`, bulkClearBody(modeField.value, ids));
      applied();
      await changed();
    } catch (err) {
      failed(err);
    }
  });
}
// Tap a free socket with 2+ targets selected: preview "Ch 1 -> 5, Ch 2 -> 6 ..." then apply.
async function patchSelectedFrom(sk) {
  const ids = orderByNumber(selIds.value, targetNumbers.value);
  const port = { device_id: sk.device_id, port_id: sk.port_id };
  const body = (dry) => autoPatchBody(modeField.value, ids, port, { start: sk.socket, skip: true, dry, append: addEndpoint.value, shared: false });
  try {
    const { data } = await api.post(`${lb.value}/soft-patch/auto`, body(true));
    const shown = data.plan.slice(0, 6).map((r) => planRowText(r, targetPrefix.value)).join(", ");
    const more = data.plan.length > 6 ? ` … +${data.plan.length - 6}` : "";
    $q.dialog({
      title: t("console.patchSelectedTitle", { n: data.plan.length, x: sk.socket }),
      message: `${shown}${more}`,
      cancel: true,
      persistent: true,
    }).onOk(async () => {
      try {
        const done = await api.post(`${lb.value}/soft-patch/auto`, body(false));
        $q.notify({ type: "positive", message: t("console.autoDone", { n: done.data.plan.length }) });
        await changed();
      } catch (err) {
        failed(err);
      }
    });
  } catch (err) {
    failed(err);
  }
}

// auto patch -------------------------------------------------------------------------------------
// The dialog patches channels (inputs or direct outs) or buses (outputs) onto consecutive sockets of
// one port. `auto.field` picks the kind; the picker lists the matching strips and the port chooser
// only offers ports of the right direction.
const channelItemsFor = (field) =>
  softStrips.value.map((c) => ({
    id: c.id,
    kind: "input",
    label: c.source_label || "",
    number: String(c.channel_number),
    group: c.instrument_group,
    caption: c[field] ? refLabel(c[field]) : "",
  }));
const busItems = computed(() =>
  softBusStrips.value.map((b) => ({
    id: b.id,
    kind: "mix",
    label: b.source_label || "",
    number: String(b.channel_number),
    caption: b.out_socket ? refLabel(b.out_socket) : "",
  })),
);
const autoItems = computed(() => (auto.field === "out_socket" ? busItems.value : channelItemsFor(auto.field)));
const autoNumbers = computed(() => (auto.field === "out_socket" ? busNumbers.value : channelNumbers.value));
const autoPortOptions = computed(() => {
  const dir = softFieldInfo(auto.field).direction;
  const used = useMap(dir === "in" ? "dsp_source" : "direct_out");
  return groupPortsByDevice(soft.value?.ports, dir).flatMap((g) =>
    g.ports.map((p) => ({
      value: portKey(p),
      label: `${p.device_name} · ${p.connector || p.port_id} (${t("console.freeOf", { free: p.channels - (used.get(portKey(p)) || 0), n: p.channels })})`,
    })),
  );
});
const autoTargets = computed(() => [
  { label: t("console.inputSocket"), value: "dsp_source" },
  { label: t("console.directOut"), value: "direct_out" },
  { label: t("console.busOutputs"), value: "out_socket" },
]);
const splitPortKey = (key) => {
  const i = key.indexOf(":");
  return { device_id: key.slice(0, i), port_id: key.slice(i + 1) };
};
function onAutoPort(key) {
  auto.plan = null;
  auto.error = "";
  const port = (soft.value?.ports || []).find((p) => portKey(p) === key);
  const rows = auto.field === "dsp_source"
    ? portSockets(soft.value?.sockets, port, "dsp_source", channelNumbers.value)
    : portSocketsOut(soft.value?.sockets, port, channelNumbers.value, busNumbers.value);
  auto.start = firstFreeSocket(rows);
}
// the target kind changed inside the dialog: the picked strips and port no longer apply
function onAutoField() {
  auto.channels = [];
  auto.plan = null;
  auto.error = "";
  auto.port = autoPortOptions.value[0]?.value || null;
  if (auto.port) onAutoPort(auto.port);
}
// Opens the dialog pre-filled with the multi-selection (in order), else the one target picked in
// the grid. Both stay editable in the dialog.
function openAuto(ids) {
  const field = modeField.value;
  const picked = Array.isArray(ids) && ids.length ? orderByNumber(ids, targetNumbers.value) : selChannelId.value ? [selChannelId.value] : [];
  Object.assign(auto, { field, channels: picked, plan: null, error: "", skip: true, append: false, shared: false, port: null, start: 1 });
  const port = selPort.value ? portKey(selPort.value) : null;
  auto.port = port || autoPortOptions.value[0]?.value || null;
  if (auto.port) onAutoPort(auto.port);
  autoOpen.value = true;
}
async function runAuto(dry) {
  auto.error = "";
  const order = (id) => autoNumbers.value.get(id) ?? 0;
  const ids = [...auto.channels].sort((a, b) => order(a) - order(b));
  const body = autoPatchBody(auto.field, ids, splitPortKey(auto.port), { start: auto.start, skip: auto.skip, dry, append: auto.append, shared: auto.shared });
  try {
    const { data } = await api.post(`${lb.value}/soft-patch/auto`, body);
    if (dry) {
      auto.plan = data.plan;
      return;
    }
    autoOpen.value = false;
    $q.notify({ type: "positive", message: t("console.autoDone", { n: data.plan.length }) });
    await changed();
  } catch (err) {
    auto.plan = null;
    auto.error = apiErrorText(err, t("console.failed"));
  }
}

// bulk clear -------------------------------------------------------------------------------------
const patchedItems = computed(() =>
  targetStrips.value
    .filter((c) => c[modeField.value])
    .map((c) => ({
      id: c.id,
      kind: patchMode.value === "bus" ? "mix" : "input",
      label: c.source_label || "",
      number: String(c.channel_number),
      group: c.instrument_group,
      caption: refLabel(c[modeField.value]),
    })),
);
function openBulkClear() {
  bulkIds.value = [];
  bulkOpen.value = true;
}
async function runBulkClear() {
  try {
    await api.put(`${lb.value}/soft-patch/bulk`, bulkClearBody(modeField.value, bulkIds.value));
    bulkOpen.value = false;
    $q.notify({ type: "positive", message: t("console.bulkDone", { n: bulkIds.value.length }) });
    await changed();
  } catch (err) {
    failed(err);
  }
}

// --- expansion cards --------------------------------------------------------------------------
async function loadExpansion() {
  try {
    const { data } = await api.get(`${lb.value}/expansion`);
    expansion.value = data;
    if (!expDirty.value) {
      expCards.value = (data.installed || []).map((c) => ({ key: ++cardKey, protocol: c.protocol, channels_in: c.channels_in, channels_out: c.channels_out }));
    }
  } catch {
    expansion.value = { available: [], installed: [] };
  }
}
const cardsOf = (port) => expCards.value.filter((c) => c.protocol === String(port.protocol).toLowerCase());
function expansionFacts(port) {
  const bits = [];
  if (port.slots) bits.push(`${port.slots} ${t("console.slotsShort")}`);
  const inLimit = expansionLimit(port, "in");
  const outLimit = expansionLimit(port, "out");
  if (inLimit != null && inLimit === outLimit) bits.push(t("console.expansionMax", { n: inLimit }));
  else {
    if (inLimit != null) bits.push(`${t("console.maxIn")} ${inLimit}`);
    if (outLimit != null) bits.push(`${t("console.maxOut")} ${outLimit}`);
  }
  return bits.join(" · ");
}
const limitHint = (port, side) => {
  const n = expansionLimit(port, side);
  return n == null ? "" : `≤ ${n}`;
};
function fitCard(port) {
  expCards.value = [
    ...expCards.value,
    { key: ++cardKey, protocol: String(port.protocol).toLowerCase(), channels_in: expansionLimit(port, "in") ?? 0, channels_out: expansionLimit(port, "out") ?? 0 },
  ];
  expSaver.flush();
}
function removeCard(card) {
  expCards.value = expCards.value.filter((c) => c.key !== card.key);
  expSaver.flush();
}
async function persistExpansion() {
  try {
    await api.put(`${lb.value}/expansion`, { installed: expansionPayload(expCards.value) });
    await changed();
    return true;
  } catch (err) {
    failed(err);
    if (!isRefusal(err)) return false;
    expSaver.reset();
    await loadExpansion();
    return true;
  }
}

// --- leaving -----------------------------------------------------------------------------------
// Pending (debounced) edits are written when the tab changes, the panel closes or the page is hidden.
function requestTab(next) {
  if (next === tab.value) return;
  settleAll();
  tab.value = next;
}
function onHidden() {
  if (document.visibilityState === "hidden") settleAll();
}
document.addEventListener("visibilitychange", onHidden);
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onHidden);
  settleAll();
});
// the editor that hosts the panel lets pending edits land before it closes it
defineExpose({ settle: settleAll, openTab: (name) => (tab.value = name) });
</script>

<style scoped>
.fader-bank {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  gap: 6px;
}
.fader-strip {
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  padding: 4px 6px;
  min-height: 62px;
  min-width: 0;
}
.kind-input { background: rgba(63, 135, 63, 0.25); }
.kind-mix { background: rgba(38, 166, 154, 0.25); }
.kind-dca { background: rgba(255, 193, 7, 0.22); }
.kind-fx { background: rgba(156, 39, 176, 0.28); }
.kind-fxsend { background: rgba(233, 30, 99, 0.25); }
.socket-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
  gap: 4px;
}
.socket-btn { min-height: 40px; }
.fader-over { outline: 2px solid var(--q-primary); }
.fader-tray { border: 1px dashed rgba(255, 255, 255, 0.35); border-radius: 6px; padding: 8px; }
.fader-strip[draggable="true"] { cursor: grab; }
.kind-empty { opacity: 0.4; }
.fx-placeholder { opacity: 0.65; }
.hidden-fx { border: 1px dashed rgba(255, 255, 255, 0.3); border-radius: 6px; }
.fader-editable { cursor: pointer; outline: 1px dashed rgba(255, 255, 255, 0.35); }
.pair-tile {
  min-width: 72px;
  min-height: 40px;
}
</style>
