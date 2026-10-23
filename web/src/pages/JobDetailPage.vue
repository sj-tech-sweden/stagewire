<template>
  <q-page class="q-pa-md">
    <div
      v-if="jobError"
      class="text-center q-mt-xl text-grey"
    >
      {{ jobError }}
    </div>

    <template v-else>
      <div class="row items-center q-mb-md">
        <q-btn
          flat
          round
          icon="arrow_back"
          :aria-label="t('channels.backToJobs')"
          class="q-mr-sm"
          @click="router.push('/')"
        />
        <div class="col">
          <div class="row items-center">
            <div class="text-h5">
              {{ job?.title }}
            </div>
            <q-btn
              flat
              round
              dense
              icon="edit"
              class="q-ml-sm"
              :aria-label="t('channels.editJob')"
              @click="openJobDialog"
            />
            <q-space />
            <q-btn
              flat
              icon="description"
              :label="t('channels.patchSheets')"
              class="q-ml-sm"
              @click="router.push(`/jobs/${route.params.jobId}/patch-sheets`)"
            />
          </div>
          <div class="row items-center q-gutter-xs q-mt-xs">
            <q-chip
              dense
              square
              :color="job?.stockwire_job_id ? 'positive' : 'grey-7'"
              text-color="white"
              icon="link"
            >
              {{ job?.stockwire_job_id ? t('stockwire.linkedAs', { id: job.stockwire_job_id }) : t('stockwire.notLinked') }}
            </q-chip>
            <template v-if="!job?.stockwire_job_id">
              <q-btn
                dense
                outline
                color="primary"
                icon="link"
                :label="t('stockwire.linkExisting')"
                @click="openLinkDialog"
              />
              <q-btn
                dense
                outline
                color="primary"
                icon="add"
                :label="t('stockwire.createNew')"
                :loading="linking"
                @click="linkStockwire(null)"
              />
            </template>
            <q-btn
              dense
              outline
              color="primary"
              icon="playlist_add"
              :label="t('stockwire.addDevices')"
              :loading="pushing"
              :disable="!job?.stockwire_job_id"
              @click="pushToStockwire"
            >
              <q-tooltip v-if="!job?.stockwire_job_id">
                {{ t('stockwire.addDevicesNeedsLink') }}
              </q-tooltip>
            </q-btn>
            <q-btn
              dense
              outline
              color="primary"
              icon="open_in_new"
              :label="t('stockwire.openInStockwire')"
              :disable="!job?.stockwire_job_id"
              @click="openInStockwire"
            />
          </div>
          <div class="text-caption text-grey-7 q-mt-xs">
            {{ t('stockwire.addDevicesHint') }}
          </div>
          <div
            v-if="pushMessage"
            class="text-caption q-mt-xs"
            :class="pushError ? 'text-negative' : 'text-positive'"
          >
            {{ pushMessage }}
          </div>
          <div
            class="text-subtitle2 text-grey-7 cursor-pointer"
            @click="openJobDialog"
          >
            <span v-if="job?.venue_name">{{ job.venue_name }}</span>
            <span v-if="job?.event_date"> · {{ formatDate(job.event_date) }}</span>
          </div>
          <TruncateText
            v-if="job?.notes"
            :lines="2"
            class="q-mt-xs text-body2"
          >
            <MarkdownText :source="job.notes" />
          </TruncateText>
        </div>
      </div>

      <q-banner
        v-if="store.error"
        class="bg-negative text-white q-mb-md"
      >
        {{ store.error }}
      </q-banner>

      <q-splitter
        v-model="split"
        :horizontal="!$q.screen.lt.sm"
        :limits="$q.screen.lt.sm ? [18, 18] : [20, 50]"
        class="full-height"
      >
        <!-- Channel lists -->
        <template #before>
          <div
            v-if="!$q.screen.lt.sm"
            class="q-pa-sm"
          >
            <div class="row items-center q-mb-sm">
              <div class="text-subtitle1">
                {{ t('channels.lists') }}
              </div>
              <q-space />
              <q-btn
                dense
                flat
                round
                icon="add"
                :aria-label="t('channels.addList')"
                @click="openNewList"
              />
            </div>
            <q-list
              v-if="store.lists.length"
              bordered
              separator
            >
              <q-item
                v-for="list in store.lists"
                :key="list.id"
                v-ripple
                clickable
                :active="list.id === store.selectedListId"
                active-class="bg-primary text-white"
                @click="selectList(list.id)"
              >
                <q-item-section>{{ list.name }}</q-item-section>
                <q-item-section side>
                  <div class="row no-wrap">
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="edit"
                      @click.stop="openRenameList(list)"
                    />
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="delete"
                      @click.stop="removeList(list)"
                    />
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="download"
                      :aria-label="t('export.title')"
                      @click.stop="openExport(list)"
                    />
                  </div>
                </q-item-section>
              </q-item>
            </q-list>
            <div
              v-else
              class="text-grey q-pa-sm"
            >
              {{ t('channels.noLists') }}
            </div>
          </div>

          <div
            v-else
            class="q-pa-sm"
          >
            <div class="row items-center q-gutter-sm">
              <q-select
                :model-value="store.selectedListId"
                :options="listOptions"
                emit-value
                map-options
                :label="t('channels.lists')"
                class="col"
                @update:model-value="selectList"
              />
              <q-btn
                dense
                flat
                round
                icon="add"
                :aria-label="t('channels.addList')"
                @click="openNewList"
              />
              <q-btn-dropdown
                v-if="store.selectedList"
                dense
                flat
                icon="more_vert"
                auto-close
              >
                <q-list>
                  <q-item
                    clickable
                    @click="openRenameList(store.selectedList)"
                  >
                    <q-item-section avatar>
                      <q-icon name="edit" />
                    </q-item-section>
                    <q-item-section>{{ t('channels.renameList') }}</q-item-section>
                  </q-item>
                  <q-item
                    clickable
                    @click="openExport(store.selectedList)"
                  >
                    <q-item-section avatar>
                      <q-icon name="download" />
                    </q-item-section>
                    <q-item-section>{{ t('export.title') }}</q-item-section>
                  </q-item>
                  <q-item
                    clickable
                    @click="removeList(store.selectedList)"
                  >
                    <q-item-section avatar>
                      <q-icon
                        name="delete"
                        color="negative"
                      />
                    </q-item-section>
                    <q-item-section class="text-negative">
                      {{ t('common.delete') }}
                    </q-item-section>
                  </q-item>
                </q-list>
              </q-btn-dropdown>
            </div>
          </div>
        </template>

        <!-- Channels -->
        <template #after>
          <div class="q-pa-sm">
            <div
              v-if="!store.selectedList"
              class="text-grey q-pa-md text-center"
            >
              {{ t('channels.noLists') }}
            </div>
            <template v-else>
              <q-card
                flat
                bordered
                class="q-pa-sm q-mb-sm row items-center q-gutter-sm"
              >
                <q-icon
                  name="tune"
                  color="primary"
                  size="sm"
                />
                <div class="col">
                  <div class="text-caption text-grey-7">
                    {{ t('stockwire.mixerOfList') }}
                  </div>
                  <div v-if="store.selectedList.mixer_product_name">
                    {{ store.selectedList.mixer_product_name }}
                    <span
                      v-if="store.selectedList.mixer_inputs != null"
                      class="text-grey-7"
                    > · {{ store.selectedList.mixer_inputs }} {{ t('stockwire.inputsShort') }}</span>
                    <span
                      v-if="store.selectedList.mixer_buses != null"
                      class="text-grey-7"
                    > · {{ store.selectedList.mixer_buses }} {{ t('stockwire.busesShort') }}</span>
                  </div>
                  <div
                    v-else
                    class="text-grey-7"
                  >
                    {{ t('stockwire.mixerNotSet') }}
                  </div>
                </div>
                <q-btn
                  outline
                  color="primary"
                  icon="edit"
                  :label="store.selectedList.mixer_product_name ? t('stockwire.changeMixer') : t('stockwire.setMixer')"
                  @click="openMixer(store.selectedList)"
                />
              </q-card>
              <div class="row items-center q-mb-sm">
                <div class="text-subtitle1">
                  {{ store.selectedList.name }}
                </div>
                <q-space />
                <q-btn
                  color="primary"
                  icon="add"
                  :label="t('channels.addChannel')"
                  class="q-mr-xs"
                  @click="openChannelDialog()"
                />
                <q-btn
                  outline
                  color="primary"
                  icon="playlist_add"
                  :label="t('channels.bulkAdd')"
                  class="q-mr-xs"
                  @click="bulkDialog = true"
                />
                <q-btn
                  outline
                  color="primary"
                  icon="download"
                  :label="t('export.action')"
                  class="q-mr-xs"
                  :disable="!store.selectedList"
                  @click="openExport(store.selectedList)"
                />
              </div>

              <div class="row items-center q-mt-sm q-mb-xs">
                <div class="text-subtitle2">
                  {{ t('channels.inputs') }}
                </div>
                <q-space />
                <ColumnChooser :prefs="channelPrefs" />
              </div>

              <q-list
                v-if="$q.screen.lt.sm"
                separator
                class="q-mt-sm"
              >
                <q-card
                  v-for="row in store.channels"
                  :key="row.id"
                  flat
                  bordered
                  class="q-ma-xs q-pa-xs"
                >
                  <q-card-section class="q-gutter-xs">
                    <div class="row q-gutter-sm items-center">
                      <q-input
                        :model-value="row.channel_number"
                        type="number"
                        dense
                        :label="t('channels.fieldChannelNumber')"
                        style="width: 72px"
                        @change="(v) => saveInline(row, 'channel_number', v === '' || v === null ? null : Number(v))"
                      />
                      <q-input
                        :model-value="row.source_label"
                        dense
                        :label="t('channels.fieldSource')"
                        class="col"
                        @change="(v) => saveInline(row, 'source_label', v)"
                      />
                    </div>
                    <div class="row q-gutter-sm">
                      <q-select
                        :model-value="row.input_type"
                        :options="inputTypeOptions"
                        dense
                        emit-value
                        map-options
                        clearable
                        :label="t('channels.type.label')"
                        class="col"
                        @update:model-value="(v) => saveInline(row, 'input_type', v)"
                      />
                      <q-select
                        :model-value="row.connector"
                        :options="connectorOptions"
                        dense
                        clearable
                        :label="t('channels.fieldConnector')"
                        class="col"
                        @update:model-value="(v) => saveInline(row, 'connector', v)"
                      />
                    </div>
                    <StockwireProductPicker
                      :model-value="standModel(row)"
                      gear-type="stand"
                      :label="t('stockwire.selectStand')"
                      hint=""
                      @update:model-value="(v) => saveStand(row, v)"
                    />
                    <StockwireProductPicker
                      :model-value="deviceModel(row)"
                      :gear-type="gearTypeForInput(row.input_type)"
                      :label="t('channels.fieldDevice')"
                      hint=""
                      @update:model-value="(v) => saveDevice(row, v)"
                    />
                    <div class="row items-center justify-between">
                      <q-toggle
                        :model-value="row.phantom_power"
                        :label="t('channels.fieldPhantom')"
                        @update:model-value="(v) => saveInline(row, 'phantom_power', v)"
                      />
                      <q-chip
                        v-if="stereoView(row).linked"
                        dense
                        color="primary"
                        text-color="white"
                        size="sm"
                      >
                        {{ stereoView(row).isL ? 'L' : 'R' }}
                      </q-chip>
                      <span
                        v-else
                        class="text-grey-6 text-caption"
                      >{{ t('channels.mono') }}</span>
                    </div>
                    <div
                      v-if="row.notes"
                      class="text-caption"
                    >
                      <MarkdownText :source="row.notes" />
                    </div>
                  </q-card-section>
                  <q-card-actions align="right">
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="edit"
                      @click="openChannelDialog(row)"
                    />
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="delete"
                      color="negative"
                      @click="removeChannel(row)"
                    />
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="account_tree"
                      :aria-label="t('channels.viewFlow')"
                      @click="openFlow('input', row)"
                    />
                  </q-card-actions>
                </q-card>
              </q-list>

              <q-table
                v-else
                :rows="store.channels"
                :columns="channelColumns"
                row-key="id"
                dense
                :no-data-label="t('channels.none')"
                :loading="store.loading"
                :pagination="pagination"
                :rows-per-page-options="[50, 100, 0]"
              >
                <template #body-cell-channel_number="cell">
                  <q-td
                    :props="cell"
                    style="width: 70px"
                  >
                    <q-input
                      :model-value="cell.value"
                      type="number"
                      dense
                      borderless
                      @change="(v) => saveInline(cell.row, 'channel_number', v === '' || v === null ? null : Number(v))"
                    />
                  </q-td>
                </template>
                <template #body-cell-source_label="cell">
                  <q-td :props="cell">
                    <q-input
                      :model-value="cell.value"
                      dense
                      borderless
                      @change="(v) => saveInline(cell.row, 'source_label', v)"
                    />
                  </q-td>
                </template>
                <template #body-cell-input_type="cell">
                  <q-td :props="cell">
                    <q-select
                      :model-value="cell.value"
                      :options="inputTypeOptions"
                      dense
                      borderless
                      emit-value
                      map-options
                      clearable
                      @update:model-value="(v) => saveInline(cell.row, 'input_type', v)"
                    />
                  </q-td>
                </template>
                <template #body-cell-connector="cell">
                  <q-td :props="cell">
                    <q-select
                      :model-value="cell.value"
                      :options="connectorOptions"
                      dense
                      borderless
                      clearable
                      @update:model-value="(v) => saveInline(cell.row, 'connector', v)"
                    />
                  </q-td>
                </template>
                <template #body-cell-stand="cell">
                  <q-td
                    :props="cell"
                    style="min-width: 220px"
                  >
                    <StockwireProductPicker
                      :model-value="standModel(cell.row)"
                      gear-type="stand"
                      label=""
                      hint=""
                      @update:model-value="(v) => saveStand(cell.row, v)"
                    />
                  </q-td>
                </template>
                <template #body-cell-device="cell">
                  <q-td
                    :props="cell"
                    style="min-width: 240px"
                  >
                    <StockwireProductPicker
                      :model-value="deviceModel(cell.row)"
                      :gear-type="gearTypeForInput(cell.row.input_type)"
                      label=""
                      hint=""
                      @update:model-value="(v) => saveDevice(cell.row, v)"
                    />
                  </q-td>
                </template>
                <template #body-cell-phantom="cell">
                  <q-td
                    :props="cell"
                    class="text-center"
                    style="width: 70px"
                  >
                    <q-toggle
                      :model-value="cell.value"
                      @update:model-value="(v) => saveInline(cell.row, 'phantom_power', v)"
                    />
                  </q-td>
                </template>

                <template #body-cell-stereo="cell">
                  <q-td
                    :props="cell"
                    class="text-center"
                    style="width: 80px; padding: 0"
                  >
                    <template v-if="(sv = stereoView(cell.row)) && sv.linked">
                      <div class="stereo-link-col">
                        <template v-if="sv.isL">
                          <q-chip
                            dense
                            color="primary"
                            text-color="white"
                            size="sm"
                            :title="stereoTitle(cell.row)"
                          >
                            L
                          </q-chip>
                          <template v-if="sv.top">
                            <div class="stereo-line" />
                            <q-icon
                              name="link"
                              color="primary"
                              size="1rem"
                              class="stereo-icon"
                            />
                          </template>
                          <q-icon
                            v-else
                            name="link"
                            color="primary"
                            size="1rem"
                          />
                        </template>
                        <template v-else>
                          <template v-if="sv.bottom">
                            <div class="stereo-line" />
                          </template>
                          <q-chip
                            dense
                            color="primary"
                            text-color="white"
                            size="sm"
                            :title="stereoTitle(cell.row)"
                          >
                            R
                          </q-chip>
                          <q-icon
                            v-if="!sv.bottom"
                            name="link"
                            color="primary"
                            size="1rem"
                          />
                        </template>
                      </div>
                    </template>
                    <span
                      v-else
                      class="text-grey-6"
                    >—</span>
                  </q-td>
                </template>

                <template #body-cell-notes="cell">
                  <q-td :props="cell">
                    <TruncateText
                      v-if="cell.value"
                      :lines="2"
                    >
                      <MarkdownText :source="cell.value" />
                    </TruncateText>
                    <span
                      v-else
                      class="text-grey-6"
                    >—</span>
                  </q-td>
                </template>
                <template #body-cell-actions="cell">
                  <q-td :props="cell">
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="edit"
                      @click="openChannelDialog(cell.row)"
                    />
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="delete"
                      @click="removeChannel(cell.row)"
                    />
                    <q-btn
                      dense
                      flat
                      round
                      size="sm"
                      icon="account_tree"
                      :aria-label="t('channels.viewFlow')"
                      @click="openFlow('input', cell.row)"
                    />
                  </q-td>
                </template>
              </q-table>

              <!-- Outputs (buses) -->
              <div class="text-subtitle1 q-mt-lg q-mb-xs">
                {{ t('channels.outputs') }}
              </div>
              <div class="text-caption text-grey-7 q-mb-sm">
                {{ t('channels.outputsHint') }}
              </div>
              <div class="row q-gutter-sm q-mb-md">
                <q-btn
                  color="primary"
                  icon="add"
                  :label="t('channels.addOutput')"
                  @click="openOutputDialog(store.selectedList.id)"
                />
                <q-btn
                  outline
                  color="primary"
                  icon="library_add"
                  :label="t('channels.bulkAddOutputs')"
                  @click="openBulkOutputs"
                />
              </div>
              <q-expansion-item
                v-for="bus in store.selectedList.outputs || []"
                :key="bus.id"
                :label="bus.name"
                :caption="busHeaderCaption(bus)"
                default-opened
                class="q-mb-xs"
                group="outputs"
              >
                <q-card
                  flat
                  bordered
                >
                  <q-card-section>
                    <div
                      v-if="bus.notes"
                      class="text-body2 q-mb-sm"
                      style="white-space: pre-line"
                    >
                      {{ bus.notes }}
                    </div>
                    <div class="row items-center q-mb-xs">
                      <q-space />
                      <ColumnChooser :prefs="outputPrefs" />
                    </div>
                    <q-list
                      v-if="$q.screen.lt.sm"
                      separator
                      class="q-mt-xs"
                    >
                      <q-card
                        v-for="point in bus.points || []"
                        :key="point.id"
                        flat
                        bordered
                        class="q-ma-xs q-pa-xs"
                      >
                        <q-card-section class="q-gutter-xs">
                          <template
                            v-for="col in outputTableColumns"
                            :key="col.name"
                          >
                            <div
                              v-if="col.name !== 'device' && col.name !== 'actions'"
                              class="row q-gutter-sm items-center"
                            >
                              <div class="text-caption text-grey-7 col-5">
                                {{ col.label }}
                              </div>
                              <div class="col">
                                {{ outputCellDisplay(col, point) || '—' }}
                              </div>
                            </div>
                          </template>
                          <StockwireProductPicker
                            v-if="outputTableColumns.find((c) => c.name === 'device')"
                            :model-value="outputDeviceModel(point)"
                            :gear-type="pointGearType(point.point_type)"
                            :label="t('channels.fieldDevice')"
                            hint=""
                            @update:model-value="(v) => saveOutputDevice(bus, point, v)"
                          />
                        </q-card-section>
                      </q-card>
                    </q-list>
                    <q-table
                      v-else
                      :rows="bus.points || []"
                      :columns="outputTableColumns"
                      row-key="id"
                      flat
                      bordered
                      dense
                      hide-bottom
                      :no-data-label="t('channels.patchPoint.none')"
                    >
                      <template #body-cell-device="cell">
                        <q-td :props="cell">
                          <StockwireProductPicker
                            :model-value="outputDeviceModel(cell.row)"
                            :gear-type="pointGearType(cell.row.point_type)"
                            label=""
                            hint=""
                            @update:model-value="(v) => saveOutputDevice(bus, cell.row, v)"
                          />
                        </q-td>
                      </template>
                    </q-table>
                    <div class="row q-gutter-sm q-mt-sm">
                      <q-btn
                        dense
                        flat
                        icon="edit"
                        :label="t('common.edit')"
                        @click="openOutputDialog(store.selectedList.id, bus)"
                      />
                      <q-btn
                        dense
                        flat
                        icon="delete"
                        color="negative"
                        :label="t('common.delete')"
                        @click="removeOutput(store.selectedList.id, bus)"
                      />
                      <q-btn
                        dense
                        flat
                        icon="account_tree"
                        :label="t('channels.viewFlow')"
                        @click="openFlow('output', bus)"
                      />
                    </div>
                  </q-card-section>
                </q-card>
              </q-expansion-item>
            </template>
          </div>
        </template>
      </q-splitter>
    </template>

    <!-- Channel edit dialog -->
    <q-dialog
      v-model="channelDialog"
      persistent
    >
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ editingChannel ? t('channels.editChannel') : t('channels.addChannel') }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="form.channel_number"
              type="number"
              :label="t('channels.fieldChannelNumber')"
              style="width: 90px"
            />
            <q-input
              v-model="form.source_label"
              :label="t('channels.fieldSource')"
              class="col"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-select
              v-model="form.input_type"
              :options="inputTypeOptions"
              :label="t('channels.type.label')"
              emit-value
              map-options
              clearable
              class="col"
            />
            <q-select
              v-model="form.connector"
              :options="connectorOptions"
              :label="t('channels.fieldConnector')"
              clearable
              class="col"
            />
          </div>
          <div class="row q-gutter-sm q-mt-xs">
            <StockwireProductPicker
              v-model="form.stockwire_product"
              :gear-type="sourceGearType"
              :label="t('channels.fieldDevice')"
              :hint="form.stockwire_product?.sku || t('channels.fieldDeviceHint')"
              class="col"
            />
            <StockwireProductPicker
              v-model="form.stand_product"
              gear-type="stand"
              :label="t('stockwire.selectStand')"
              :hint="form.stand_product ? form.stand_product.sku : ''"
              class="col"
            />
          </div>
          <div class="row q-gutter-sm items-center">
            <q-toggle
              v-model="form.phantom_power"
              :label="t('channels.fieldPhantom')"
            />
            <q-toggle
              v-model="form.stereo"
              :label="t('channels.fieldStereo')"
              @update:model-value="onStereoToggle"
            />
            <q-input
              v-if="form.stereo"
              v-model.number="form.stereo_channel"
              type="number"
              :label="t('channels.fieldStereoChannel')"
              style="width: 110px"
            />
          </div>
          <div class="text-subtitle2 q-mt-sm q-mb-xs">
            {{ t('channels.patchPoints') }}
          </div>
          <div class="text-caption text-grey-7 q-mb-xs">
            {{ t('channels.patchPoint.flowHint') }}
          </div>
          <div class="text-caption text-primary q-mb-xs">
            {{ t('channels.patchPoint.orderHint') }}
          </div>
          <q-list
            bordered
            separator
          >
            <q-item
              v-for="(pt, idx) in patchPoints"
              :key="pt.id || `np-${idx}`"
            >
              <q-item-section>
                <div class="row q-gutter-sm items-center">
                  <q-select
                    v-model="pt.point_type"
                    :options="patchPointTypeOptions"
                    :label="t('channels.patchPoint.type')"
                    emit-value
                    map-options
                    dense
                    style="width: 160px"
                  />
                  <q-select
                    v-model="pt.name"
                    :options="patchNameOptions"
                    :label="t('channels.patchPoint.name')"
                    :hint="t('channels.patchPoint.nameHint')"
                    dense
                    use-input
                    new-value-mode="add-unique"
                    clearable
                    class="col"
                  />
                  <q-select
                    v-model="pt.connector"
                    :options="connectorOptions"
                    :label="t('channels.patchPoint.connector')"
                    :hint="t('channels.patchPoint.connectorHint')"
                    dense
                    clearable
                    style="width: 120px"
                  />
                  <q-input
                    v-model="pt.patch_label"
                    :label="t('channels.patchPoint.label')"
                    :hint="t('channels.patchPoint.labelHint')"
                    dense
                    style="width: 110px"
                  />
                </div>
                <StockwireProductPicker
                  v-model="pt.stockwire_product"
                  :gear-type="pointGearType(pt.point_type)"
                  :label="t('stockwire.selectPatch')"
                  :hint="pt.stockwire_product ? pt.stockwire_product.sku : ''"
                  class="q-mt-xs"
                />
                <q-input
                  v-model="pt.notes"
                  :label="t('channels.patchPoint.notes')"
                  dense
                  type="textarea"
                  autogrow
                  class="q-mt-xs"
                />
              </q-item-section>
              <q-item-section side>
                <div class="column">
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="arrow_upward"
                    :disable="idx === 0"
                    @click="movePatchPoint(idx, -1)"
                  />
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="arrow_downward"
                    :disable="idx === patchPoints.length - 1"
                    @click="movePatchPoint(idx, 1)"
                  />
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="delete"
                    color="negative"
                    @click="removePatchPoint(idx)"
                  />
                </div>
              </q-item-section>
            </q-item>
          </q-list>
          <q-btn
            class="q-mt-sm"
            dense
            flat
            icon="add"
            :label="t('channels.patchPoint.add')"
            @click="addPatchPoint"
          />
          <q-input
            v-model="form.notes"
            :label="t('channels.fieldNotes')"
            type="textarea"
            autogrow
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            @click="saveChannel"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Bulk add dialog -->
    <q-dialog
      v-model="bulkOutputDialog"
      persistent
    >
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('channels.bulkAddOutputs') }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="bulkOut.quantity"
              type="number"
              :label="t('channels.bulk.quantity')"
              style="width: 100px"
            />
            <q-input
              v-model.number="bulkOut.startNumber"
              type="number"
              :label="t('channels.bulk.startOutput')"
              style="width: 120px"
            />
            <q-input
              v-model="bulkOut.prefix"
              :label="t('channels.bulk.prefix')"
              class="col"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-select
              v-model="bulkOut.mode"
              :options="outputModeOptions"
              :label="t('channels.outputMode')"
              emit-value
              map-options
              class="col"
            />
            <q-select
              v-model="bulkOut.connector"
              :options="connectorOptions"
              :label="t('channels.patchPoint.connector')"
              clearable
              class="col"
            />
          </div>
          <div class="text-caption text-grey-7">
            {{ t('channels.bulkOutputsHint', { count: Math.max(0, Number(bulkOut.quantity) || 0) }) }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            :disable="!(Number(bulkOut.quantity) > 0)"
            @click="saveBulkOutputs"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog
      v-model="bulkDialog"
      persistent
    >
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('channels.bulkAdd') }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="bulk.quantity"
              type="number"
              :label="t('channels.bulk.quantity')"
              style="width: 100px"
            />
            <q-input
              v-model.number="bulk.startChannel"
              type="number"
              :label="t('channels.bulk.startChannel')"
              style="width: 120px"
            />
            <q-input
              v-model="bulk.prefix"
              :label="t('channels.bulk.prefix')"
              class="col"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-select
              v-model="bulk.type"
              :options="inputTypeOptions"
              :label="t('channels.bulk.type')"
              emit-value
              map-options
              clearable
              class="col"
            />
            <q-input
              v-model="bulk.device"
              :label="t('channels.bulk.device')"
              class="col"
            />
          </div>
          <div class="row q-gutter-sm items-center">
            <q-toggle
              v-model="bulk.phantom"
              :label="t('channels.bulk.phantom')"
            />
            <q-toggle
              v-model="bulk.stereo"
              :label="t('channels.bulk.stereo')"
            />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            @click="saveBulk"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- List create / rename popup -->
    <q-dialog
      v-model="listDialog"
      persistent
    >
      <q-card style="min-width: 360px">
        <q-card-section class="text-h6">
          {{ listEditing ? t('channels.renameList') : t('channels.addList') }}
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="listName"
            :label="t('channels.newListName')"
            autofocus
            @keyup.enter="saveList"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            :disable="!listName.trim()"
            @click="saveList"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Link to an existing stockwire-rental job -->
    <q-dialog
      v-model="linkDialog"
      persistent
    >
      <q-card style="min-width: 520px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('stockwire.linkExistingTitle') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <q-input
            v-model="linkSearch"
            :label="t('stockwire.linkSearch')"
            dense
            clearable
            autofocus
            @update:model-value="onLinkSearch"
          />
          <q-list
            v-if="linkResults.length"
            bordered
            separator
          >
            <q-item
              v-for="r in linkResults"
              :key="r.id"
              clickable
              @click="linkStockwire(r.id)"
            >
              <q-item-section>
                <div class="text-subtitle2">
                  {{ r.description || r.job_code }}
                </div>
                <div class="text-caption text-grey-7">
                  {{ r.job_code }}
                  <span v-if="r.venue_name"> · {{ r.venue_name }}</span>
                  <span v-if="r.start_date"> · {{ r.start_date }}</span>
                </div>
              </q-item-section>
            </q-item>
          </q-list>
          <div
            v-else-if="!linkLoading"
            class="text-grey q-pa-sm text-center"
          >
            {{ t('stockwire.linkNoResults') }}
          </div>
          <div
            v-else
            class="text-grey q-pa-sm text-center"
          >
            {{ t('stockwire.searching') }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Mixer for a channel list -->
    <q-dialog
      v-model="mixerDialog"
      persistent
    >
      <q-card style="min-width: 480px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('stockwire.mixerDialogTitle', { name: mixerList?.name || '' }) }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <div class="text-caption text-grey-7">
            {{ t('stockwire.mixerDialogHint') }}
          </div>
          <StockwireProductPicker
            :model-value="mixerProduct"
            gear-type="mixer"
            :label="t('stockwire.mixerPickLabel')"
            :hint="mixerProduct?.sku || ''"
            @update:model-value="(v) => chooseMixer(v)"
          />
          <div
            v-if="mixerSpecNote"
            class="text-caption text-grey-7"
          >
            {{ mixerSpecNote }}
          </div>
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="mixerInputs"
              :label="t('stockwire.mixerInputs')"
              type="number"
              dense
              class="col"
            />
            <q-input
              v-model.number="mixerBuses"
              :label="t('stockwire.mixerBuses')"
              type="number"
              dense
              class="col"
            />
          </div>
          <div class="row items-center q-gutter-sm">
            <q-btn
              flat
              icon="auto_fix_high"
              :label="t('stockwire.suggestMixer')"
              :loading="mixerSuggesting"
              @click="suggestMixer"
            />
            <span class="text-caption text-grey-7">
              {{ t('stockwire.suggestMixerHint', { count: channelCount || mixerInputs || 1 }) }}
            </span>
          </div>
          <q-list
            v-if="mixerSuggestions.length"
            bordered
            separator
          >
            <q-item
              v-for="p in mixerSuggestions"
              :key="p.id"
              clickable
              @click="applyMixerSuggestion(p)"
            >
              <q-item-section>
                <div class="text-subtitle2">
                  {{ p.name }}
                </div>
                <div class="text-caption text-grey-7">
                  <span v-if="p.brand">{{ p.brand }}</span>
                  <span v-if="p.manufacturer"> · {{ p.manufacturer }}</span>
                  <span v-if="p.sku"> · {{ p.sku }}</span>
                </div>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            @click="saveMixer"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Export to console dialog -->
    <q-dialog
      v-model="exportDialog"
      persistent
    >
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('export.title') }}
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <div
            v-if="exportList"
            class="text-caption text-grey-7 q-mb-xs"
          >
            {{ t('export.fromList') }}: {{ exportList.name }}
          </div>
          <div class="text-caption q-mb-sm">
            {{ t('export.description') }}
          </div>
          <q-list
            bordered
            separator
          >
            <q-item
              v-for="p in exportPlugins"
              :key="p.key"
              v-ripple
              clickable
              :active="exportSelected === p.key"
              active-class="bg-primary text-white"
              @click="exportSelected = p.key"
            >
              <q-item-section>
                <div class="text-subtitle2">
                  {{ p.label }}
                </div>
                <div class="text-caption text-grey-7">
                  {{ p.description }}
                </div>
              </q-item-section>
              <q-item-section side>
                <q-chip
                  dense
                  outline
                >
                  {{ p.file_extension }}
                </q-chip>
              </q-item-section>
            </q-item>
          </q-list>
          <div
            v-if="exportError"
            class="text-negative q-mt-sm"
          >
            {{ exportError }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('export.close')"
            color="primary"
          />
          <q-btn
            flat
            :disable="!exportSelected"
            :label="t('export.download')"
            color="primary"
            :loading="exportLoading"
            @click="downloadExportFile"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Job edit dialog -->
    <q-dialog
      v-model="jobDialog"
      persistent
    >
      <q-card style="min-width: 420px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('channels.editJob') }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input
            v-model="jobForm.title"
            :label="t('jobs.fieldTitle')"
          />
          <q-input
            v-model="jobForm.venue_name"
            :label="t('jobs.fieldVenue')"
          />
          <DateTimePicker
            v-model="jobForm.event_date"
            :label="t('jobs.fieldEventDate')"
          />
          <q-input
            v-model="jobForm.notes"
            :label="t('jobs.fieldNotes')"
            type="textarea"
            autogrow
          />
          <div class="text-subtitle2 q-mt-sm">
            {{ t('stockwire.linkedJob') }}
          </div>
          <div class="row q-gutter-sm items-center">
            <q-input
              v-model="jobForm.stockwire_job_id"
              :label="t('stockwire.linkJob')"
              class="col"
            />
            <q-btn
              flat
              icon="open_in_new"
              :label="t('stockwire.openInStockwire')"
              :disable="!jobForm.stockwire_job_id"
              @click="openInStockwire"
            />
            <q-btn
              color="primary"
              icon="send"
              :label="t('stockwire.pushToStockwire')"
              :loading="pushing"
              @click="pushToStockwire"
            />
          </div>
          <div
            v-if="pushMessage"
            class="text-caption text-positive q-mt-xs"
          >
            {{ pushMessage }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            @click="saveJob"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Output (bus) edit dialog -->
    <q-dialog
      v-model="outputDialog"
      persistent
    >
      <q-card style="min-width: 460px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ outputEditing ? t('channels.editOutput') : t('channels.addOutput') }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input
            v-model="outputForm.name"
            :label="t('channels.outputName')"
            autofocus
          />
          <q-select
            v-model="outputForm.mode"
            :options="outputModeOptions"
            :label="t('channels.outputMode')"
            emit-value
            map-options
            dense
          />
          <q-select
            v-model="outputForm.connector"
            :options="connectorOptions"
            :label="t('channels.patchPoint.connector')"
            clearable
          />
          <q-input
            v-model="outputForm.notes"
            :label="t('channels.fieldNotes')"
            type="textarea"
            autogrow
          />
          <div class="row items-center q-mt-sm q-mb-xs">
            <div class="text-subtitle2">
              {{ t('channels.patchPoints') }}
            </div>
            <q-space />
            <q-btn
              v-if="busConnectorOptions.length"
              flat
              dense
              size="sm"
              icon="call_split"
              :label="t('channels.addPointsForConnectors')"
              @click="addPointsForConnectors"
            />
          </div>
          <div class="text-caption text-primary q-mb-xs">
            {{ t('channels.patchPoint.orderHint') }}
          </div>
          <q-list
            bordered
            separator
          >
            <q-item
              v-for="(pt, pidx) in outputPoints"
              :key="pt.id || `op-${pidx}`"
            >
              <q-item-section>
                <div class="row q-gutter-sm items-center">
                  <q-select
                    v-model="pt.point_type"
                    :options="patchPointTypeOptions"
                    :label="t('channels.patchPoint.type')"
                    emit-value
                    map-options
                    dense
                    style="width: 150px"
                  />
                  <q-select
                    v-model="pt.name"
                    :options="patchNameOptions"
                    :label="t('channels.patchPoint.name')"
                    :hint="t('channels.patchPoint.nameHint')"
                    dense
                    use-input
                    new-value-mode="add-unique"
                    clearable
                    class="col"
                  />
                  <q-select
                    v-model="pt.connector"
                    :options="connectorOptions"
                    :label="t('channels.patchPoint.connector')"
                    :hint="t('channels.patchPoint.connectorHint')"
                    dense
                    clearable
                    style="width: 120px"
                  />
                  <q-input
                    v-model="pt.patch_label"
                    :label="t('channels.patchPoint.label')"
                    :hint="t('channels.patchPoint.labelHint')"
                    dense
                    style="width: 110px"
                  />
                </div>
                <StockwireProductPicker
                  v-model="pt.stockwire_product"
                  :gear-type="pointGearType(pt.point_type)"
                  :label="t('stockwire.selectPatch')"
                  :hint="pt.stockwire_product ? pt.stockwire_product.sku : ''"
                  class="q-mt-xs"
                />
                <q-input
                  v-model="pt.notes"
                  :label="t('channels.patchPoint.notes')"
                  dense
                  type="textarea"
                  autogrow
                  class="q-mt-xs"
                />
                <div class="row q-gutter-sm items-center q-mt-xs">
                  <q-select
                    v-model="pt.parentLocalId"
                    :options="connectFromOptions(pidx)"
                    :label="t('channels.patchPoint.connectsFrom')"
                    emit-value
                    map-options
                    dense
                    style="width: 200px"
                    @update:model-value="(v) => onConnectFromChange(pt, v)"
                  />
                  <q-select
                    v-if="busConnectorOptions.length"
                    v-model="pt.bus_connector"
                    :options="busConnectorOptions"
                    :label="t('channels.patchPoint.connectorTag')"
                    emit-value
                    map-options
                    dense
                    clearable
                    style="width: 130px"
                  />
                </div>
              </q-item-section>
              <q-item-section side>
                <div class="column">
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="arrow_upward"
                    :disable="pidx === 0"
                    @click="moveOutputPoint(pidx, -1)"
                  />
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="arrow_downward"
                    :disable="pidx === outputPoints.length - 1"
                    @click="moveOutputPoint(pidx, 1)"
                  />
                  <q-btn
                    dense
                    flat
                    round
                    size="sm"
                    icon="delete"
                    color="negative"
                    @click="removeOutputPoint(pidx)"
                  />
                </div>
              </q-item-section>
            </q-item>
          </q-list>
          <q-btn
            class="q-mt-sm"
            dense
            flat
            icon="add"
            :label="t('channels.patchPoint.add')"
            @click="addOutputPoint"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
            color="primary"
          />
          <q-btn
            flat
            :label="t('app.actions.save')"
            color="primary"
            @click="saveOutput"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
    <!-- Signal flow dialog -->
    <q-dialog
      v-model="flowDialog"
      full-width
    >
      <q-card>
        <q-card-section class="text-h6">
          {{ t('channels.signalFlow') }}
        </q-card-section>
        <q-card-section>
          <div
            v-if="flowKind === 'input' && flowLinear.length"
            class="flow-linear column items-center"
          >
            <template
              v-for="(n, i) in flowLinear"
              :key="n.id || i"
            >
              <q-card
                flat
                bordered
                class="flow-node q-pa-xs text-center"
              >
                <div class="text-body2">
                  {{ n.name || '—' }}
                </div>
                <div
                  v-if="n.ptype"
                  class="text-caption text-grey-7"
                >
                  {{ n.ptype }}
                </div>
                <div class="text-caption text-grey-7">
                  {{ [n.connector, n.patch_label].filter(Boolean).join(' · ') || '—' }}
                </div>
                <div
                  v-if="n.connectorTag"
                  class="text-caption text-grey-7"
                >
                  {{ n.connectorTag }}
                </div>
                <div
                  v-if="n.meta"
                  class="text-caption text-grey-7"
                >
                  {{ n.meta }}
                </div>
                <div
                  v-if="n.notes"
                  class="text-caption text-grey-7"
                >
                  <TruncateText :text="n.notes" />
                </div>
              </q-card>
              <div
                v-if="i < flowLinear.length - 1"
                class="flow-linear-connector"
              >
                <q-icon name="arrow_downward" />
              </div>
            </template>
          </div>
          <FlowTree
            v-else-if="flowTree"
            :node="flowTree"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.close')"
            color="primary"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import TruncateText from '@/components/TruncateText.vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/boot/api'
import { useChannelsStore } from '@/stores/channels'
import { useAuthStore } from '@/stores/auth'
import { useStockwireStore } from '@/stores/stockwire'
import DateTimePicker from '@/components/DateTimePicker.vue'
import MarkdownText from '@/components/MarkdownText.vue'
import FlowTree from '@/components/FlowTree.vue'
import StockwireProductPicker from '@/components/StockwireProductPicker.vue'
import ColumnChooser from '@/components/ColumnChooser.vue'
import { useColumnPrefs } from '../composables/useColumnPrefs'

const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const route = useRoute()
const store = useChannelsStore()
const authStore = useAuthStore()
const stockwire = useStockwireStore()

const job = ref(null)
const jobError = ref(null)
const split = ref(28)
const channelDialog = ref(false)
const bulkDialog = ref(false)
const editingChannel = ref(null)
const listDialog = ref(false)
const listEditing = ref(null)
const listName = ref('')
const exportDialog = ref(false)
const exportList = ref(null)
const exportPlugins = ref([])
const exportSelected = ref(null)
const exportError = ref(null)
const exportLoading = ref(false)
const mixerDialog = ref(false)
const mixerList = ref(null)
const mixerProduct = ref(null)
const mixerInputs = ref(null)
const mixerBuses = ref(null)
const mixerSuggestions = ref([])
const mixerSuggesting = ref(false)
const mixerSpecNote = ref('')
const outputDialog = ref(false)
const outputEditing = ref(null)
const outputListId = ref(null)
const outputForm = reactive({ name: '', mode: 'mono', connector: null, notes: '' })
const outputPoints = ref([])
const outputOriginalIds = ref(new Set())
const flowDialog = ref(false)
const flowSource = ref(null)
const jobDialog = ref(false)
const jobForm = reactive({ title: '', venue_name: '', event_date: '', notes: '', stockwire_job_id: '' })
const pushing = ref(false)
const linking = ref(false)
const pushMessage = ref('')
const pushError = ref(false)
const pagination = ref({
  rowsPerPage: 100,
  sortBy: 'channel_number',
  descending: false,
})

const inputTypeOptions = [
  { label: t('channels.type.microphone'), value: 'microphone' },
  { label: t('channels.type.di'), value: 'di' },
  { label: t('channels.type.wireless'), value: 'wireless' },
  { label: t('channels.type.fxReturn'), value: 'fxReturn' },
]


const columns = [
  { name: 'channel_number', label: t('channels.fieldChannelNumber'), field: 'channel_number', align: 'left', style: 'width: 60px' },
  { name: 'source_label', label: t('channels.fieldSource'), field: 'source_label', align: 'left' },
  { name: 'input_type', label: t('channels.type.label'), field: 'input_type', align: 'left', format: (v) => (v ? t(`channels.type.${v}`) : '') },
  { name: 'device', label: t('channels.fieldDevice'), field: 'device', align: 'left' },
  { name: 'phantom', label: t('channels.fieldPhantom'), field: 'phantom_power', align: 'center', style: 'width: 70px' },
  { name: 'stereo', label: t('channels.fieldStereo'), field: 'stereo', align: 'center', style: 'width: 60px' },
  { name: 'notes', label: t('channels.fieldNotes'), field: 'notes', align: 'left' },
  { name: 'connector', label: t('channels.fieldConnector'), field: 'connector', align: 'left', defaultHidden: true },
  { name: 'stand', label: t('stockwire.selectStand'), field: 'stand_product_name', align: 'left', defaultHidden: true },
  { name: 'patch_count', label: t('columns.in.patches'), field: (row) => (row.patch_points || []).length, align: 'center', style: 'width: 80px', defaultHidden: true },
  { name: 'actions', label: '', field: 'actions', align: 'right', style: 'width: 80px', locked: true },
]

const channelPrefs = useColumnPrefs('stagewire.cols.inputs', columns)
const channelColumns = channelPrefs.visible

const outputColumns = [
  { name: 'name', label: t('columns.out.name'), field: 'name', align: 'left' },
  { name: 'device', label: t('columns.out.device'), field: 'device', align: 'left' },
  { name: 'point_type', label: t('columns.out.type'), field: 'point_type', align: 'left' },
  { name: 'connector', label: t('columns.out.connector'), field: 'connector', align: 'left' },
  { name: 'patch_label', label: t('columns.out.patch'), field: 'patch_label', align: 'left' },
  { name: 'notes', label: t('columns.out.notes'), field: 'notes', align: 'left' },
  { name: 'bus_connector', label: t('columns.out.busConnector'), field: 'bus_connector', align: 'left', defaultHidden: true },
  { name: 'parallel', label: t('columns.out.parallel'), field: 'parallel', align: 'center', format: (v) => (v ? '✓' : ''), defaultHidden: true },
  { name: 'actions', label: '', field: 'actions', align: 'right', style: 'width: 60px', locked: true },
]

const outputPrefs = useColumnPrefs('stagewire.cols.outputs', outputColumns)
const outputTableColumns = outputPrefs.visible

function outputCellDisplay(col, point) {
  if (col.name === 'device' || col.name === 'actions') return ''
  const raw =
    typeof col.field === 'function' ? col.field(point) : point[col.field]
  const value = col.format ? col.format(raw, point) : raw
  return value == null ? '' : String(value)
}

const connectorOptions = [
  'XLR',
  'TRS',
  'TS',
  'Jack',
  'AES/EBU',
  'Dante',
  'Analog',
  'Optical',
  'Speakon',
  'BNC',
  'Ethernet',
  'Cat5e',
  'Cat6',
  'dsnake',
  'AES50',
  'MADI',
  'AVB',
  'Optocore',
  'Network',
]

const listOptions = computed(() =>
  store.lists.map((l) => ({ label: l.name, value: l.id })),
)

const outputModeOptions = [
  { label: t('channels.outputModeMono'), value: 'mono' },
  { label: t('channels.outputModeStereo'), value: 'stereo' },
  { label: t('channels.outputMode51'), value: '5.1' },
  { label: t('channels.outputMode71'), value: '7.1' },
  { label: t('channels.outputMode712'), value: '7.1.2' },
  { label: t('channels.outputModeOther'), value: 'other' },
]

const emptyForm = () => ({
  channel_number: store.channels.length ? Math.max(...store.channels.map((c) => c.channel_number || 0)) + 1 : 1,
  source_label: '',
  input_type: null,
  connector: null,
  device: '',
  phantom_power: false,
  stereo: false,
  stereo_channel: null,
  notes: '',
  stockwire_product: null,
  stand_product: null,
})

const sourceGearType = computed(() => {
  const map = { microphone: 'microphone', di: 'di', wireless: 'wireless' }
  return map[form.input_type] || null
})

function pointGearType(pointType) {
  if (!pointType) return null
  if (pointType.includes('stagebox')) return 'stagebox'
  if (pointType === 'mixer') return 'mixer'
  if (pointType === 'split') return 'stagebox'
  if (pointType === 'speaker') return 'speaker'
  if (pointType === 'monitor') return 'monitor'
  return null
}
const form = reactive(emptyForm())
const bulk = reactive({
  quantity: 8,
  startChannel: 1,
  prefix: '',
  type: null,
  device: '',
  phantom: false,
  stereo: false,
})

const patchPointTypeOptions = [
  { label: t('channels.patchPoint.typeMixer'), value: 'mixer' },
  { label: t('channels.patchPoint.typeAnalog'), value: 'analog_stagebox' },
  { label: t('channels.patchPoint.typeDigital'), value: 'digital_stagebox' },
  { label: t('channels.patchPoint.typeSplit'), value: 'split' },
  { label: t('channels.patchPoint.typeNetwork'), value: 'network' },
  { label: t('channels.patchPoint.typeDirect'), value: 'direct' },
  { label: t('channels.patchPoint.typeSpeaker'), value: 'speaker' },
  { label: t('channels.patchPoint.typeMonitor'), value: 'monitor' },
  { label: t('channels.patchPoint.typeRecorder'), value: 'recorder' },
  { label: t('channels.patchPoint.typeAmp'), value: 'amp' },
  { label: t('channels.patchPoint.typeStage'), value: 'stage' },
  { label: t('channels.patchPoint.typeOther'), value: 'other' },
]
const patchPoints = ref([])
const patchOriginalIds = ref(new Set())

const patchNameOptions = computed(() => {
  const names = new Set()
  for (const list of store.lists) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        if (p.name) names.add(p.name)
      }
    }
    for (const out of list.outputs || []) {
      for (const p of out.points || []) {
        if (p.name) names.add(p.name)
      }
    }
  }
  return Array.from(names).sort()
})

