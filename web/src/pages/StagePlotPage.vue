<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('stagePlot.back')"
        class="q-mr-sm"
        @click="goBackToJob"
      />
      <div class="col">
        <div class="text-h6">
          {{ t('stagePlot.title') }}
        </div>
        <div
          v-if="job"
          class="text-subtitle2 text-grey-7"
        >
          <span v-if="job.title">{{ job.title }}</span>
          <span v-if="job.venue_name"> · {{ job.venue_name }}</span>
        </div>
      </div>
    </div>

    <q-banner
      v-if="highlightIds.length"
      class="bg-accent text-white q-mb-md rounded-borders"
      dense
    >
      <template #avatar>
        <q-icon name="visibility" />
      </template>
      {{ t('stagePlot.highlightActive', { name: highlightLabel }) }}
      <template #action>
        <q-btn
          flat
          color="white"
          :label="t('stagePlot.highlightClear')"
          @click="clearHighlight"
        />
      </template>
    </q-banner>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-3">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('stagePlot.stageSetup') }}
            </div>
            <div
              v-if="job && job.venue_name"
              class="text-caption text-grey-7 q-mb-xs"
            >
              {{ job.venue_name }}
            </div>
            <div class="row q-gutter-sm">
              <q-input
                v-model.number="stageW"
                type="number"
                :label="t('stagePlot.stageWidth')"
                dense
                class="col"
                @change="saveStage"
              />
              <q-input
                v-model.number="stageH"
                type="number"
                :label="t('stagePlot.stageHeight')"
                dense
                class="col"
                @change="saveStage"
              />
            </div>
            <div class="text-caption text-grey-7 q-mt-xs">
              {{ t('stagePlot.stageUnitsHint') }}
            </div>
            <div class="text-subtitle2 q-mt-md">
              {{ t('stagePlot.venueSize') }}
            </div>
            <div class="row q-gutter-sm">
              <q-input
                v-model.number="venueW"
                type="number"
                :label="t('stagePlot.venueWidth')"
                dense
                class="col"
                @change="saveVenueSize"
              />
              <q-input
                v-model.number="venueH"
                type="number"
                :label="t('stagePlot.venueHeight')"
                dense
                class="col"
                @change="saveVenueSize"
              />
            </div>
            <div class="text-subtitle2 q-mt-sm">
              {{ t('stagePlot.stagePosition') }}
            </div>
            <div class="row q-gutter-sm">
              <q-input
                v-model.number="stageX"
                type="number"
                :label="t('stagePlot.stageX')"
                dense
                class="col"
                @change="saveStagePosition"
              />
              <q-input
                v-model.number="stageY"
                type="number"
                :label="t('stagePlot.stageY')"
                dense
                class="col"
                @change="saveStagePosition"
              />
            </div>
            <div class="text-caption text-grey-7 q-mt-xs">
              {{ t('stagePlot.venueHint') }}
            </div>
          </q-card-section>
        </q-card>

        <q-card
          flat
          bordered
          class="q-mt-md"
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('stagePlot.palette') }}
            </div>
            <q-list
              dense
              separator
            >
              <q-item
                v-for="(def, type) in palette"
                :key="type"
                v-ripple
                clickable
                @click="addElement(type)"
              >
                <q-item-section avatar>
                  <q-icon
                    :name="def.icon"
                    :style="{ color: def.color }"
                  />
                </q-item-section>
                <q-item-section>{{ paletteLabel(def) }}</q-item-section>
              </q-item>
              <q-item
                v-ripple
                clickable
                @click="startAudience"
              >
                <q-item-section avatar>
                  <q-icon name="groups" />
                </q-item-section>
                <q-item-section>{{ t('stagePlot.audienceDraw') }}</q-item-section>
              </q-item>
              <q-item
                v-ripple
                clickable
                @click="openSpeakerDialog"
              >
                <q-item-section avatar>
                  <q-icon name="speaker_group" />
                </q-item-section>
                <q-item-section>{{ t('stagePlot.addSpeakers') }}</q-item-section>
              </q-item>
              <q-item
                v-ripple
                clickable
                @click="addCustom"
              >
                <q-item-section avatar>
                  <q-icon name="add" />
                </q-item-section>
                <q-item-section>{{ t('stagePlot.custom') }}</q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>

        <q-card
          v-if="selected"
          flat
          bordered
          class="q-mt-md"
          @drop="onEditorDrop"
          @dragover.prevent
        >
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ t('stagePlot.element') }}
            </div>
            <q-input
              v-model="draft.label"
              :label="t('stagePlot.label')"
              dense
              @change="commitDraft"
            />
            <q-select
              v-model="draft.linked_channel_id"
              :label="t('stagePlot.linkChannel')"
              :options="channelOptions"
              emit-value
              map-options
              clearable
              dense
              class="q-mt-sm"
              @update:model-value="commitLink"
            />
            <q-select
              v-if="selected"
              v-model="draft.linked_video_input_id"
              :label="t('stagePlot.linkVideo')"
              :options="videoInputOptions"
              emit-value
              map-options
              clearable
              dense
              class="q-mt-sm"
              @update:model-value="commitVideoInput"
            />
            <template v-if="selected && selected.element_type === 'camera'">
              <q-select
                v-model="draft.linked_lens_device_id"
                :label="t('stagePlot.linkLens')"
                :options="lensOptions"
                emit-value
                map-options
                clearable
                dense
                class="q-mt-sm"
                @update:model-value="commitLens"
              />
              <div
                v-if="cameraSpec(selected) && cameraSpec(selected).focal_min_mm && cameraSpec(selected).focal_max_mm > cameraSpec(selected).focal_min_mm"
                class="q-mt-sm"
              >
                <div class="text-caption">
                  {{ t('stagePlot.focalLength') }}: {{ Math.round(cameraSpec(selected).focal_mm) }} mm
                </div>
                <q-slider
                  :model-value="cameraSpec(selected).focal_mm"
                  :min="cameraSpec(selected).focal_min_mm"
                  :max="cameraSpec(selected).focal_max_mm"
                  label
                  color="primary"
                  @change="commitFocal"
                />
              </div>
              <div class="text-caption text-grey-7 q-mt-xs">
                {{ cameraCaption(selected) }}
              </div>
            </template>
            <q-select
              v-if="!isSpeakerElement(selected)"
              v-model="draft.linked_device_id"
              :label="t('stagePlot.linkDevice')"
              :options="deviceOptions"
              emit-value
              map-options
              clearable
              dense
              class="q-mt-sm"
              @update:model-value="commitDevice"
            />
            <div
              v-if="draft.linked_channel_id || draft.linked_device_id"
              class="row q-gutter-sm q-mt-xs"
            >
              <q-btn
                v-if="draft.linked_channel_id"
                flat
                dense
                icon="open_in_new"
                :label="t('stagePlot.openChannel')"
                @click="openLinkedChannel"
              />
              <q-btn
                v-if="draft.linked_device_id && !isSpeakerElement(selected)"
                flat
                dense
                icon="open_in_new"
                :label="t('stagePlot.openDevice')"
                @click="openLinkedDevice"
              />
            </div>
            <div class="row q-gutter-sm q-mt-sm">
              <q-input
                v-model.number="draft.width_cm"
                type="number"
                :label="t('stagePlot.widthCm')"
                dense
                class="col"
                @update:model-value="commitSize"
              />
              <q-input
                v-model.number="draft.height_cm"
                type="number"
                :label="t('stagePlot.heightCm')"
                dense
                class="col"
                @update:model-value="commitSize"
              />
            </div>
            <div class="q-mt-sm">
              <q-file
                :model-value="null"
                accept="image/*"
                :label="t('stagePlot.imageUpload')"
                dense
                clearable
                :loading="uploading"
                @update:model-value="onImageFilePicked"
              >
                <template #append>
                  <q-icon name="image" />
                </template>
              </q-file>
              <div
                v-if="draft.image_url"
                class="row items-center q-gutter-sm q-mt-xs"
              >
                <img
                  :src="fullImageUrl(draft.image_url)"
                  alt=""
                  style="max-width: 160px; max-height: 110px; border-radius: 4px"
                >
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('stagePlot.removeImage')"
                  @click="clearImage"
                />
                <q-btn
                  flat
                  dense
                  icon="open_in_new"
                  type="a"
                  :href="fullImageUrl(draft.image_url)"
                  target="_blank"
                  rel="noopener"
                />
              </div>
              <div
                v-else
                class="text-caption text-grey-7 q-mt-xs"
              >
                {{ t('stagePlot.imageDropHint') }}
              </div>
            </div>
            <q-input
              v-model.number="draft.rotation"
              type="number"
              :label="t('stagePlot.rotation')"
              dense
              class="q-mt-sm"
              @update:model-value="commitRotation"
            />
            <div class="row q-gutter-xs q-mt-xs">
              <q-btn
                v-for="step in ROTATE_STEPS"
                :key="step"
                dense
                outline
                no-caps
                :label="rotateLabel(step)"
                @click="rotateBy(step)"
              />
            </div>
            <div
              v-if="isSpeakerElement(selected)"
              class="q-mt-sm"
            >
              <div class="text-subtitle2">
                {{ t('stagePlot.speakerSection') }}
              </div>
              <div class="row q-gutter-sm q-mt-xs">
                <q-input
                  v-model.number="draft.coverage_angle_h"
                  type="number"
                  :label="t('stagePlot.coverageAngle')"
                  dense
                  class="col"
                  @update:model-value="commitCoverage"
                />
                <q-input
                  v-model.number="draft.coverage_distance_m"
                  type="number"
                  :label="t('stagePlot.coverageDistance')"
                  dense
                  class="col"
                  @update:model-value="commitCoverage"
                />
              </div>
              <q-select
                v-model="draft.linked_output_point_id"
                :label="t('stagePlot.linkOutput')"
                :options="outputPointOptions"
                emit-value
                map-options
                clearable
                dense
                class="q-mt-sm"
                @update:model-value="commitOutputPoint"
              />
              <div
                v-if="speakerSpecs[selected.id]"
                class="text-caption text-grey-7 q-mt-xs"
              >
                {{
                  speakerSpecs[selected.id].source === 'stockwire'
                    ? t('stagePlot.specsFromStockwire', {
                      name: speakerSpecs[selected.id].product_name || '—',
                    })
                    : t('stagePlot.specsManual')
                }}
              </div>
            </div>
            <div class="row q-gutter-sm q-mt-sm">
              <q-input
                v-model.number="draft.position_x"
                type="number"
                :label="xLabel"
                dense
                class="col"
                @update:model-value="commitPosition"
              />
              <q-input
                v-model.number="draft.position_y"
                type="number"
                :label="yLabel"
                dense
                class="col"
                @update:model-value="commitPosition"
              />
            </div>
            <q-btn
              color="negative"
              class="full-width q-mt-md"
              :label="t('stagePlot.delete')"
              @click="removeSelected"
            />
          </q-card-section>
        </q-card>

        <q-card
          flat
          bordered
          class="q-mt-md"
        >
          <q-card-section>
            <div class="text-subtitle2 q-mb-xs">
              {{ t('stagePlot.units') }}
            </div>
            <q-btn-toggle
              v-model="unit"
              spread
              no-caps
              :options="unitOptions"
            />
            <div class="text-subtitle2 q-mt-sm q-mb-xs">
              {{ t('stagePlot.zoom') }}
            </div>
            <q-slider
              v-model="scale"
              :min="0.3"
              :max="1.5"
              :step="0.1"
              label
            />
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-9 order-first order-md-last">
        <q-card
          flat
          bordered
        >
          <q-card-section
            @drop="onStageDrop"
            @dragover.prevent
          >
            <div class="text-caption text-grey-7">
              {{ t('stagePlot.addHint') }}
            </div>
            <div class="row items-center q-gutter-sm q-mt-xs">
              <q-toggle
                v-model="showSoundCoverage"
                :label="t('stagePlot.showSoundCoverage')"
              />
              <q-toggle
                v-model="showCameraCoverage"
                :label="t('stagePlot.showCameraCoverage')"
              />
              <q-btn
                v-for="c in categoryOptions"
                :key="c.value"
                dense
                no-caps
                :outline="!visibleCategories.includes(c.value)"
                :color="visibleCategories.includes(c.value) ? 'primary' : 'grey-7'"
                :label="c.label"
                :aria-pressed="visibleCategories.includes(c.value) ? 'true' : 'false'"
                @click="toggleCategory(c.value)"
              />
              <div
                v-if="showSoundCoverage && !hasVenue"
                class="text-caption text-warning"
              >
                {{ t('stagePlot.coverageNoVenue') }}
              </div>
              <div
                v-else-if="showSoundCoverage && coverageLabel"
                class="text-caption"
              >
                {{ coverageLabel }}
              </div>
            </div>
            <div
              v-if="drawingAudience"
              class="row items-center q-gutter-sm q-mt-sm"
            >
              <div class="text-caption">
                {{ t('stagePlot.audienceHint') }}
              </div>
              <q-btn
                dense
                color="primary"
                :label="t('stagePlot.audienceFinish')"
                :disable="audiencePoints.length < 3"
                @click="finishAudience"
              />
              <q-btn
                dense
                flat
                :label="t('app.actions.cancel')"
                @click="cancelAudience"
              />
            </div>
            <div
              v-if="audienceShown.length >= 3 && !drawingAudience"
              class="row items-center q-gutter-sm q-mt-sm"
            >
              <div class="text-caption">
                {{ t('stagePlot.audienceShown') }}
              </div>
              <q-btn
                flat
                dense
                icon="delete"
                :label="t('stagePlot.audienceClear')"
                @click="clearAudience"
              />
              <q-btn
                v-if="job?.venue_id"
                flat
                dense
                icon="save"
                :label="t('stagePlot.audienceSaveVenue')"
                @click="saveAudienceToVenue"
              />
            </div>
            <div
              v-if="store.loading"
              class="q-my-md"
            >
              <q-spinner color="primary" />
            </div>
            <div
              v-else-if="!store.elements.length"
              class="text-grey-7 q-my-md"
            >
              {{ t('stagePlot.empty') }}
            </div>
            <v-stage
              v-if="!store.loading"
              ref="stageRef"
              :config="stageConfig"
              @click="onStageClick"
              @tap="onStageClick"
            >
              <v-layer>
                <v-rect :config="venueFrameConfig" />
                <v-image
                  v-if="bgImage"
                  :config="bgConfig"
                />
                <v-line
                  v-for="(g, i) in gridLines"
                  :key="'g' + i"
                  :config="g"
                />
                <v-image
                  v-if="coverageImage"
                  :config="coverageConfig"
                />
                <v-line
                  v-for="cv in cameraViews"
                  :key="'cam' + cv.id"
                  :config="cv.config"
                />
                <v-rect :config="stageBg" />
                <v-line
                  v-if="audienceShown.length >= 3"
                  :config="audienceConfig"
                />
                <v-text
                  v-if="audienceShown.length >= 3"
                  :config="audienceLabelConfig"
                />
                <v-line
                  v-if="drawingAudience && audiencePoints.length"
                  :config="audienceDraftConfig"
                />
                <v-line
                  v-for="w in cablePlan.cableways"
                  :key="'w' + w.id"
                  :config="cableWayConfig(w)"
                />
                <v-line
                  v-for="row in visibleCableRows"
                  :key="'c' + row.key"
                  :config="cableConfig(row)"
                />
                <v-line
                  v-if="drawingWay && drawPoints.length"
                  :config="drawConfig"
                />
                <v-circle
                  v-for="(p, i) in drawingWay ? drawPoints : []"
                  :key="'h' + i"
                  :config="pointHandleConfig(p, i)"
                />
                <v-circle
                  v-for="(wp, i) in rerouteWaypoints"
                  :key="'wp' + i"
                  :config="waypointConfig(wp)"
                />
                <v-group
                  v-for="el in visibleElements"
                  :key="el.id"
                  :config="groupConfig(el)"
                >
                  <v-wedge
                    v-if="showSoundCoverage && sectorFor(el)"
                    :config="wedgeConfig(el)"
                  />
                  <v-rect :config="rectConfig(el)" />
                  <v-image
                    v-if="imageFor(el)"
                    :config="imageConfig(el)"
                  />
                  <v-text :config="labelConfig(el)" />
                  <v-text
                    v-if="linkedSummary(el)"
                    :config="linkedTextConfig(el)"
                  />
                </v-group>
                <v-transformer
                  ref="trRef"
                  :config="transformerConfig"
                />
              </v-layer>
            </v-stage>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12">
        <q-card
          flat
          bordered
        >
          <q-card-section>
            <div class="row items-center q-gutter-sm">
              <div class="text-subtitle1 col">
                {{ t('cables.title') }}
              </div>
              <q-toggle
                v-model="cablesVisible"
                :label="t('cables.show')"
              />
              <q-btn
                flat
                dense
                icon="alt_route"
                :label="t('cables.drawWay')"
                :disable="drawingWay || drawingAudience || !!rerouteKey"
                @click="startDrawWay"
              />
              <q-btn
                flat
                dense
                icon="download"
                :label="t('cables.exportCsv')"
                :disable="!cableRows.length"
                @click="exportCables"
              />
            </div>
            <div
              v-if="drawingWay"
              class="row items-center q-gutter-sm q-mt-sm"
            >
              <div class="text-caption">
                {{ editingWayId ? t('cables.editHint') : t('cables.drawHint') }}
              </div>
              <q-btn
                dense
                outline
                no-caps
                icon="undo"
                :label="t('cables.undoPoint')"
                :disable="!drawPoints.length"
                @click="undoDrawPoint"
              />
              <q-btn
                dense
                color="primary"
                :label="editingWayId ? t('cables.saveWay') : t('cables.finishWay')"
                :disable="drawPoints.length < 2"
                @click="finishDrawWay"
              />
              <q-btn
                dense
                flat
                :label="t('app.actions.cancel')"
                @click="cancelDrawWay"
              />
            </div>
            <div
              v-if="rerouteRow"
              class="row items-center q-gutter-sm q-mt-sm"
            >
              <div class="text-caption">
                {{ t('cables.rerouteHint', { name: 'C' + rerouteRow.index }) }}
              </div>
              <q-btn
                dense
                flat
                :label="t('cables.undoWaypoint')"
                :disable="!rerouteWaypoints.length"
                @click="undoWaypoint"
              />
              <q-btn
                dense
                flat
                :label="t('cables.resetRoute')"
                @click="resetRoute(rerouteRow)"
              />
              <q-btn
                dense
                color="primary"
                :label="t('cables.doneReroute')"
                @click="rerouteKey = null"
              />
            </div>

            <div class="row q-col-gutter-md q-mt-xs">
              <q-input
                :model-value="cablePlan.settings.slack_pct"
                type="number"
                dense
                outlined
                :label="t('cables.slackPct')"
                class="col-12 col-sm-3"
                @update:model-value="(v) => saveCableSettings({ slack_pct: Number(v) || 0 })"
              />
              <q-input
                :model-value="cablePlan.settings.slack_m"
                type="number"
                dense
                outlined
                :label="t('cables.slackM')"
                class="col-12 col-sm-3"
                @update:model-value="(v) => saveCableSettings({ slack_m: Number(v) || 0 })"
              />
              <div class="col-12 col-sm-6">
                <div class="text-caption text-grey-7">
                  {{ t('cables.cablewayFactor') }}: {{ Number(cablePlan.settings.cableway_factor).toFixed(2) }}
                </div>
                <q-slider
                  :model-value="Number(cablePlan.settings.cableway_factor)"
                  :min="0.1"
                  :max="1"
                  :step="0.05"
                  label
                  color="primary"
                  @change="(v) => saveCableSettings({ cableway_factor: Number(v) })"
                />
              </div>
              <q-input
                :model-value="standardLengthsText"
                dense
                outlined
                :label="t('cables.standardLengths')"
                class="col-12 col-sm-6"
                @update:model-value="saveStandardLengths"
              />
            </div>

            <div
              v-if="cableOrder.length"
              class="q-mt-md"
            >
              <div class="text-subtitle2 q-mb-xs">
                {{ t('cables.order') }}
              </div>
              <q-chip
                v-for="o in cableOrder"
                :key="String(o.length)"
                dense
                color="primary"
                text-color="white"
              >
                {{ o.count }} × {{ o.length === 'over' ? t('cables.overMax') : `${o.length} m` }}
              </q-chip>
            </div>

            <div
              v-if="cableTypes.length"
              class="q-mt-md"
            >
              <div class="text-subtitle2 q-mb-xs">
                {{ t('cables.byType') }}
              </div>
              <div
                v-for="g in cableTypes"
                :key="g.type"
                class="text-body2"
              >
                <b>{{ g.type === 'unspecified' ? t('cables.unspecified') : g.type.toUpperCase() }}</b>
                · {{ g.total }} {{ t('cables.total') }}:
                <span
                  v-for="(l, li) in g.lengths"
                  :key="String(l.length)"
                >
                  {{ l.count }} × {{ l.length === 'over' ? t('cables.overMax') : `${l.length} m` }}<span v-if="li < g.lengths.length - 1">, </span>
                </span>
              </div>
            </div>

            <div class="text-caption text-grey-7 q-mt-md">
              {{ t('cables.actionsHint') }}
            </div>
            <q-list
              separator
              class="q-mt-xs"
            >
              <q-item
                v-for="row in cableRows"
                :key="row.key"
                :active="selectedCableKey === row.key || rerouteKey === row.key"
                clickable
                @click="selectedCableKey = row.key"
              >
                <q-item-section>
                  <q-item-label>
                    C{{ row.index }} · {{ row.fromName }} → {{ row.toName }}
                  </q-item-label>
                  <q-item-label caption>
                    {{ row.label }} · {{ row.connector || '—' }} ·
                    {{
                      row.placed
                        ? t(`cables.route.${row.mode}`)
                        : t('cables.missingOn', { name: row.missingName })
                    }}
                    <span
                      v-if="row.crossesAudience"
                      class="text-warning"
                    >
                      · {{ t('cables.crossesAudience') }}
                    </span>
                  </q-item-label>
                  <div class="row wrap q-mt-xs">
                    <q-btn
                      class="q-mr-sm q-mb-xs cable-action"
                      outline
                      dense
                      no-caps
                      color="primary"
                      :icon="row.hidden ? 'visibility_off' : 'visibility'"
                      :label="row.hidden ? t('cables.showCable') : t('cables.hideCable')"
                      :aria-label="row.hidden ? t('cables.showCable') : t('cables.hideCable')"
                      @click.stop="toggleCableHidden(row)"
                    >
                      <q-tooltip>{{ t('cables.hideTip') }}</q-tooltip>
                    </q-btn>
                    <q-btn
                      class="q-mr-sm q-mb-xs cable-action"
                      outline
                      dense
                      no-caps
                      color="primary"
                      icon="alt_route"
                      :label="t('cables.rerouteAction')"
                      :aria-label="t('cables.rerouteAction')"
                      :disable="!row.placed || !!drawingWay"
                      @click.stop="startReroute(row)"
                    >
                      <q-tooltip>
                        {{ row.placed ? t('cables.rerouteTip') : t('cables.rerouteDisabledTip') }}
                      </q-tooltip>
                    </q-btn>
                    <q-btn
                      v-if="row.requestedMode === 'manual'"
                      class="q-mr-sm q-mb-xs cable-action"
                      outline
                      dense
                      no-caps
                      color="primary"
                      icon="undo"
                      :label="t('cables.autoRouteAction')"
                      :aria-label="t('cables.autoRouteAction')"
                      @click.stop="resetRoute(row)"
                    >
                      <q-tooltip>{{ t('cables.autoRouteTip') }}</q-tooltip>
                    </q-btn>
                  </div>
                </q-item-section>
                <q-item-section side>
                  <q-item-label v-if="row.placed">
                    {{ row.pathM }} m
                  </q-item-label>
                  <q-item-label
                    v-if="row.placed"
                    caption
                  >
                    {{ t('cables.lengthClass') }}:
                    {{ row.assignedM === null ? t('cables.overMax') : `${row.assignedM} m` }}
                  </q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
            <div
              v-if="!cableRows.length"
              class="text-grey-7 q-mt-sm"
            >
              {{ t('cables.none') }}
            </div>

            <div
              v-if="cablePlan.cableways.length"
              class="q-mt-md"
            >
              <div class="text-subtitle2 q-mb-xs">
                {{ t('cables.waysTitle') }}
              </div>
              <div
                v-for="(w, i) in cablePlan.cableways"
                :key="w.id"
                class="row items-center q-gutter-sm"
              >
                <div class="col">
                  {{ t('cables.wayLabel', { n: i + 1 }) }}
                  <span class="text-grey-7">({{ w.points.length }} {{ t('cables.points') }})</span>
                </div>
                <q-btn
                  outline
                  dense
                  no-caps
                  color="primary"
                  icon="edit"
                  :label="t('cables.editWay')"
                  :aria-label="t('cables.editWay')"
                  :disable="drawingWay"
                  @click="startEditWay(w)"
                >
                  <q-tooltip>{{ t('cables.editWayTip') }}</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  dense
                  round
                  icon="delete"
                  color="negative"
                  :aria-label="t('cables.deleteWay')"
                  :disable="drawingWay"
                  @click="removeCableway(w.id)"
                />
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>
    <q-dialog v-model="speakerDialog">
      <q-card style="min-width: 360px; max-width: 95vw">
        <q-card-section class="text-h6">
          {{ t('stagePlot.addSpeakers') }}
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-select
            v-model="speakerForm.type"
            :options="speakerTypeOptions"
            :label="t('stagePlot.speakerType')"
            emit-value
            map-options
            dense
            @update:model-value="applySpeakerDefaults"
          />
          <q-input
            v-model="speakerForm.label"
            :label="t('stagePlot.speakerLabel')"
            dense
          />
          <q-input
            v-model.number="speakerForm.count"
            type="number"
            :label="t('stagePlot.speakerCount')"
            :min="1"
            :max="16"
            dense
          />
          <div class="row q-gutter-sm">
            <q-input
              v-model.number="speakerForm.coverage_angle_h"
              type="number"
              :label="t('stagePlot.coverageAngle')"
              dense
              class="col"
            />
            <q-input
              v-model.number="speakerForm.coverage_distance_m"
              type="number"
              :label="t('stagePlot.coverageDistance')"
              dense
              class="col"
            />
          </div>
          <q-select
            v-model="speakerForm.linked_output_point_id"
            :options="outputPointOptions"
            :label="t('stagePlot.linkOutput')"
            emit-value
            map-options
            clearable
            dense
          />
          <div class="text-caption text-grey-7">
            {{ t('stagePlot.speakerPlacementHint') }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('app.actions.cancel')"
          />
          <q-btn
            color="primary"
            :label="t('stagePlot.addSpeakerConfirm')"
            :loading="addingSpeakers"
            @click="addSpeakers"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';
import { api } from '@/boot/api';
import { getApiBaseUrl } from '@/utils/runtime-config';
import { useStagePlotStore } from '@/stores/stageplot';
import { channelColor } from '@/utils/instrumentGroups';
import { useDevicesStore } from '@/stores/devices';
import { CATEGORIES, categoryOfDeviceType, categoryOfElement } from '@/utils/categories';
import { horizontalFovDeg, viewPolygon } from '@/utils/camera';
import {
  buildCableRows,
  elementCentre,
  cablesToCsv,
  DEFAULT_CABLE_SETTINGS,
  emptyCablePlan,
  cableTypeCsv,
  cableTypeOrder,
  lengthOrder,
} from '@/utils/cables';

const { t } = useI18n({ useScope: 'global' });
const route = useRoute();
const router = useRouter();

function goBackToJob() {
  router.push({
    path: `/jobs/${jobId}`,
    query: route.query.from === 'video' ? { view: 'video' } : {},
  });
}
const jobId = route.params.jobId;
const store = useStagePlotStore();
const devicesStore = useDevicesStore();

const DEFAULT_W = 1200;
const DEFAULT_H = 700;
const GRID_CM = 50;

const palette = {
  performer: { labelKey: 'stagePlot.types.performer', icon: 'person', color: '#35A853', w: 60, h: 60 },
  instrument: { labelKey: 'stagePlot.types.instrument', icon: 'music_note', color: '#26A69A', w: 90, h: 60 },
  microphone: { labelKey: 'stagePlot.types.microphone', icon: 'mic', color: '#AB47BC', w: 26, h: 26 },
  wireless_receiver: { labelKey: 'stagePlot.types.wirelessReceiver', icon: 'settings_input_antenna', color: '#7E57C2', w: 48, h: 48 },
  speaker_main: {
    labelKey: 'stagePlot.types.speakerMain',
    icon: 'volume_up',
    color: '#FF7043',
    w: 42,
    h: 72,
    coverageAngle: 90,
    coverageDistance: 30,
    defaultRotation: 180,
  },
  speaker_sub: {
    labelKey: 'stagePlot.types.speakerSub',
    icon: 'graphic_eq',
    color: '#F4511E',
    w: 60,
    h: 60,
    coverageAngle: 360,
    coverageDistance: 15,
    defaultRotation: 180,
  },
  speaker_delay: {
    labelKey: 'stagePlot.types.speakerDelay',
    icon: 'speaker',
    color: '#FFA726',
    w: 42,
    h: 60,
    coverageAngle: 60,
    coverageDistance: 40,
    defaultRotation: 180,
  },
  monitor: {
    label: 'Monitor',
    icon: 'headphones',
    color: '#26C6DA',
    w: 46,
    h: 36,
    coverageAngle: 60,
    coverageDistance: 8,
  },
  camera: {
    labelKey: 'stagePlot.types.camera',
    icon: 'videocam',
    color: '#42A5F5',
    w: 40,
    h: 30,
    deviceType: 'camera',
    createDevice: true,
  },
  mixer: {
    labelKey: 'stagePlot.types.mixer',
    icon: 'tune',
    color: '#7E57C2',
    w: 90,
    h: 45,
    deviceType: 'mixer',
  },
  switcher: {
    labelKey: 'stagePlot.types.switcher',
    icon: 'memory',
    color: '#26A69A',
    w: 80,
    h: 45,
    deviceType: 'switcher',
  },
  di: { label: 'DI', icon: 'crop_square', color: '#5C6BC0', w: 24, h: 18 },
  multicore: { label: 'Multicore', icon: 'cable', color: '#8D6E63', w: 32, h: 120 },
  dais: { labelKey: 'stagePlot.types.dais', icon: 'crop_16_9', color: '#78909C', w: 220, h: 120 },
  riser: { labelKey: 'stagePlot.types.riser', icon: 'layers', color: '#607D8B', w: 180, h: 90 },
};
const CUSTOM_DEF = { label: 'Custom', icon: 'add', color: '#90A4AE', w: 60, h: 60 };
const SPEAKER_TYPES = new Set(['speaker', 'speaker_main', 'speaker_sub', 'speaker_delay', 'monitor']);
const LEGACY_TYPE = { speaker: 'speaker_main' };
function paletteLabel(def) {
  return def.labelKey ? t(def.labelKey) : def.label;
}
function elementColor(el, fallback) {
  if (!el.linked_channel_id) return fallback;
  const channel = findChannel(el.linked_channel_id);
  return channel ? channelColor(channel) : fallback;
}
function isSpeakerElement(el) {
  return !!el && SPEAKER_TYPES.has(el.element_type);
}

const pointTypeKey = {
  mixer: 'typeMixer',
  analog_stagebox: 'typeAnalog',
  digital_stagebox: 'typeDigital',
  split: 'typeSplit',
  network: 'typeNetwork',
  direct: 'typeDirect',
  speaker: 'typeSpeaker',
  monitor: 'typeMonitor',
  recorder: 'typeRecorder',
  amp: 'typeAmp',
  stage: 'typeStage',
  other: 'typeOther',
};
function patchPointTypeLabel(pt) {
  return t(`channels.patchPoint.${pointTypeKey[pt] || 'typeDirect'}`);
}

function defFor(type) {
  return palette[type] || palette[LEGACY_TYPE[type]] || CUSTOM_DEF;
}

const $q = useQuasar();
const scale = ref(0.7);
// On a phone the whole plot should fit the screen width when it is first shown.
function fitPlotToScreen() {
  if (!$q.screen.lt.sm) return;
  const usable = Math.max(200, window.innerWidth - 64);
  scale.value = Math.max(0.15, Math.min(0.7, usable / (canvasW.value || 1200)));
}
const unit = ref('cm');
const unitOptions = [
  { label: 'cm', value: 'cm' },
  { label: 'mm', value: 'mm' },
];
const selectedId = ref(null);
const stageRef = ref(null);
const trRef = ref(null);
const draft = ref({
  label: '',
  rotation: 0,
  position_x: 0,
  position_y: 0,
  linked_channel_id: null,
  linked_device_id: null,
  linked_output_point_id: null,
  linked_video_input_id: null,
  linked_lens_device_id: null,
  focal_mm: null,
  width_cm: 60,
  height_cm: 60,
  image_url: '',
  coverage_angle_h: 0,
  coverage_distance_m: 0,
});
const videoLists = ref([]);

const stageW = ref(DEFAULT_W);
const stageH = ref(DEFAULT_H);
const stageX = ref(0);
const stageY = ref(0);
const venueW = ref(0);
const venueH = ref(0);
const job = ref(null);
const channelLists = ref([]);
const imageCache = ref({});
const bgImage = ref(null);
const uploading = ref(false);
const showSoundCoverage = ref(false);
const showCameraCoverage = ref(false);
const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: t(`stagePlot.categories.${c}`) }));
const categoryStorageKey = computed(() => `sw_stage_categories_${jobId}`);
const visibleCategories = ref([...CATEGORIES]);
watch(categoryStorageKey, (key) => {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    visibleCategories.value = Array.isArray(saved) ? saved : [...CATEGORIES];
  } catch {
    visibleCategories.value = [...CATEGORIES];
  }
}, { immediate: true });
watch(visibleCategories, (value) => {
  localStorage.setItem(categoryStorageKey.value, JSON.stringify(value));
});
function toggleCategory(category) {
  visibleCategories.value = visibleCategories.value.includes(category)
    ? visibleCategories.value.filter((c) => c !== category)
    : [...visibleCategories.value, category];
}
function deviceTypeOf(deviceId) {
  return deviceId ? devicesStore.byId(deviceId)?.device_type || null : null;
}
function elementCategory(el) {
  return categoryOfElement(el, deviceTypeOf(el.linked_device_id));
}
const visibleElements = computed(() =>
  store.elements.filter((el) => visibleCategories.value.includes(elementCategory(el))),
);
function endpointVisible(elementId, deviceId) {
  if (elementId) {
    const el = store.elements.find((e) => e.id === elementId);
    return !!el && visibleCategories.value.includes(elementCategory(el));
  }
  if (deviceId) {
    return visibleCategories.value.includes(categoryOfDeviceType(deviceTypeOf(deviceId)));
  }
  return true;
}
const coverage = ref(null);
const coverageImage = ref(null);
const speakerSpecs = ref({});
const speakerDialog = ref(false);
const addingSpeakers = ref(false);
const ROTATE_STEPS = [-90, -15, 15, 90];
const SPEAKER_ROW_Y = 20;
const SPEAKER_CHOICES = ['speaker_main', 'speaker_sub', 'speaker_delay', 'monitor'];
const speakerForm = reactive({
  type: 'speaker_main',
  label: '',
  count: 1,
  coverage_angle_h: 90,
  coverage_distance_m: 30,
  linked_output_point_id: null,
});
let coverageTimer = null;