function addPatchPoint() {
  patchPoints.value.push({
    point_type: 'mixer',
    name: '',
    connector: form.connector || '',
    patch_label: form.channel_number ? String(form.channel_number) : '',
    notes: '',
    stockwire_product: null,
  })
}

function ensureDefaultMixerPoint() {
  if (patchPoints.value.length === 0) {
    patchPoints.value.push({
      point_type: 'mixer',
      name: 'Mixer',
      connector: form.connector || '',
      patch_label: form.channel_number ? String(form.channel_number) : '',
      notes: '',
    })
  }
}

watch(
  () => form.connector,
  (val) => {
    const mixer = patchPoints.value.find((p) => p.name === 'Mixer' && !p.id && !p.connector)
    if (mixer && val) mixer.connector = val
  },
)

function removePatchPoint(idx) {
  patchPoints.value.splice(idx, 1)
}

function movePatchPoint(idx, dir) {
  const target = idx + dir
  if (target < 0 || target >= patchPoints.value.length) return
  const arr = patchPoints.value
  const tmp = arr[idx]
  arr[idx] = arr[target]
  arr[target] = tmp
}

function openChannelDialog(channel = null) {
  editingChannel.value = channel
  Object.assign(form, emptyForm())
  if (channel) {
    Object.assign(form, {
      channel_number: channel.channel_number,
      source_label: channel.source_label,
      input_type: channel.input_type,
      connector: channel.connector,
      device: channel.device,
      phantom_power: channel.phantom_power,
      stereo: channel.stereo,
      stereo_channel: channel.stereo_channel,
      notes: channel.notes,
      stockwire_product: (channel.stockwire_product_name || channel.device)
        ? {
            id: channel.stockwire_product_id || null,
            name: channel.stockwire_product_name || channel.device,
          }
        : null,
      stand_product: channel.stand_product_name
        ? { id: channel.stand_product_id || null, name: channel.stand_product_name }
        : null,
    })
    patchPoints.value = (channel.patch_points || []).map((p) => ({
      ...p,
      stockwire_product: p.stockwire_product_name
        ? { id: p.stockwire_product_id || null, name: p.stockwire_product_name }
        : null,
    }))
  } else {
    patchPoints.value = []
  }
  ensureDefaultMixerPoint()
  patchOriginalIds.value = new Set(
    patchPoints.value.filter((p) => p.id).map((p) => p.id),
  )
  channelDialog.value = true
}