const hasVenue = computed(() => venueW.value > 0 && venueH.value > 0);
const canvasW = computed(() => (hasVenue.value ? venueW.value : stageX.value + stageW.value));
const canvasH = computed(() => (hasVenue.value ? venueH.value : stageY.value + stageH.value));

const pxPerCm = computed(() => scale.value);

function fullImageUrl(value) {
  if (!value) return value;
  if (/^https?:\/\//i.test(value)) return value;
  return getApiBaseUrl() + value;
}
const selected = computed(
  () => store.elements.find((e) => e.id === selectedId.value) || null,
);
const channelOptions = computed(() => {
  const opts = [];
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      const bits = [list.name, `Ch ${ch.channel_number}: ${ch.source_label || ''}`.trim()];
      if (ch.input_type) bits.push(ch.input_type);
      opts.push({ value: ch.id, label: bits.filter(Boolean).join(' · ') });
    }
  }
  return opts;
});
const pointChannelMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) m[p.id] = ch.id;
    }
  }
  return m;
});
const pointNameMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        m[p.id] = deviceNameMap.value[p.device_id] || patchPointTypeLabel(p.point_type);
      }
    }
  }
  return m;
});
const deviceOptions = computed(() =>
  devicesStore.devices.map((d) => ({ value: d.id, label: d.name || '—' })),
);
const deviceNameMap = computed(() => {
  const m = {};
  for (const d of devicesStore.devices) m[d.id] = d.name || '—';
  return m;
});
const deviceChannelMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        if (p.device_id) {
          (m[p.device_id] = m[p.device_id] || new Set()).add(ch.id);
        }
      }
    }
  }
  return m;
});
const devicePatchPointMap = computed(() => {
  const m = {};
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      for (const p of ch.patch_points || []) {
        if (p.device_id) {
          (m[p.device_id] = m[p.device_id] || new Set()).add(p.id);
        }
      }
    }
  }
  return m;
});