function onStereoToggle(val) {
  if (val && !form.stereo_channel) {
    form.stereo_channel =
      Number(form.channel_number) % 2 === 0
        ? Number(form.channel_number) - 1
        : Number(form.channel_number) + 1
  }
  if (!val) {
    form.stereo_channel = null
  }
}

function stripSuffix(label) {
  return (label || '').replace(/\s+(L|R)$/, '')
}

function stereoView(row) {
  if (!row.stereo || !row.stereo_channel) return { linked: false }
  const isL = row.channel_number < row.stereo_channel
  const rows = store.channels
  const idx = rows.findIndex((r) => r.id === row.id)
  const partner = rows.find((r) => r.channel_number === row.stereo_channel)
  const top = isL && rows[idx + 1] && rows[idx + 1].id === partner?.id
  const bottom = !isL && rows[idx - 1] && rows[idx - 1].id === partner?.id
  return { linked: true, isL, top, bottom }
}

function stereoTitle(row) {
  return t('channels.stereoLinkedTo', { ch: row.stereo_channel })
}

async function saveChannel() {
  const payload = {
    ...form,
    device: form.stockwire_product?.name || null,
    stockwire_product_id: form.stockwire_product?.id || null,
    stockwire_product_name: form.stockwire_product?.name || null,
    stand_product_id: form.stand_product?.id || null,
    stand_product_name: form.stand_product?.name || null,
  }
  if (editingChannel.value) {
    await store.updateChannel(route.params.jobId, editingChannel.value.id, payload)
  } else {
    const created = await store.createChannel(
      route.params.jobId,
      store.selectedListId,
      payload,
    )
    editingChannel.value = created
  }
  const channelId = editingChannel.value.id
  const mainNum = Number(form.channel_number)
  for (const p of patchPoints.value) {
    const body = {
      position: patchPoints.value.indexOf(p),
      point_type: p.point_type,
      name: p.name,
      connector: p.connector,
      patch_label: p.patch_label,
      notes: p.notes,
      stockwire_product_id: p.stockwire_product?.id || null,
      stockwire_product_name: p.stockwire_product?.name || null,
    }
    if (p.id && patchOriginalIds.value.has(p.id)) {
      await store.updatePatchPoint(route.params.jobId, channelId, p.id, body)
    } else if (!p.id) {
      await store.createPatchPoint(route.params.jobId, channelId, body)
    }
  }
  for (const id of patchOriginalIds.value) {
    if (!patchPoints.value.some((p) => p.id === id)) {
      await store.deletePatchPoint(route.params.jobId, channelId, id)
    }
  }

  if (form.stereo) {
    let partnerNum = Number(form.stereo_channel)
    if (!partnerNum) {
      partnerNum = mainNum % 2 === 0 ? mainNum - 1 : mainNum + 1
    }
    let partner = store.channels.find(
      (c) => c.id !== channelId && c.channel_number === partnerNum,
    )
    if (!partner) {
      const created = await store.createChannel(route.params.jobId, store.selectedListId, {
        channel_number: partnerNum,
        source_label: '',
        input_type: null,
        connector: null,
        device: '',
        phantom_power: false,
        stereo: false,
      })
      partner = created
    }
    if (!partner.patch_points || partner.patch_points.length === 0) {
      await store.createPatchPoint(route.params.jobId, partner.id, {
        position: 0,
        point_type: 'mixer',
        name: 'Mixer',
        connector: form.connector || '',
        patch_label: '',
        notes: '',
      })
    }
    const lowerIsMain = mainNum < partnerNum
    const base = stripSuffix(form.source_label) || `Input ${mainNum}`
    const mainLabel = base + (lowerIsMain ? ' L' : ' R')
    const partnerLabel = base + (lowerIsMain ? ' R' : ' L')
    await store.updateChannel(route.params.jobId, channelId, {
      stereo: true,
      stereo_channel: partnerNum,
      source_label: mainLabel,
    })
    await store.updateChannel(route.params.jobId, partner.id, {
      stereo: true,
      stereo_channel: mainNum,
      source_label: partnerLabel,
      input_type: form.input_type,
      connector: form.connector,
      device: form.device,
      phantom_power: form.phantom_power,
    })
  } else if (form.stereo_channel) {
    const partner = store.channels.find(
      (c) => c.id !== channelId && c.channel_number === form.stereo_channel,
    )
    if (partner) {
      await store.updateChannel(route.params.jobId, partner.id, {
        stereo: false,
        stereo_channel: null,
      })
    }
  }

  channelDialog.value = false
}