const highlightParam = computed(() => route.query.highlight || '');
const highlightIds = computed(() => {
  const raw = highlightParam.value;
  if (!raw) return [];
  const idx = String(raw).indexOf(':');
  const mode = idx >= 0 ? String(raw).slice(0, idx) : String(raw);
  const value = idx >= 0 ? String(raw).slice(idx + 1) : '';
  const deviceSet = new Set();
  const channelSet = new Set();
  const pointSet = new Set();
  if (mode === 'device' && value) {
    deviceSet.add(value);
  } else if (mode === 'channel' && value) {
    channelSet.add(value);
    for (const [devId, chans] of Object.entries(deviceChannelMap.value)) {
      if (chans.has(value)) deviceSet.add(devId);
    }
  } else if (mode === 'patchpoint' && value) {
    pointSet.add(value);
    if (pointChannelMap.value[value]) channelSet.add(pointChannelMap.value[value]);
    for (const [devId, pts] of Object.entries(devicePatchPointMap.value)) {
      if (pts.has(value)) deviceSet.add(devId);
    }
  } else if (mode === 'sheet' && value) {
    const name = decodeURIComponent(value);
    const dev = devicesStore.devices.find(
      (d) => (d.name || '').toLowerCase() === name.toLowerCase(),
    );
    if (dev) deviceSet.add(dev.id);
    for (const list of channelLists.value) {
      for (const ch of list.channels || []) {
        for (const p of ch.patch_points || []) {
          if (p.device_id && p.device_id === dev?.id) {
            pointSet.add(p.id);
            channelSet.add(ch.id);
          }
        }
      }
    }
  }
  const ids = [];
  for (const el of store.elements) {
    if (
      (el.linked_device_id && deviceSet.has(el.linked_device_id)) ||
      (el.linked_channel_id && channelSet.has(el.linked_channel_id)) ||
      (el.linked_patch_point_id && pointSet.has(el.linked_patch_point_id))
    ) {
      ids.push(el.id);
    }
  }
  return ids;
});
const highlightLabel = computed(() => {
  const raw = highlightParam.value;
  if (!raw) return '';
  const idx = String(raw).indexOf(':');
  const mode = idx >= 0 ? String(raw).slice(0, idx) : String(raw);
  const value = idx >= 0 ? String(raw).slice(idx + 1) : '';
  if (mode === 'sheet') return decodeURIComponent(value || '');
  if (mode === 'device') return deviceNameMap.value[value] || '';
  if (mode === 'channel') {
    const ch = findChannel(value);
    return ch ? `Ch ${ch.channel_number}` : '';
  }
  if (mode === 'patchpoint') return pointNameMap.value[value] || '';
  return '';
});
function clearHighlight() {
  router.replace({ name: route.name, params: route.params });
}
const xLabel = computed(() => `X (${unit.value})`);
const yLabel = computed(() => `Y (${unit.value})`);
const stageConfig = computed(() => ({
  width: canvasW.value * pxPerCm.value,
  height: canvasH.value * pxPerCm.value,
}));
const venueFrameConfig = computed(() => ({
  x: 0,
  y: 0,
  width: canvasW.value * pxPerCm.value,
  height: canvasH.value * pxPerCm.value,
  fill: bgImage.value ? 'transparent' : '#0b1013',
  stroke: '#455a64',
  strokeWidth: 2,
  listening: false,
}));
const bgConfig = computed(() => ({
  image: bgImage.value,
  x: 0,
  y: 0,
  width: canvasW.value * pxPerCm.value,
  height: canvasH.value * pxPerCm.value,
  listening: false,
}));
const coverageConfig = computed(() => ({
  image: coverageImage.value,
  x: 0,
  y: 0,
  width: canvasW.value * pxPerCm.value,
  height: canvasH.value * pxPerCm.value,
  listening: false,
}));
const stageBg = computed(() => ({
  x: stageX.value * pxPerCm.value,
  y: stageY.value * pxPerCm.value,
  width: stageW.value * pxPerCm.value,
  height: stageH.value * pxPerCm.value,
  fill: '#0f161a',
  opacity: bgImage.value ? 0.6 : 1,
  stroke: '#37474f',
  strokeWidth: 2,
  draggable: true,
  name: 'stage-area',
  ondragend: onStageDragEnd,
}));
const gridLines = computed(() => {
  const lines = [];
  const w = canvasW.value * pxPerCm.value;
  const h = canvasH.value * pxPerCm.value;
  const step = GRID_CM * pxPerCm.value;
  for (let x = step; x < w; x += step) {
    lines.push({ points: [x, 0, x, h], stroke: '#1c272d', strokeWidth: 1, listening: false });
  }
  for (let y = step; y < h; y += step) {
    lines.push({ points: [0, y, w, y], stroke: '#1c272d', strokeWidth: 1, listening: false });
  }
  return lines;
});
const transformerConfig = {
  rotateEnabled: true,
  enabledAnchors: [],
  rotationSnaps: Array.from({ length: 24 }, (_, i) => i * 15),
  borderEnabled: false,
};

function round1(n) {
  return Math.round(n * 10) / 10;
}
function groupConfig(el) {
  return {
    id: el.id,
    x: (stageX.value + el.position_x) * pxPerCm.value,
    y: (stageY.value + el.position_y) * pxPerCm.value,
    rotation: el.rotation,
    draggable: true,
    onclick: () => select(el.id),
    ontap: () => select(el.id),
    ondragend: (e) => onDragEnd(el, e),
    ontransform: (e) => keepLabelsUpright(e.target),
    ontransformend: (e) => onTransformEnd(el, e),
  };
}
function rotateLabel(step) {
  return `${step > 0 ? '+' : ''}${step}°`;
}
function rotateBy(step) {
  if (!selected.value) return;
  const current = Number(draft.value.rotation) || 0;
  draft.value.rotation = ((((current + step) % 360) + 360) % 360);
  commitRotation();
}
function rectConfig(el) {
  const def = defFor(el.element_type);
  const hi = highlightIds.value.includes(el.id);
  const selected = selectedId.value === el.id;
  const hasImage = !!imageFor(el);
  return {
    width: el.width_cm * pxPerCm.value,
    height: el.height_cm * pxPerCm.value,
    // When an image is present it fills the box, so hide the coloured fill
    // (the picture shows instead of the box). Keep a transparent fill so the
    // shape still catches clicks/drag.
    fill: hasImage && !hi ? 'transparent' : elementColor(el, def.color),
    cornerRadius: 4,
    opacity: hi || selected ? 1 : hasImage ? 1 : 0.85,
    stroke: hi ? '#35A853' : selected ? '#ffb300' : 'transparent',
    strokeWidth: hi ? 4 : selected ? 3 : 0,
    shadowColor: hi ? '#35A853' : 'transparent',
    shadowBlur: hi ? 14 : 0,
  };
}
// Labels live inside the element's rotated group, so each one counter-rotates by
// the element's rotation to stay upright and readable. Its pivot is the anchor
// point (the centre of the box, or the bottom-centre when a photo sits above it).
function uprightTextProps(el, width) {
  return { rotation: -(el.rotation || 0), offsetX: width / 2 };
}
function labelConfig(el) {
  const s = pxPerCm.value;
  const def = defFor(el.element_type);
  const w = el.width_cm * s;
  const h = el.height_cm * s;
  if (imageFor(el)) {
    // Photo fills the box; show the label below it so it stays readable.
    const labelFont = Math.max(9, 10 * s);
    return {
      name: 'element-label',
      text: el.label || paletteLabel(def),
      ...uprightTextProps(el, w),
      x: w / 2,
      y: h + 2,
      width: w,
      align: 'center',
      fontSize: labelFont,
      fill: '#e0e0e0',
      listening: false,
    };
  }
  return {
    name: 'element-label',
    text: el.label || paletteLabel(def),
    ...uprightTextProps(el, w),
    x: w / 2,
    y: h / 2,
    offsetY: h / 2,
    width: w,
    height: h,
    align: 'center',
    verticalAlign: 'middle',
    fontSize: Math.max(10, 12 * s),
    fill: '#ffffff',
    listening: false,
  };
}
function imageFor(el) {
  return el.image_url ? imageCache.value[el.id] || null : null;
}
function effectiveSpeaker(el) {
  const spec = speakerSpecs.value[el.id];
  if (!spec) return el;
  return {
    ...el,
    coverage_angle_h: spec.coverage_angle_h,
    coverage_distance_m: spec.coverage_distance_m,
  };
}
function sectorFor(el) {
  const sp = effectiveSpeaker(el);
  return isSpeakerElement(sp) && sp.coverage_angle_h > 0 && sp.coverage_distance_m > 0;
}
function wedgeConfig(el) {
  const s = pxPerCm.value;
  const sp = effectiveSpeaker(el);
  const angle = Math.min(sp.coverage_angle_h, 360);
  return {
    x: (el.width_cm / 2) * s,
    y: (el.height_cm / 2) * s,
    radius: sp.coverage_distance_m * 100 * s,
    angle,
    // Konva starts a wedge at its rotation and sweeps clockwise; face the wedge up
    // (-90°, the element's front at rotation 0) and centre it on that heading.
    rotation: -90 - angle / 2,
    fill: 'rgba(255, 183, 77, 0.14)',
    stroke: 'rgba(255, 183, 77, 0.55)',
    strokeWidth: 1,
    listening: false,
  };
}
const outputPointOptions = computed(() => {
  const opts = [];
  for (const list of channelLists.value) {
    for (const out of list.outputs || []) {
      for (const pt of out.points || []) {
        const bits = [out.name || 'Output'];
        if (pt.patch_label) bits.push(pt.patch_label);
        else bits.push(patchPointTypeLabel(pt.point_type));
        if (pt.device_id && deviceNameMap.value[pt.device_id]) bits.push(deviceNameMap.value[pt.device_id]);
        opts.push({ value: pt.id, label: bits.join(' · ') });
      }
    }
  }
  return opts;
});
function findChannel(channelId) {
  for (const list of channelLists.value) {
    for (const ch of list.channels || []) {
      if (ch.id === channelId) return ch;
    }
  }
  return null;
}
function outputPointDeviceId(pointId) {
  for (const list of channelLists.value) {
    for (const out of list.outputs || []) {
      for (const pt of out.points || []) {
        if (pt.id === pointId) return pt.device_id || null;
      }
    }
  }
  return null;
}
function linkedSummary(el) {
  const parts = [];
  const deviceId = isSpeakerElement(el)
    ? outputPointDeviceId(el.linked_output_point_id)
    : el.linked_device_id;
  if (deviceId) {
    const name = deviceNameMap.value[deviceId];
    if (name) parts.push(name);
  }
  if (el.linked_channel_id) {
    const option = channelOptions.value.find((o) => o.value === el.linked_channel_id);
    if (option) parts.push(option.label);
  }
  if (el.linked_video_input_id) {
    const opt = videoInputOptions.value.find((o) => o.value === el.linked_video_input_id);
    if (opt) parts.push(opt.label);
  }
  return parts.join(' · ');
}
function linkedTextConfig(el) {
  const s = pxPerCm.value;
  const labelFont = Math.max(9, 10 * s);
  const offset = imageFor(el) ? labelFont + 2 : 0;
  const w = el.width_cm * s;
  return {
    name: 'element-label',
    text: linkedSummary(el),
    ...uprightTextProps(el, w),
    x: w / 2,
    y: el.height_cm * s + 2 + offset,
    width: w,
    align: 'center',
    fontSize: Math.max(9, 10 * s),
    fill: '#9ccc9c',
    listening: false,
  };
}
function imageConfig(el) {
  return {
    image: imageFor(el),
    x: 0,
    y: 0,
    width: el.width_cm * pxPerCm.value,
    height: el.height_cm * pxPerCm.value,
    listening: false,
  };
}
function loadBgImage(url) {
  if (!url) {
    bgImage.value = null;
    return;
  }
  const img = new Image();
  img.onload = () => {
    bgImage.value = img;
  };
  img.src = fullImageUrl(url);
}
function loadImages(els) {
  for (const el of els) {
    if (!el.image_url) continue;
    const cached = imageCache.value[el.id];
    if (cached && cached.src === el.image_url) continue;
    const img = new Image();
    img.onload = () => {
      imageCache.value = { ...imageCache.value, [el.id]: img };
    };
    img.src = fullImageUrl(el.image_url);
  }
}