const bulkOutputDialog = ref(false)
const bulkOut = reactive({
  quantity: 4,
  startNumber: 1,
  prefix: 'Out',
  mode: 'stereo',
  connector: null,
})

function openBulkOutputs() {
  bulkOutputDialog.value = true
}

async function saveBulkOutputs() {
  const listId = store.selectedList?.id
  if (!listId) return
  const jobId = route.params.jobId
  const qty = Math.max(0, Number(bulkOut.quantity) || 0)
  const start = Number(bulkOut.startNumber) || 1
  const connectors = busConnectors(bulkOut.mode)
  for (let i = 0; i < qty; i++) {
    const num = start + i
    const created = await store.createOutput(jobId, listId, {
      name: `${bulkOut.prefix || 'Out'} ${num}`.trim(),
      mode: bulkOut.mode,
      connector: bulkOut.connector,
      notes: '',
    })
    for (const [pos, c] of connectors.entries()) {
      await store.createOutputPoint(jobId, listId, created.id, {
        position: pos,
        point_type: 'mixer',
        name: '',
        connector: bulkOut.connector || '',
        patch_label: '',
        notes: '',
        parallel: false,
        parent_id: null,
        bus_connector: c,
      })
    }
  }
  bulkOutputDialog.value = false
}

async function saveBulk() {
  const qty = Number(bulk.quantity) || 0
  const start = Number(bulk.startChannel) || 1
  for (let i = 0; i < qty; i++) {
    const num = start + i
    const payload = {
      channel_number: num,
      source_label: bulk.prefix ? `${bulk.prefix} ${i + 1}` : `Input ${num}`,
      input_type: bulk.type,
      device: bulk.device,
      phantom_power: bulk.phantom,
      stereo: false,
    }
    const created = await store.createChannel(route.params.jobId, store.selectedListId, payload)
    await store.createPatchPoint(route.params.jobId, created.id, {
      position: 0,
      point_type: 'mixer',
      name: 'Mixer',
      connector: '',
      patch_label: '',
      notes: '',
    })
  }
  bulkDialog.value = false
}