function updateTransformer() {
  const tr = trRef.value && trRef.value.getNode ? trRef.value.getNode() : null;
  if (!tr) return;
  if (!selectedId.value) {
    tr.nodes([]);
    return;
  }
  const stage = stageRef.value && stageRef.value.getStage ? stageRef.value.getStage() : null;
  // Element ids are UUIDs, which can start with a digit and so are not valid
  // CSS selectors. Match on the id directly instead.
  const node = stage ? stage.findOne((n) => n.id() === selectedId.value) : null;
  tr.nodes(node ? [node] : []);
  const layer = tr.getLayer();
  if (layer) layer.batchDraw();
}

function select(id) {
  selectedId.value = id;
  const el = store.elements.find((e) => e.id === id);
  if (el) {
    draft.value = {
      label: el.label,
      rotation: el.rotation,
      position_x: el.position_x,
      position_y: el.position_y,
      linked_channel_id: el.linked_channel_id || null,
      linked_device_id: el.linked_device_id || null,
      linked_output_point_id: el.linked_output_point_id || null,
      linked_video_input_id: el.linked_video_input_id || null,
      linked_lens_device_id: el.linked_lens_device_id || null,
      focal_mm: el.focal_mm ?? null,
      width_cm: el.width_cm,
      height_cm: el.height_cm,
      image_url: el.image_url || '',
      coverage_angle_h: el.coverage_angle_h || 0,
      coverage_distance_m: el.coverage_distance_m || 0,
    };
  }
  updateTransformer();
}

function onStageClick(e) {
  if (drawingAudience.value) {
    addAudiencePoint(e);
    return;
  }
  if (drawingWay.value) {
    addDrawPoint(e);
    return;
  }
  if (rerouteKey.value) {
    addWaypoint(e);
    return;
  }
  if (e.target === e.target.getStage()) {
    selectedId.value = null;
    selectedCableKey.value = null;
    updateTransformer();
  }
}

function onDragEnd(el, e) {
  const node = e.target;
  const x = round1(node.x() / pxPerCm.value - stageX.value);
  const y = round1(node.y() / pxPerCm.value - stageY.value);
  store.updateElement(jobId, el.id, { position_x: x, position_y: y });
  if (selectedId.value === el.id) {
    draft.value.position_x = x;
    draft.value.position_y = y;
  }
}

function onStageDragEnd(e) {
  const node = e.target;
  const x = round1(node.x() / pxPerCm.value);
  const y = round1(node.y() / pxPerCm.value);
  stageX.value = x;
  stageY.value = y;
  saveStagePosition();
}

function keepLabelsUpright(group) {
  const rotation = group.rotation();
  group.find('.element-label').forEach((node) => node.rotation(-rotation));
  group.getLayer()?.batchDraw();
}
function onTransformEnd(el, e) {
  // The transformer rotates about the box centre, which moves the group origin,
  // so the position is saved along with the rotation.
  const node = e.target;
  const rotation = ((Math.round(node.rotation()) % 360) + 360) % 360;
  const position_x = round1(node.x() / pxPerCm.value - stageX.value);
  const position_y = round1(node.y() / pxPerCm.value - stageY.value);
  store.updateElement(jobId, el.id, { rotation, position_x, position_y });
  if (selectedId.value === el.id) {
    draft.value.rotation = rotation;
    draft.value.position_x = position_x;
    draft.value.position_y = position_y;
  }
}

// A mixer or switcher on the plot links to a job device of its type that is not on
// the plot yet, so the cables from it and to it are drawn.
function unplacedDeviceOf(deviceType) {
  const placed = new Set(store.elements.map((e) => e.linked_device_id).filter(Boolean));
  return devicesStore.devices.find((d) => d.device_type === deviceType && !placed.has(d.id)) || null;
}

async function addElement(type) {
  const def = palette[type];
  let device = def.deviceType ? unplacedDeviceOf(def.deviceType) : null;
  if (!device && def.createDevice) {
    const count = devicesStore.devices.filter((d) => d.device_type === def.deviceType).length;
    device = await devicesStore.createDevice(jobId, {
      name: `${paletteLabel(def)} ${count + 1}`,
      device_type: def.deviceType,
    });
  }
  const payload = {
    element_type: type,
    position_x: stageW.value / 2 - def.w / 2,
    position_y: stageH.value / 2 - def.h / 2,
    rotation: def.defaultRotation ?? 0,
    label: device?.name || paletteLabel(def),
    width_cm: def.w,
    height_cm: def.h,
    linked_device_id: device?.id || null,
  };
  if (def.coverageAngle) {
    payload.coverage_angle_h = def.coverageAngle;
    payload.coverage_distance_m = def.coverageDistance;
  }
  const created = await store.createElement(jobId, payload);
  select(created.id);
}

function addCustom() {
  const payload = {
    element_type: 'custom',
    position_x: stageW.value / 2 - CUSTOM_DEF.w / 2,
    position_y: stageH.value / 2 - CUSTOM_DEF.h / 2,
    rotation: 0,
    label: t('stagePlot.custom'),
    width_cm: CUSTOM_DEF.w,
    height_cm: CUSTOM_DEF.h,
  };
  store.createElement(jobId, payload).then((created) => select(created.id));
}

async function commitDraft() {
  if (!selected.value) return;
  const element = await store.updateElement(jobId, selected.value.id, {
    label: draft.value.label,
  });
  if (element.element_type === 'performer' && element.linked_channel_id) {
    const channel = findChannel(element.linked_channel_id);
    if (channel) channel.performer_name = element.label;
  }
}
async function commitLink(val) {
  if (!selected.value) return;
  const element = await store.updateElement(jobId, selected.value.id, {
    linked_channel_id: val || null,
  });
  if (element.element_type === 'performer' && element.linked_channel_id) {
    const channel = findChannel(element.linked_channel_id);
    if (channel) channel.performer_name = element.label;
  }
}
function openLinkedChannel() {
  router.push({ path: `/jobs/${jobId}`, query: { channel: draft.value.linked_channel_id } });
}
function openLinkedDevice() {
  router.push({ path: `/jobs/${jobId}/devices`, query: { device: draft.value.linked_device_id } });
}
function commitDevice(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { linked_device_id: val || null });
}
function commitSize() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    width_cm: Number(draft.value.width_cm) || 0,
    height_cm: Number(draft.value.height_cm) || 0,
  });
}
function commitCoverage() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    coverage_angle_h: Number(draft.value.coverage_angle_h) || 0,
    coverage_distance_m: Number(draft.value.coverage_distance_m) || 0,
  });
}
const videoInputOptions = computed(() => {
  const opts = [];
  for (const list of videoLists.value) {
    for (const input of list.inputs || []) {
      const label = input.source_label || t('video.types.camera');
      opts.push({ value: input.id, label: `${list.name} · ${input.input_number}: ${label}` });
    }
  }
  return opts;
});
function commitVideoInput(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { linked_video_input_id: val || null });
}
function commitOutputPoint(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { linked_output_point_id: val || null });
}
function commitImage() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { image_url: draft.value.image_url || '' });
}
async function uploadImageFile(file) {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post('/uploads', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data.url;
}
async function applyDroppedImage(file, el) {
  if (!el) return;
  uploading.value = true;
  try {
    const url = await uploadImageFile(file);
    await store.updateElement(jobId, el.id, { image_url: url });
    if (selectedId.value === el.id) draft.value.image_url = url;
  } finally {
    uploading.value = false;
  }
}
function onImageFilePicked(file) {
  if (!file) return;
  applyDroppedImage(file, selected.value);
}
function clearImage() {
  draft.value.image_url = '';
  commitImage();
}
function onEditorDragOver(e) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
}
function onEditorDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (!file || !/^image\//.test(file.type)) return;
  if (selected.value) applyDroppedImage(file, selected.value);
}
function onStageDragOver(e) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
}
function onStageDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (!file || !/^image\//.test(file.type)) return;
  const stage = stageRef.value?.getStage?.();
  let cmx = null;
  let cmy = null;
  if (stage) {
    const rect = stage.container().getBoundingClientRect();
    cmx = (e.clientX - rect.left) / pxPerCm.value - stageX.value;
    cmy = (e.clientY - rect.top) / pxPerCm.value - stageY.value;
  }
  let targetId = null;
  if (cmx !== null) {
    for (const el of store.elements) {
      const w = el.width_cm || 0;
      const h = el.height_cm || 0;
      if (cmx >= el.position_x && cmx <= el.position_x + w && cmy >= el.position_y && cmy <= el.position_y + h) {
        targetId = el.id;
        break;
      }
    }
  }
  if (!targetId) targetId = selectedId.value;
  if (!targetId) return;
  const el = store.elements.find((x) => x.id === targetId);
  if (el) applyDroppedImage(file, el);
}
function commitRotation() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    rotation: Number(draft.value.rotation) || 0,
  });
}
function commitPosition() {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, {
    position_x: Number(draft.value.position_x) || 0,
    position_y: Number(draft.value.position_y) || 0,
  });
}

async function removeSelected() {
  if (!selectedId.value) return;
  const id = selectedId.value;
  selectedId.value = null;
  await store.deleteElement(jobId, id);
}

async function saveStage() {
  try {
    await api.patch(`/jobs/${jobId}`, {
      stage_width_cm: stageW.value,
      stage_height_cm: stageH.value,
    });
  } catch (err) {
    console.error('Failed to save stage size', err);
  }
}

async function saveStagePosition() {
  try {
    const { data } = await api.patch(`/jobs/${jobId}`, {
      stage_x_cm: stageX.value,
      stage_y_cm: stageY.value,
    });
    applyJobFields(data, ['stage_x_cm', 'stage_y_cm']);
  } catch (err) {
    console.error('Failed to save stage position', err);
  }
}

async function saveVenueSize() {
  try {
    const { data } = await api.patch(`/jobs/${jobId}`, {
      venue_width_cm: venueW.value,
      venue_height_cm: venueH.value,
    });
    applyJobFields(data, ['venue_width_cm', 'venue_height_cm']);
  } catch (err) {
    console.error('Failed to save venue size', err);
  }
}