async function selectList(listId) {
  await store.selectList(route.params.jobId, listId)
}

function deviceModel(row) {
  const name = row.stockwire_product_name || row.device
  if (!name) return null
  return { id: row.stockwire_product_id || null, name }
}

function gearTypeForInput(inputType) {
  const map = { microphone: 'microphone', di: 'di', wireless: 'wireless' }
  return map[inputType] || null
}

function standModel(row) {
  if (!row.stand_product_name) return null
  return { id: row.stand_product_id || null, name: row.stand_product_name }
}

function saveStand(row, product) {
  const name = product?.name || null
  store.updateChannel(route.params.jobId, row.id, {
    stand_product_id: product?.id || null,
    stand_product_name: name,
  })
}

function saveDevice(row, product) {
  const name = product?.name || null
  store.updateChannel(route.params.jobId, row.id, {
    device: name,
    stockwire_product_id: product?.id || null,
    stockwire_product_name: name,
  })
}

function outputDeviceModel(row) {
  if (!row.stockwire_product_name) return null
  return { id: row.stockwire_product_id || null, name: row.stockwire_product_name }
}

function saveOutputDevice(bus, row, product) {
  if (!row.id) return
  const name = product?.name || null
  store.updateOutputPoint(route.params.jobId, store.selectedList.id, bus.id, row.id, {
    stockwire_product_id: product?.id || null,
    stockwire_product_name: name,
  })
}