async function loadJob() {
  try {
    const { data } = await api.get(`/jobs/${jobId}`);
    job.value = data;
    if (data.stage_width_cm && data.stage_width_cm > 0) stageW.value = data.stage_width_cm;
    if (data.stage_height_cm && data.stage_height_cm > 0) stageH.value = data.stage_height_cm;
    stageX.value = data.stage_x_cm || 0;
    stageY.value = data.stage_y_cm || 0;
    venueW.value = data.venue_width_cm || 0;
    venueH.value = data.venue_height_cm || 0;
    loadBgImage(data.venue_background_image_url);
    fitPlotToScreen();
  } catch (err) {
    console.error('Failed to load job', err);
  }
}

async function fetchCoverage() {
  if (!showSoundCoverage.value || !hasVenue.value) {
    coverage.value = null;
    return;
  }
  try {
    const { data } = await api.get(`/jobs/${jobId}/coverage`, { params: { cell_cm: 25 } });
    coverage.value = data;
  } catch (err) {
    console.error('Failed to load coverage', err);
  }
}

const cameraSpecs = ref({});
async function fetchCameraSpecs() {
  try {
    const { data } = await api.get(`/jobs/${jobId}/camera-specs`);
    cameraSpecs.value = data || {};
  } catch (err) {
    console.error('Failed to load camera specs', err);
  }
}

async function fetchSpeakerSpecs() {
  try {
    const { data } = await api.get(`/jobs/${jobId}/speaker-specs`);
    speakerSpecs.value = data || {};
  } catch (err) {
    console.error('Failed to load speaker specs', err);
  }
}

function scheduleCoverage() {
  clearTimeout(coverageTimer);
  coverageTimer = setTimeout(() => {
    fetchCoverage();
    fetchSpeakerSpecs();
    fetchCameraSpecs();
  }, 250);
}

function applySpeakerDefaults(type) {
  const def = palette[type];
  speakerForm.label = paletteLabel(def);
  speakerForm.coverage_angle_h = def.coverageAngle;
  speakerForm.coverage_distance_m = def.coverageDistance;
}
const speakerTypeOptions = computed(() =>
  SPEAKER_CHOICES.map((type) => ({ value: type, label: paletteLabel(palette[type]) })),
);
function openSpeakerDialog() {
  speakerForm.count = 1;
  speakerForm.linked_output_point_id = null;
  speakerForm.type = 'speaker_main';
  applySpeakerDefaults('speaker_main');
  speakerDialog.value = true;
}
async function addSpeakers() {
  const def = palette[speakerForm.type];
  const n = Math.min(16, Math.max(1, Math.round(Number(speakerForm.count) || 1)));
  const baseLabel = speakerForm.label.trim() || paletteLabel(def);
  const spacing = stageW.value / (n + 1);
  addingSpeakers.value = true;
  try {
    const created = await Promise.all(
      Array.from({ length: n }, (_, i) =>
        store.createElement(jobId, {
          element_type: speakerForm.type,
          label: n > 1 ? `${baseLabel} ${i + 1}` : baseLabel,
          position_x: round1(spacing * (i + 1) - def.w / 2),
          position_y: SPEAKER_ROW_Y,
          rotation: def.defaultRotation ?? 0,
          width_cm: def.w,
          height_cm: def.h,
          coverage_angle_h: Number(speakerForm.coverage_angle_h) || 0,
          coverage_distance_m: Number(speakerForm.coverage_distance_m) || 0,
          linked_output_point_id: speakerForm.linked_output_point_id || null,
        }),
      ),
    );
    speakerDialog.value = false;
    if (created.length) select(created[0].id);
  } finally {
    addingSpeakers.value = false;
  }
}

function buildCoverageCanvas(data) {
  const canvas = document.createElement('canvas');
  canvas.width = data.cols;
  canvas.height = data.rows;
  const ctx = canvas.getContext('2d');
  const pixels = ctx.createImageData(data.cols, data.rows);
  data.grid.forEach((line, r) => {
    for (let c = 0; c < data.cols; c += 1) {
      const covered = line[c] === '1';
      const i = (r * data.cols + c) * 4;
      pixels.data[i] = covered ? 53 : 229;
      pixels.data[i + 1] = covered ? 168 : 57;
      pixels.data[i + 2] = covered ? 83 : 53;
      pixels.data[i + 3] = covered ? 90 : 70;
    }
  });
  ctx.putImageData(pixels, 0, 0);
  return canvas;
}

const lensOptions = computed(() =>
  devicesStore.devices
    .filter((d) => d.device_type === 'lens')
    .map((d) => ({ value: d.id, label: d.name || '—' })),
);
function cameraSpec(el) {
  return cameraSpecs.value[el.id] || null;
}
function cameraCaption(el) {
  const spec = cameraSpec(el);
  if (!spec || !spec.sensor_width_mm || !spec.focal_mm) return t('stagePlot.cameraNeedsValues');
  const fov = horizontalFovDeg(spec.sensor_width_mm, spec.focal_mm).toFixed(1);
  const source = spec.source === 'stockwire' ? t('stagePlot.specsFromStockwireShort') : t('stagePlot.specsManualShort');
  return `${t('stagePlot.fovCaption', { deg: fov })} · ${source}`;
}
const cameraViews = computed(() => {
  if (!showCameraCoverage.value) return [];
  const s = pxPerCm.value;
  const box = {
    minX: -stageX.value,
    minY: -stageY.value,
    maxX: canvasW.value - stageX.value,
    maxY: canvasH.value - stageY.value,
  };
  const views = [];
  for (const el of visibleElements.value) {
    const spec = cameraSpecs.value[el.id];
    if (!spec || !spec.sensor_width_mm || !spec.focal_mm) continue;
    const [cx, cy] = elementCentre(el);
    const points = viewPolygon({
      apex: { x: cx, y: cy },
      rotationDeg: el.rotation || 0,
      fovDeg: horizontalFovDeg(spec.sensor_width_mm, spec.focal_mm),
      maxDistanceCm: spec.max_distance_m ? spec.max_distance_m * 100 : null,
      box,
    });
    views.push({
      id: el.id,
      config: {
        points: points.flatMap(([x, y]) => [(x + stageX.value) * s, (y + stageY.value) * s]),
        closed: true,
        fill: 'rgba(66, 165, 245, 0.16)',
        stroke: 'rgba(66, 165, 245, 0.6)',
        strokeWidth: 1,
        listening: false,
      },
    });
  }
  return views;
});
function commitLens(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { linked_lens_device_id: val || null });
}
function commitFocal(val) {
  if (!selected.value) return;
  store.updateElement(jobId, selected.value.id, { focal_mm: Number(val) });
}
const coverageLabel = computed(() =>
  coverage.value ? t('stagePlot.coveragePct', { pct: coverage.value.covered_pct }) : '',
);

async function loadVideoLists() {
  try {
    const { data } = await api.get(`/jobs/${jobId}/video-lists`);
    videoLists.value = data || [];
  } catch (err) {
    console.error('Failed to load video inputs', err);
  }
}

async function loadChannels() {
  try {
    const { data } = await api.get(`/jobs/${jobId}/channel-lists`);
    channelLists.value = data || [];
  } catch (err) {
    console.error('Failed to load channel lists', err);
  }
}

const cablesVisible = ref(true);
const selectedCableKey = ref(null);
const rerouteKey = ref(null);
const drawingWay = ref(false);
const drawingAudience = ref(false);
const audiencePoints = ref([]);
const audienceShown = computed(() => job.value?.audience_polygon || []);
const audienceConfig = computed(() => {
  const s = pxPerCm.value;
  const flat = audienceShown.value.flatMap(([x, y]) => [x * s, y * s]);
  return {
    points: flat,
    closed: true,
    fill: 'rgba(229, 57, 53, 0.12)',
    stroke: '#e53935',
    strokeWidth: 2,
    dash: [10, 6],
    listening: false,
  };
});
const audienceLabelConfig = computed(() => {
  const s = pxPerCm.value;
  const [x, y] = audienceShown.value[0] || [0, 0];
  return {
    x: x * s + 6,
    y: y * s + 4,
    text: t('stagePlot.audienceLabel'),
    fontSize: Math.max(11, 12 * s),
    fill: '#ef9a9a',
    listening: false,
  };
});
const audienceDraftConfig = computed(() => {
  const s = pxPerCm.value;
  return {
    points: audiencePoints.value.flatMap(([x, y]) => [x * s, y * s]),
    stroke: '#e53935',
    strokeWidth: 2,
    dash: [6, 4],
    listening: false,
  };
});
function startAudience() {
  rerouteKey.value = null;
  drawingWay.value = false;
  audiencePoints.value = [];
  drawingAudience.value = true;
}
function cancelAudience() {
  drawingAudience.value = false;
  audiencePoints.value = [];
}
function addAudiencePoint(e) {
  const p = e.target.getStage().getPointerPosition();
  if (!p) return;
  audiencePoints.value = [...audiencePoints.value, [round1(p.x / pxPerCm.value), round1(p.y / pxPerCm.value)]];
}
async function finishAudience() {
  if (audiencePoints.value.length < 3) return;
  await saveJobAudience(audiencePoints.value);
  cancelAudience();
}
async function saveJobAudience(polygon) {
  try {
    const { data } = await api.patch(`/jobs/${jobId}`, { audience_polygon: polygon });
    applyJobFields(data, ['audience_polygon']);
  } catch (err) {
    console.error('Failed to save the audience area', err);
  }
}
function clearAudience() {
  saveJobAudience([]);
}
async function saveAudienceToVenue() {
  if (!job.value?.venue_id) return;
  try {
    await api.patch(`/venues/${job.value.venue_id}`, { audience_polygon: audienceShown.value });
  } catch (err) {
    console.error('Failed to save the audience area to the venue', err);
  }
}
const drawPoints = ref([]);
const editingWayId = ref(null);