function saveInline(row, field, value) {
  if (row[field] === value) return
  store.updateChannel(route.params.jobId, row.id, { [field]: value })
}

const channelCount = computed(() => {
  if (mixerList.value && store.selectedListId === mixerList.value.id) {
    return store.channels.length
  }
  return 0
})

function pickerObject(p) {
  return {
    id: String(p.id),
    name: p.name,
    sku: p.sku,
    brand: p.brand,
    manufacturer: p.manufacturer,
    category_id: p.category_id,
    category: null,
  }
}

async function loadMixerSpecs(product) {
  mixerSpecNote.value = ''
  if (!product?.id) return
  try {
    const prod = await stockwire.getProduct(product.id)
    const specs = prod?.specs || {}
    const inputs = specs.inputs ?? specs.sb_inputs ?? null
    const buses = specs.outputs ?? specs.sb_outputs ?? null
    if (inputs == null && buses == null) {
      mixerSpecNote.value = t('stockwire.mixerNoSpecs')
      return
    }
    if (inputs != null) mixerInputs.value = inputs
    if (buses != null) mixerBuses.value = buses
    mixerSpecNote.value = t('stockwire.mixerSpecsLoaded', {
      inputs: inputs ?? '–',
      buses: buses ?? '–',
    })
  } catch (err) {
    mixerSpecNote.value = `${t('stockwire.mixerSpecsError')} (${stockwireErrorText(err)})`
  }
}

// Picker or suggestion chose a mixer: set it, then load its inputs/buses from stockwire.
async function chooseMixer(product) {
  mixerProduct.value = product
  await loadMixerSpecs(product)
}

async function suggestMixer() {
  mixerSuggesting.value = true
  try {
    const cats = stockwire.categoriesForGearType('mixer')
    const need = channelCount.value || mixerInputs.value || 1
    const base = { min_inputs: need, limit: 10 }
    let items = []
    if (cats.length) {
      for (const id of cats) {
        const res = await stockwire.searchProducts({ ...base, category_id: id })
        items.push(...(res.items || []))
      }
    } else {
      const res = await stockwire.searchProducts(base)
      items = res.items || []
    }
    mixerSuggestions.value = items
  } catch {
    mixerSuggestions.value = []
  } finally {
    mixerSuggesting.value = false
  }
}

function applyMixerSuggestion(p) {
  mixerSuggestions.value = []
  chooseMixer(pickerObject(p))
}

function openMixer(list) {
  mixerList.value = list
  mixerSpecNote.value = ''
  if (list.mixer_product_id) {
    mixerProduct.value = {
      id: String(list.mixer_product_id),
      name: list.mixer_product_name,
      sku: null,
      brand: null,
      manufacturer: null,
      category_id: null,
      category: null,
    }
  } else if (list.mixer_product_name) {
    mixerProduct.value = {
      id: null,
      name: list.mixer_product_name,
      sku: null,
      brand: null,
      manufacturer: null,
      category_id: null,
      category: null,
    }
  } else {
    mixerProduct.value = null
  }
  mixerInputs.value = list.mixer_inputs ?? null
  mixerBuses.value = list.mixer_buses ?? null
  mixerSuggestions.value = []
  mixerDialog.value = true
}

function busChannelCount(mode) {
  return busConnectors(mode).length || 1
}

// Adds empty inputs/outputs so the list has at least as many as the mixer. Never removes.
async function fillMixerSlots(jobId, listId, wantInputs, wantBuses) {
  let addedInputs = 0
  let addedBuses = 0
  if (store.selectedListId === listId && wantInputs > store.channels.length) {
    const missing = wantInputs - store.channels.length
    const maxNum = store.channels.reduce((m, c) => Math.max(m, Number(c.channel_number) || 0), 0)
    for (let k = 1; k <= missing; k++) {
      await store.createChannel(jobId, listId, {
        channel_number: maxNum + k,
        source_label: '',
        input_type: null,
        device: '',
        phantom_power: false,
        stereo: false,
      })
      addedInputs++
    }
  }
  // Count buses in channels: a stereo output is two buses, a mono output is one.
  const current = store.lists.find((l) => l.id === listId)?.outputs || []
  const usedBuses = current.reduce((sum, out) => sum + busChannelCount(out.mode), 0)
  if (wantBuses > usedBuses) {
    const missing = wantBuses - usedBuses
    for (let k = 1; k <= missing; k++) {
      await store.createOutput(jobId, listId, {
        name: `Out ${current.length + k}`,
        mode: 'mono',
        connector: null,
        notes: '',
      })
      addedBuses++
    }
  }
  return { addedInputs, addedBuses }
}

async function saveMixer() {
  const list = mixerList.value
  if (!list) return
  const jobId = route.params.jobId
  await store.renameList(jobId, list.id, list.name, {
    mixer_product_id: mixerProduct.value?.id || null,
    mixer_product_name: mixerProduct.value?.name || null,
    mixer_inputs: mixerInputs.value ?? null,
    mixer_buses: mixerBuses.value ?? null,
  })
  const { addedInputs, addedBuses } = await fillMixerSlots(
    jobId,
    list.id,
    Number(mixerInputs.value) || 0,
    Number(mixerBuses.value) || 0,
  )
  if (addedInputs || addedBuses) {
    pushMessage.value = t('stockwire.mixerFilled', { inputs: addedInputs, buses: addedBuses })
    pushError.value = false
  }
  mixerDialog.value = false
}

function openNewList() {
  listEditing.value = null
  listName.value = ''
  listDialog.value = true
}

function openRenameList(list) {
  listEditing.value = list
  listName.value = list.name
  listDialog.value = true
}

async function openExport(list) {
  exportList.value = list
  exportSelected.value = null
  exportError.value = null
  exportPlugins.value = []
  exportDialog.value = true
  try {
    exportPlugins.value = await store.fetchExportPlugins(route.params.jobId, list.id)
  } catch (err) {
    exportError.value = err.message || t('common.errorOccurred')
  }
}

function selectedPluginExtension() {
  const p = exportPlugins.value.find((x) => x.key === exportSelected.value)
  return p?.file_extension || ''
}