const cablePlan = computed(() => emptyCablePlan(job.value?.cable_plan));
const cableRows = computed(() =>
  buildCableRows({
    lists: channelLists.value,
    devices: devicesStore.devices,
    elements: store.elements,
    plan: cablePlan.value,
    videoLists: videoLists.value,
    audience: job.value?.audience_polygon || [],
    stageOffset: [job.value?.stage_x_cm || 0, job.value?.stage_y_cm || 0],
  }),
);
const highlightCableKeys = computed(() => {
  const keys = new Set();
  const raw = highlightParam.value;
  if (!raw) return keys;
  const idx = String(raw).indexOf(':');
  const mode = idx >= 0 ? String(raw).slice(0, idx) : String(raw);
  const value = idx >= 0 ? String(raw).slice(idx + 1) : '';
  if (!value) return keys;
  const name = decodeURIComponent(value).toLowerCase();
  const sheetDevice = devicesStore.devices.find((d) => (d.name || '').toLowerCase() === name);
  for (const r of cableRows.value) {
    if (mode === 'channel' && r.channelId === value) keys.add(r.key);
    else if (mode === 'patchpoint' && (r.toPointId === value || r.fromPointId === value)) {
      keys.add(r.key);
    } else if (mode === 'device' && (r.toDeviceId === value || r.fromDeviceId === value)) {
      keys.add(r.key);
    } else if (
      mode === 'sheet' &&
      sheetDevice &&
      (r.toDeviceId === sheetDevice.id || r.fromDeviceId === sheetDevice.id)
    ) {
      keys.add(r.key);
    }
  }
  return keys;
});
const visibleCableRows = computed(() =>
  cableRows.value.filter(
    (r) =>
      r.placed &&
      endpointVisible(r.fromElementId, r.fromDeviceId) &&
      endpointVisible(r.toElementId, r.toDeviceId) &&
      (highlightCableKeys.value.has(r.key) || (cablesVisible.value && !r.hidden)),
  ),
);
const cableOrder = computed(() => lengthOrder(cableRows.value));
const cableTypes = computed(() => cableTypeOrder(cableRows.value));
const rerouteRow = computed(() => cableRows.value.find((r) => r.key === rerouteKey.value) || null);
const rerouteWaypoints = computed(
  () => cablePlan.value.routes[rerouteKey.value]?.waypoints || [],
);
const standardLengthsText = computed(() =>
  (cablePlan.value.settings.standard_lengths_m || DEFAULT_CABLE_SETTINGS.standard_lengths_m).join(', '),
);

// Only the newest cable-plan save may write its response back, so an older reply
// can never bring back a plan the user has already changed.
let planSeq = 0;
// Copies just the named job fields from a response. A full copy could carry an old
// cable plan from a save that was still in flight.
function applyJobFields(data, keys) {
  job.value = { ...job.value, ...Object.fromEntries(keys.map((k) => [k, data[k]])) };
}
async function savePlan(next) {
  const seq = ++planSeq;
  job.value = { ...job.value, cable_plan: next };
  try {
    const { data } = await api.patch(`/jobs/${jobId}`, { cable_plan: next });
    if (seq === planSeq) job.value = { ...job.value, cable_plan: data.cable_plan };
  } catch (err) {
    console.error('Failed to save cables', err);
  }
}
function updateRoute(key, patch) {
  const plan = cablePlan.value;
  const current = plan.routes[key] || { mode: 'auto', waypoints: [], hidden: false };
  savePlan({ ...plan, routes: { ...plan.routes, [key]: { ...current, ...patch } } });
}
function toggleCableHidden(row) {
  updateRoute(row.key, { hidden: !row.hidden });
}
function resetRoute(row) {
  updateRoute(row.key, { mode: 'auto', waypoints: [] });
  if (rerouteKey.value === row.key) rerouteKey.value = null;
}
function startReroute(row) {
  selectedCableKey.value = row.key;
  rerouteKey.value = row.key;
  const keep = row.requestedMode === 'manual' ? row.waypoints : [];
  updateRoute(row.key, { mode: 'manual', waypoints: keep });
}
function stagePoint(e) {
  const p = e.target.getStage().getPointerPosition();
  if (!p) return null;
  return [p.x / pxPerCm.value - stageX.value, p.y / pxPerCm.value - stageY.value];
}
function addWaypoint(e) {
  const cm = stagePoint(e);
  const key = rerouteKey.value;
  if (!cm || !key) return;
  const current = cablePlan.value.routes[key]?.waypoints || [];
  updateRoute(key, { mode: 'manual', waypoints: [...current, cm] });
}
function undoWaypoint() {
  const key = rerouteKey.value;
  if (!key) return;
  const current = cablePlan.value.routes[key]?.waypoints || [];
  updateRoute(key, { mode: 'manual', waypoints: current.slice(0, -1) });
}
function startDrawWay() {
  rerouteKey.value = null;
  editingWayId.value = null;
  drawPoints.value = [];
  drawingWay.value = true;
}
function startEditWay(way) {
  rerouteKey.value = null;
  editingWayId.value = way.id;
  drawPoints.value = way.points.map((p) => [...p]);
  drawingWay.value = true;
}
function undoDrawPoint() {
  drawPoints.value = drawPoints.value.slice(0, -1);
}
function movePoint(index, e) {
  const node = e.target;
  const next = drawPoints.value.slice();
  next[index] = [
    round1(node.x() / pxPerCm.value - stageX.value),
    round1(node.y() / pxPerCm.value - stageY.value),
  ];
  drawPoints.value = next;
}
function cancelDrawWay() {
  drawingWay.value = false;
  drawPoints.value = [];
  editingWayId.value = null;
}
function pointHandleConfig(p, index) {
  return {
    x: (p[0] + stageX.value) * pxPerCm.value,
    y: (p[1] + stageY.value) * pxPerCm.value,
    radius: 6,
    fill: '#ffb300',
    stroke: '#263238',
    strokeWidth: 1,
    draggable: true,
    ondragend: (e) => movePoint(index, e),
    onclick: (e) => {
      e.cancelBubble = true;
    },
    ontap: (e) => {
      e.cancelBubble = true;
    },
  };
}
function addDrawPoint(e) {
  const cm = stagePoint(e);
  if (cm) drawPoints.value = [...drawPoints.value, cm];
}
function finishDrawWay() {
  if (drawPoints.value.length < 2) return;
  const plan = cablePlan.value;
  const cableways = editingWayId.value
    ? plan.cableways.map((w) =>
        w.id === editingWayId.value ? { ...w, points: drawPoints.value } : w,
      )
    : [...plan.cableways, { id: crypto.randomUUID(), points: drawPoints.value }];
  savePlan({ ...plan, cableways });
  cancelDrawWay();
}
function removeCableway(id) {
  const plan = cablePlan.value;
  savePlan({ ...plan, cableways: plan.cableways.filter((w) => w.id !== id) });
}
function saveCableSettings(patch) {
  const plan = cablePlan.value;
  savePlan({ ...plan, settings: { ...plan.settings, ...patch } });
}
function saveStandardLengths(text) {
  const lengths = String(text)
    .split(',')
    .map((v) => Number(v.trim()))
    .filter((v) => v > 0)
    .sort((a, b) => a - b);
  saveCableSettings({ standard_lengths_m: lengths });
}
function exportCables() {
  const blob = new Blob([`${cablesToCsv(cableRows.value)}\n\n${cableTypeCsv(cableRows.value)}`], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'cables.csv';
  a.click();
  URL.revokeObjectURL(url);
}
function cableLinePoints(points) {
  return points.flatMap(([x, y]) => [
    (x + stageX.value) * pxPerCm.value,
    (y + stageY.value) * pxPerCm.value,
  ]);
}
function cableConfig(row) {
  const highlighted = highlightCableKeys.value.has(row.key);
  const active = selectedCableKey.value === row.key || rerouteKey.value === row.key;
  return {
    points: cableLinePoints(row.points),
    stroke: highlighted ? '#35A853' : active ? '#ffb300' : '#b0bec5',
    strokeWidth: highlighted ? 5 : active ? 3 : 2,
    shadowColor: highlighted ? '#35A853' : 'transparent',
    shadowBlur: highlighted ? 10 : 0,
    lineCap: 'round',
    lineJoin: 'round',
    dash: row.mode === 'direct' ? [8, 6] : undefined,
    hitStrokeWidth: 12,
    onclick: () => (selectedCableKey.value = row.key),
  };
}
function cableWayConfig(w) {
  return {
    points: cableLinePoints(w.points),
    stroke: '#546e7a',
    strokeWidth: 2,
    dash: [4, 4],
    listening: false,
  };
}
const drawConfig = computed(() => ({
  points: cableLinePoints(drawPoints.value),
  stroke: '#ffb300',
  strokeWidth: 2,
  dash: [6, 4],
  listening: false,
}));
function waypointConfig(wp) {
  return {
    x: (wp[0] + stageX.value) * pxPerCm.value,
    y: (wp[1] + stageY.value) * pxPerCm.value,
    radius: 5,
    fill: '#ffb300',
    listening: false,
  };
}

watch(selectedId, updateTransformer);
watch(scale, updateTransformer);
watch(
  () => store.elements,
  (els) => loadImages(els),
  { deep: false },
);
watch(showSoundCoverage, fetchCoverage);
watch(() => [venueW.value, venueH.value, stageX.value, stageY.value], scheduleCoverage);
watch(
  () =>
    store.elements
      .map((el) =>
        [
          el.position_x,
          el.position_y,
          el.rotation,
          el.width_cm,
          el.height_cm,
          el.element_type,
          el.coverage_angle_h,
          el.coverage_distance_m,
          el.linked_output_point_id,
          el.linked_device_id,
          el.linked_lens_device_id,
          el.focal_mm,
        ].join(','),
      )
      .join('|'),
  scheduleCoverage,
);
watch(coverage, (data) => {
  coverageImage.value = data && data.cols ? buildCoverageCanvas(data) : null;
});

onMounted(() => {
  fitPlotToScreen();
  fetchSpeakerSpecs();
  fetchCameraSpecs();
  loadVideoLists();
  loadJob();
  loadChannels();
  devicesStore.fetchDevices(jobId);
  store.fetchElements(jobId);
});
</script>

<style scoped>
.cable-action {
  min-width: 104px;
}
</style>