async function downloadExportFile() {
  if (!exportList.value || !exportSelected.value) return
  exportError.value = null
  exportLoading.value = true
  try {
    const { data } = await store.downloadExport(
      route.params.jobId,
      exportList.value.id,
      exportSelected.value,
    )
    const ext = selectedPluginExtension()
    const filename = `${exportList.value.name}${ext}`
    const url = window.URL.createObjectURL(new Blob([data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    exportDialog.value = false
  } catch (err) {
    exportError.value = err.message || t('common.errorOccurred')
  } finally {
    exportLoading.value = false
  }
}

async function saveList() {
  const name = listName.value.trim()
  if (!name) return
  if (listEditing.value) {
    const cur = listEditing.value
    await store.renameList(route.params.jobId, cur.id, name, {
      mixer_product_id: cur.mixer_product_id ?? null,
      mixer_product_name: cur.mixer_product_name ?? null,
      mixer_inputs: cur.mixer_inputs ?? null,
      mixer_buses: cur.mixer_buses ?? null,
    })
  } else {
    await store.createList(route.params.jobId, name, {})
  }
  listDialog.value = false
}

function openJobDialog() {
  jobForm.title = job.value?.title || ''
  jobForm.venue_name = job.value?.venue_name || ''
  jobForm.event_date = job.value?.event_date || ''
  jobForm.notes = job.value?.notes || ''
  jobForm.stockwire_job_id = job.value?.stockwire_job_id || ''
  jobDialog.value = true
}

async function saveJob() {
  const payload = {
    title: jobForm.title,
    venue_name: jobForm.venue_name,
    event_date: jobForm.event_date || null,
    notes: jobForm.notes,
    stockwire_job_id: jobForm.stockwire_job_id || null,
  }
  const { data } = await api.patch(`/jobs/${route.params.jobId}`, payload)
  job.value = data
  jobDialog.value = false
}

function stockwireErrorText(err) {
  return err?.response?.data?.detail || err?.message || t('stockwire.noIntegration')
}

const linkDialog = ref(false)
const linkSearch = ref('')
const linkResults = ref([])
const linkLoading = ref(false)
let linkTimer = null

async function searchRentalJobs() {
  linkLoading.value = true
  try {
    const { data } = await api.get('/stockwire/rental-jobs', {
      params: { search: linkSearch.value?.trim() || undefined },
    })
    linkResults.value = data.items || []
  } catch (err) {
    linkResults.value = []
    pushError.value = true
    pushMessage.value = stockwireErrorText(err)
    linkDialog.value = false
  } finally {
    linkLoading.value = false
  }
}

function onLinkSearch() {
  if (linkTimer) clearTimeout(linkTimer)
  linkTimer = setTimeout(searchRentalJobs, 300)
}

function openLinkDialog() {
  linkSearch.value = ''
  linkResults.value = []
  linkDialog.value = true
  searchRentalJobs()
}

async function linkStockwire(existingId) {
  linking.value = true
  pushMessage.value = ''
  pushError.value = false
  try {
    const { data } = await api.post(
      `/stockwire/jobs/${route.params.jobId}/link`,
      { stockwire_job_id: existingId ? String(existingId) : null },
    )
    job.value = { ...job.value, stockwire_job_id: data.stockwire_job_id }
    linkDialog.value = false
    pushMessage.value = t('stockwire.linked', { id: data.stockwire_job_id })
  } catch (err) {
    pushError.value = true
    pushMessage.value = stockwireErrorText(err)
  } finally {
    linking.value = false
  }
}

async function openInStockwire() {
  pushMessage.value = ''
  pushError.value = false
  try {
    const url = await stockwire.jobDeeplink(route.params.jobId)
    window.open(url, '_blank')
  } catch (err) {
    pushError.value = true
    pushMessage.value = stockwireErrorText(err)
  }
}

async function pushToStockwire() {
  pushing.value = true
  pushMessage.value = ''
  pushError.value = false
  try {
    const { data } = await api.post(`/jobs/${route.params.jobId}/sync-stockwire`)
    const lines = [data.message]
    if (data.updated?.length) lines.push(t('stockwire.updatedLine', { items: data.updated.join(', ') }))
    if (data.removed?.length) lines.push(t('stockwire.removedLine', { items: data.removed.join(', ') }))
    if (data.added?.length) lines.push(t('stockwire.addedLine', { items: data.added.join(', ') }))
    if (data.errors?.length) {
      pushError.value = true
      lines.push(...data.errors)
    }
    pushMessage.value = lines.filter(Boolean).join(' · ')
  } catch (err) {
    pushError.value = true
    pushMessage.value = stockwireErrorText(err)
  } finally {
    pushing.value = false
  }
}

async function removeList(list) {
  if (window.confirm(t('channels.deleteListConfirm', { name: list.name }))) {
    await store.deleteList(route.params.jobId, list.id)
  }
}

async function removeChannel(row) {
  if (window.confirm(`${t('channels.deleteChannel')} "${row.source_label || row.channel_number}"?`)) {
    await store.deleteChannel(route.params.jobId, row.id)
  }
}

function busHeaderCaption(bus) {
  const base = busCaption(bus)
  const notes = (bus.notes || '').trim()
  if (!notes) return base
  const short = notes.length > 90 ? `${notes.slice(0, 90)}…` : notes
  return base ? `${base} · ${short}` : short
}

function busCaption(bus) {
  const mode = bus.mode === 'stereo' ? t('channels.outputModeStereo') : bus.mode === 'other' ? t('channels.outputModeOther') : t('channels.outputModeMono')
  return [mode, bus.connector].filter(Boolean).join(' · ')
}

function pointTypeLabel(value) {
  const opt = patchPointTypeOptions.find((o) => o.value === value)
  return opt ? opt.label : value
}

function busConnectors(mode) {
  switch (mode) {
    case 'stereo':
      return ['L', 'R']
    case '5.1':
      return ['L', 'R', 'C', 'LFE', 'Ls', 'Rs']
    case '7.1':
      return ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lb', 'Rb']
    case '7.1.2':
      return ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lb', 'Rb', 'Ltf', 'Rtf']
    default:
      return []
  }
}

const busConnectorOptions = computed(() => {
  const opts = busConnectors(outputForm.mode).map((c) => ({ label: c, value: c }))
  if (opts.length) opts.push({ label: t('channels.none'), value: null })
  return opts
})

function inputTypeLabel(v) {
  return v ? t(`channels.type.${v}`) : ''
}

function connectFromOptions(idx) {
  const opts = [{ label: t('channels.flowBusSource'), value: null }]
  for (let i = 0; i < idx; i++) {
    const p = outputPoints.value[i]
    const port = [p.connector, p.patch_label, p.bus_connector].filter(Boolean).join(' ')
    opts.push({ label: port ? `${p.name || `#${i + 1}`} — ${port}` : p.name || `#${i + 1}`, value: p.localId })
  }
  return opts
}

function onConnectFromChange(pt, value) {
  if (!value) {
    pt.bus_connector = null
    return
  }
  const parent = outputPoints.value.find((p) => p.localId === value)
  if (parent && parent.bus_connector) pt.bus_connector = parent.bus_connector
}

function openOutputDialog(listId, bus = null) {
  outputListId.value = listId
  outputEditing.value = bus
  Object.assign(outputForm, { name: '', mode: 'mono', connector: null, notes: '' })
  if (bus) {
    Object.assign(outputForm, {
      name: bus.name,
      mode: bus.mode || 'mono',
      connector: bus.connector,
      notes: bus.notes,
    })
    outputPoints.value = (bus.points || []).map((p) => ({
      ...p,
      localId: p.id,
      parentLocalId: p.parent_id || null,
      stockwire_product: p.stockwire_product_name
        ? { id: p.stockwire_product_id || null, name: p.stockwire_product_name }
        : null,
    }))
  } else {
    outputPoints.value = []
  }
  outputOriginalIds.value = new Set(
    outputPoints.value.filter((p) => p.id).map((p) => p.id),
  )
  outputDialog.value = true
}

function addOutputPoint() {
  outputPoints.value.push({
    localId: crypto.randomUUID(),
    parentLocalId: null,
    point_type: 'mixer',
    name: '',
    connector: outputForm.connector || '',
    patch_label: '',
    notes: '',
    bus_connector: null,
    stockwire_product: null,
  })
}

function addPointsForConnectors() {
  for (const c of busConnectors(outputForm.mode)) {
    outputPoints.value.push({
      localId: crypto.randomUUID(),
      parentLocalId: null,
      point_type: 'mixer',
      name: '',
      connector: outputForm.connector || '',
      patch_label: '',
      notes: '',
      bus_connector: c,
    })
  }
}

function removeOutputPoint(idx) {
  outputPoints.value.splice(idx, 1)
}

function moveOutputPoint(idx, dir) {
  const target = idx + dir
  if (target < 0 || target >= outputPoints.value.length) return
  const arr = outputPoints.value
  const tmp = arr[idx]
  arr[idx] = arr[target]
  arr[target] = tmp
}

async function saveOutput() {
  const jobId = route.params.jobId
  const listId = outputListId.value
  let outputId = outputEditing.value?.id
  if (!outputId) {
    const created = await store.createOutput(jobId, listId, {
      name: outputForm.name || 'Output',
      mode: outputForm.mode || 'mono',
      connector: outputForm.connector,
      notes: outputForm.notes,
    })
    outputId = created.id
  } else {
    await store.updateOutput(jobId, listId, outputId, {
      name: outputForm.name,
      mode: outputForm.mode || 'mono',
      connector: outputForm.connector,
      notes: outputForm.notes,
    })
  }
  const idMap = {}
  for (let i = 0; i < outputPoints.value.length; i++) {
    const p = outputPoints.value[i]
    const parentId = p.parentLocalId ? idMap[p.parentLocalId] || null : null
    const body = {
      position: i,
      point_type: p.point_type,
      name: p.name,
      connector: p.connector,
      patch_label: p.patch_label,
      notes: p.notes,
      parallel: !!p.parallel,
      parent_id: parentId,
      bus_connector: p.bus_connector || null,
      stockwire_product_id: p.stockwire_product?.id || null,
      stockwire_product_name: p.stockwire_product?.name || null,
    }
    if (p.id && outputOriginalIds.value.has(p.id)) {
      await store.updateOutputPoint(jobId, listId, outputId, p.id, body)
      idMap[p.localId] = p.id
    } else if (!p.id) {
      const created = await store.createOutputPoint(jobId, listId, outputId, body)
      idMap[p.localId] = created.id
    }
  }
  for (const pid of outputOriginalIds.value) {
    if (!outputPoints.value.some((p) => p.id === pid)) {
      await store.deleteOutputPoint(jobId, listId, outputId, pid)
    }
  }
  outputDialog.value = false
}

async function removeOutput(listId, bus) {
  if (window.confirm(`${t('channels.deleteOutputConfirm')} "${bus.name}"?`)) {
    await store.deleteOutput(route.params.jobId, listId, bus.id)
  }
}

function openFlow(kind, obj) {
  flowSource.value = { kind, obj }
  flowDialog.value = true
}

const flowKind = computed(() => flowSource.value?.kind || 'output')

const flowLinear = computed(() => {
  const t = flowTree.value
  if (!t) return []
  return [t, ...(t.children || [])]
})

const flowTree = computed(() => {
  const src = flowSource.value
  if (!src) return null
  const { kind, obj } = src
  if (kind === 'input') {
    const srcLabel = obj.source_label || `${t('channels.fieldChannelNumber')} ${obj.channel_number}`
    const metaParts = [obj.device, inputTypeLabel(obj.input_type)].filter(Boolean)
    if (obj.phantom_power) metaParts.push(t('channels.bulk.phantom'))
    if (obj.stereo) metaParts.push(`${t('channels.bulk.stereo')}${obj.stereo_channel ? ' ' + obj.stereo_channel : ''}`)
    const srcMeta = metaParts.join(' · ')
    const root = {
      id: 'src',
      name: srcLabel,
      connector: obj.connector,
      patch_label: '',
      notes: obj.notes || '',
      meta: srcMeta,
      children: [],
    }
    let prev = root
    for (const p of obj.patch_points || []) {
      if (!p.name) continue
      const node = {
        id: p.id,
        name: p.name,
        connector: p.connector,
        patch_label: p.patch_label,
        notes: p.notes,
        ptype: pointTypeLabel(p.point_type),
        children: [],
      }
      prev.children.push(node)
      prev = node
    }
    return root
  }
  const busLabel = obj.name
  const root = {
    id: 'bus',
    name: busLabel,
    connector: obj.connector,
    patch_label: '',
    notes: obj.notes || '',
    meta: obj.mode && obj.mode !== 'mono' ? modeLabel(obj.mode) : '',
    children: [],
  }
  const points = (obj.points || []).filter((p) => p.name).slice().sort((a, b) => a.position - b.position)
  const byId = new Map()
  for (const p of points) {
    byId.set(p.id, {
      id: p.id,
      name: p.name,
      connector: p.connector,
      patch_label: p.patch_label,
      notes: p.notes,
      ptype: pointTypeLabel(p.point_type),
      connectorTag: p.bus_connector || '',
      children: [],
    })
  }
  for (const p of points) {
    const node = byId.get(p.id)
    let parent = p.parent_id ? byId.get(p.parent_id) : null
    if (!parent) {
      if (p.parallel) {
        const idx = points.indexOf(p)
        parent = idx > 0 ? byId.get(points[idx - 1].id) : root
      } else {
        parent = root
      }
    }
    parent.children.push(node)
  }
  return root
})

function formatDate(value) {
  return new Date(value).toLocaleString()
}

let ws = null
let wsRetry = null
let wsClosed = false

function connectWs() {
  const token = authStore.token
  if (!token || ws) return
  const base = (api.defaults.baseURL || '').replace(/^http/, 'ws')
  const url = `${base}/ws/jobs/${route.params.jobId}?token=${encodeURIComponent(token)}`
  ws = new WebSocket(url)
  ws.onmessage = (ev) => {
    try {
      const event = JSON.parse(ev.data)
      if (event.type === 'job.update') {
        job.value = event.payload
        return
      }
      store.applyRealtimeEvent(event)
    } catch {
      /* ignore malformed frames */
    }
  }
  ws.onclose = () => {
    ws = null
    if (!wsClosed) wsRetry = setTimeout(connectWs, 3000)
  }
  ws.onerror = () => {
    if (ws) ws.close()
  }
}

function disconnectWs() {
  wsClosed = true
  if (wsRetry) clearTimeout(wsRetry)
  if (ws) {
    ws.close()
    ws = null
  }
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/jobs/${route.params.jobId}`)
    job.value = data
  } catch {
    jobError.value = t('common.errorOccurred') || 'Job not found'
  }
  await store.fetchLists(route.params.jobId)
  connectWs()
})

onUnmounted(disconnectWs)
</script>

<style scoped>
.stereo-link-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 44px;
}
.stereo-line {
  width: 2px;
  background: var(--q-primary);
  flex: 1 1 auto;
  min-height: 10px;
}
.stereo-icon {
  margin: 2px 0;
}
.flow-stage-active {
  background: rgba(63, 135, 63, 0.12);
  border-radius: 8px;
  padding: 4px;
}
.flow-node {
  min-width: 96px;
}
.flow-linear {
  gap: 0;
}
.flow-linear-connector {
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(150, 150, 150, 0.7);
}
</style>
