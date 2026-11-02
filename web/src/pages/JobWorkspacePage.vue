<template>
  <q-page padding>
    <ReportGenerationDialog
      v-model="reportDialog"
      :job-id="jobId"
    />
    <JobDetailsDialog
      v-model="jobDialog"
      :job-id="jobId"
      :job="job"
      @saved="reloadJob"
    />
    <StockwireAvailabilityPanel
      v-model="availabilityOpen"
      :job-id="jobId"
      :job="job"
    />
    <StageVenueDialog
      v-model="stageVenueOpen"
      :job-id="jobId"
      :frame="plotFrame.frame.value"
      @saved="stageVenueSaved"
      @error="(err) => $q.notify({ type: 'negative', message: errorText(err) })"
    />
    <ConflictDialog
      :conflict="graph.conflict"
      @resolve="resolveConflict"
      @discard="graph.clearConflict()"
    />

    <div class="row items-center q-col-gutter-sm q-mb-md">
      <q-btn
        flat
        round
        icon="arrow_back"
        :aria-label="t('workspace.back')"
        @click="router.push('/')"
      />
      <div class="col">
        <div class="text-h6">
          {{ t('workspace.title') }}
        </div>
        <div
          v-if="job"
          class="row items-center q-gutter-xs text-subtitle2 text-grey-7"
          data-testid="job-summary"
        >
          <span>{{ job.title }}</span>
          <span v-if="job.venue_name">· {{ job.venue_name }}</span>
          <span v-if="job.event_date">· {{ new Date(job.event_date).toLocaleDateString() }}</span>
          <q-chip
            dense
            square
            :color="job.stockwire_job_id ? 'positive' : 'grey-7'"
            text-color="white"
            icon="link"
          >
            {{ job.stockwire_job_id ? t('stockwire.linkedAs', { id: job.stockwire_job_id }) : t('stockwire.notLinked') }}
          </q-chip>
        </div>
      </div>
      <q-btn
        flat
        no-caps
        icon="event_note"
        :label="t('workspace.jobDetails')"
        data-testid="open-job-details"
        @click="jobDialog = true"
      />
      <q-btn
        v-if="job?.stockwire_job_id"
        flat
        no-caps
        icon="open_in_new"
        :label="t('stockwire.openInStockwire')"
        data-testid="open-in-stockwire"
        @click="openInStockwire"
      />
      <q-btn
        color="primary"
        no-caps
        icon="inventory_2"
        :label="t('workspace.catalog')"
        data-testid="open-catalog"
        @click="catalogOpen = true"
      />
      <q-btn
        flat
        no-caps
        icon="inventory"
        :label="t('stockwire.availabilityTitle')"
        data-testid="open-availability"
        @click="availabilityOpen = true"
      />
      <q-btn-dropdown
        flat
        no-caps
        icon="file_upload"
        :label="t('workspace.import')"
        data-testid="import-menu"
      >
        <q-list>
          <q-item
            v-close-popup
            clickable
            data-testid="import-fixtures-file"
            @click="importInput.click()"
          >
            <q-item-section>
              <q-item-label>{{ t('workspace.importFixtures') }}</q-item-label>
              <q-item-label caption>
                CSV, MVR
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-btn-dropdown>
      <input
        ref="importInput"
        type="file"
        accept=".csv,.mvr"
        class="hidden"
        data-testid="header-import-file"
        @change="importFixturesFile"
      >
      <q-btn-dropdown
        v-if="graph.channelLists.length"
        flat
        no-caps
        icon="file_download"
        :label="t('workspace.export')"
        data-testid="export-menu"
        @before-show="loadPlugins"
      >
        <q-list>
          <template
            v-for="list in graph.channelLists"
            :key="list.id"
          >
            <q-item-label header>
              {{ list.name }}
            </q-item-label>
            <q-item
              v-for="plugin in plugins"
              :key="`${list.id}-${plugin.key}`"
              v-close-popup
              clickable
              :data-testid="`export-${plugin.key}`"
              @click="exportList(list, plugin)"
            >
              <q-item-section>
                <q-item-label>{{ plugin.label }}</q-item-label>
              </q-item-section>
            </q-item>
          </template>
        </q-list>
      </q-btn-dropdown>
      <q-btn
        flat
        no-caps
        icon="picture_as_pdf"
        :label="t('workspace.pdfReports')"
        data-testid="open-reports"
        @click="reportDialog = true"
      />
    </div>

    <q-tabs
      :model-value="graph.mode"
      dense
      no-caps
      align="left"
      mobile-arrows
      active-color="primary"
      indicator-color="primary"
      class="q-mb-md workspace-tabs"
      data-testid="mode-toggle"
      @update:model-value="switchMode"
    >
      <q-tab
        v-for="tab in modeTabs"
        :key="tab.value"
        :name="tab.value"
        :icon="tab.icon"
        :label="tab.label"
      />
    </q-tabs>

    <div class="row items-center q-gutter-sm q-mb-md">
      <span class="text-caption text-grey-6">{{ t('workspace.layers') }}</span>
      <q-chip
        v-for="layer in LAYERS"
        :key="layer.key"
        clickable
        dense
        :color="layers[layer.key] ? 'primary' : 'grey-7'"
        text-color="white"
        :data-testid="`layer-${layer.key}`"
        @click="layers[layer.key] = !layers[layer.key]"
      >
        {{ t(layer.label) }}
      </q-chip>
      <q-space />
      <q-chip
        v-for="phase in ['L1', 'L2', 'L3']"
        :key="phase"
        dense
        :color="LEVEL_COLOR[phases[phase].level]"
        text-color="white"
        :data-testid="`phase-${phase}`"
      >
        {{ phase }} {{ Math.round(phases[phase].watts) }} W
      </q-chip>
      <q-chip
        v-if="phases.imbalanceLevel === 'warn'"
        dense
        color="warning"
        text-color="black"
        icon="warning"
      >
        {{ t('workspace.imbalance') }} {{ graph.loads.imbalance_pct }}%
      </q-chip>
    </div>

    <q-banner
      v-if="graph.error"
      class="bg-negative text-white q-mb-md"
      data-testid="graph-error"
    >
      {{ t('workspace.loadFailed') }}: {{ graph.error }}
      <template #action>
        <q-btn
          flat
          no-caps
          :label="t('workspace.retry')"
          @click="loadWorkspace"
        />
      </template>
    </q-banner>

    <div class="row q-col-gutter-md">
      <div
        class="col-12 col-md"
        data-testid="drop-zone"
        @dragover.prevent
        @drop.prevent="onProductDrop"
      >
        <q-banner
          v-if="!graph.devices.length && !graph.loading && graph.mode === 'list'"
          class="bg-grey-9 text-white rounded-borders"
        >
          {{ t('workspace.empty') }}
        </q-banner>
        <template v-else>
          <div
            v-if="graph.mode === 'canvas'"
            class="column items-stretch"
          >
            <div
              class="row items-center q-gutter-xs q-mb-xs canvas-toolbar"
              data-testid="canvas-toolbar"
            >
              <q-btn
                dense
                no-caps
                icon="cable"
                :color="connectMode ? 'primary' : undefined"
                :label="t('workspace.connectTool')"
                data-testid="connect-tool"
                @click="connectMode = !connectMode"
              />
              <q-btn
                dense
                icon="remove"
                aria-label="zoom out"
                @click="zoom = Math.max(0.05, zoom / 1.2)"
              />
              <q-btn
                dense
                icon="add"
                aria-label="zoom in"
                @click="zoom = Math.min(2, zoom * 1.2)"
              />
              <q-btn
                dense
                icon="fit_screen"
                aria-label="fit"
                data-testid="canvas-fit"
                @click="fitCanvas"
              />
              <q-btn
                dense
                no-caps
                icon="pan_tool"
                :color="handTool ? 'primary' : undefined"
                :label="t('workspace.handTool')"
                data-testid="hand-tool"
                @click="handTool = !handTool"
              >
                <q-tooltip>{{ t('workspace.handToolHint') }}</q-tooltip>
              </q-btn>
              <q-separator
                vertical
                class="q-mx-xs"
              />
              <q-btn
                dense
                no-caps
                icon="aspect_ratio"
                :label="t('workspace.gearSize')"
              >
                <q-menu>
                  <div class="q-pa-md">
                    <q-slider
                      v-model="deviceScale"
                      :min="0.4"
                      :max="3"
                      :step="0.1"
                      style="width: 180px"
                      label
                      data-testid="gear-size"
                    />
                  </div>
                </q-menu>
              </q-btn>
              <q-btn
                dense
                no-caps
                icon="crop_free"
                :label="t('workspace.stageVenue')"
                data-testid="edit-stage-venue"
                @click="stageVenueOpen = true"
              />
              <q-btn
                dense
                no-caps
                icon="add_location_alt"
                :label="t('workspace.addOutletOnMap')"
                data-testid="add-outlet-map"
                @click="addOutletOnMap"
              />
              <q-btn-dropdown
                dense
                no-caps
                icon="groups"
                :label="t('stagePlot.audienceDraw')"
                data-testid="audience-menu"
              >
                <q-list>
                  <q-item
                    v-close-popup
                    clickable
                    data-testid="audience-draw"
                    @click="startAudience"
                  >
                    <q-item-section>{{ t('stagePlot.audienceDraw') }}</q-item-section>
                  </q-item>
                  <q-item
                    v-if="plotFrame.frame.value.audience.length"
                    v-close-popup
                    clickable
                    data-testid="audience-clear"
                    @click="saveAudience([])"
                  >
                    <q-item-section>{{ t('stagePlot.audienceClear') }}</q-item-section>
                  </q-item>
                  <q-item
                    v-if="plotFrame.frame.value.audience.length && plotFrame.job.value?.venue_id"
                    v-close-popup
                    clickable
                    data-testid="audience-save-venue"
                    @click="saveAudienceToVenue"
                  >
                    <q-item-section>{{ t('stagePlot.audienceSaveVenue') }}</q-item-section>
                  </q-item>
                </q-list>
              </q-btn-dropdown>
              <q-btn-dropdown
                dense
                no-caps
                icon="speaker"
                :label="t('workspace.addGearElement')"
                data-testid="add-gear-element"
              >
                <q-list>
                  <template
                    v-for="group in ['audio', 'video', 'lighting']"
                    :key="group"
                  >
                    <q-item-label header>
                      {{ t(`workspace.gearGroup.${group}`) }}
                    </q-item-label>
                    <q-item
                      v-for="gear in GEAR_ELEMENTS.filter((g) => g.group === group)"
                      :key="gear.type"
                      v-close-popup
                      clickable
                      :data-testid="`add-gear-${gear.type}`"
                      @click="addGearElement(gear)"
                    >
                      <q-item-section avatar>
                        <q-icon
                          :name="gear.icon"
                          :style="{ color: gear.color }"
                        />
                      </q-item-section>
                      <q-item-section>{{ objectLabel(gear) }}</q-item-section>
                    </q-item>
                  </template>
                </q-list>
              </q-btn-dropdown>
              <q-btn-dropdown
                dense
                no-caps
                icon="category"
                :label="t('workspace.addObject')"
                data-testid="add-object"
              >
                <q-list>
                  <q-item
                    v-for="object in OBJECT_TYPES"
                    :key="object.type"
                    v-close-popup
                    clickable
                    :data-testid="`add-object-${object.type}`"
                    @click="addObject(object)"
                  >
                    <q-item-section avatar>
                      <q-icon
                        :name="object.icon"
                        :style="{ color: object.color }"
                      />
                    </q-item-section>
                    <q-item-section>{{ objectLabel(object) }}</q-item-section>
                  </q-item>
                </q-list>
              </q-btn-dropdown>
              <q-btn
                dense
                no-caps
                icon="cable"
                :color="plotFrame.show.cables.value ? 'primary' : undefined"
                :label="t('cables.title')"
                data-testid="layer-cables"
                @click="plotFrame.show.cables.value = !plotFrame.show.cables.value"
              />
              <q-btn
                dense
                no-caps
                icon="power"
                :color="plotFrame.show.outlets.value ? 'primary' : undefined"
                :label="t('workspace.layerOutlets')"
                data-testid="layer-outlets"
                @click="plotFrame.show.outlets.value = !plotFrame.show.outlets.value"
              />
              <q-btn
                dense
                no-caps
                icon="groups"
                :color="plotFrame.show.audience.value ? 'primary' : undefined"
                :label="t('workspace.layerAudience')"
                data-testid="layer-audience"
                @click="plotFrame.show.audience.value = !plotFrame.show.audience.value"
              />
              <q-btn
                dense
                no-caps
                icon="surround_sound"
                :color="plotFrame.show.coverage.value ? 'primary' : undefined"
                :label="t('workspace.layerSpeakerCoverage')"
                data-testid="layer-coverage"
                @click="plotFrame.show.coverage.value = !plotFrame.show.coverage.value"
              />
              <q-btn
                dense
                no-caps
                icon="videocam"
                :color="plotFrame.show.camera.value ? 'primary' : undefined"
                :label="t('workspace.layerCamera')"
                data-testid="layer-camera"
                @click="plotFrame.show.camera.value = !plotFrame.show.camera.value"
              />
              <q-btn
                dense
                no-caps
                icon="cast"
                :color="plotFrame.show.projector.value ? 'primary' : undefined"
                :label="t('workspace.layerProjector')"
                data-testid="layer-projector"
                @click="plotFrame.show.projector.value = !plotFrame.show.projector.value"
              />
            </div>
            <div
              v-if="rerouteRow"
              class="row items-center q-gutter-xs q-mb-xs"
              data-testid="reroute-bar"
            >
              <span class="text-caption text-grey-6">{{ t('cables.rerouteHint', { name: 'C' + rerouteRow.index }) }}</span>
              <q-btn
                flat
                dense
                no-caps
                icon="undo"
                :label="t('cables.undoWaypoint')"
                :disable="!rerouteWaypoints.length"
                data-testid="reroute-undo"
                @click="undoWaypoint"
              />
              <q-btn
                flat
                dense
                no-caps
                :label="t('cables.resetRoute')"
                @click="resetRoute(rerouteRow)"
              />
              <q-btn
                dense
                no-caps
                color="primary"
                icon="check"
                :label="t('cables.doneReroute')"
                data-testid="reroute-done"
                @click="rerouteKey = null"
              />
            </div>
            <div
              v-if="drawingAudience"
              class="row items-center q-gutter-xs q-mb-xs"
              data-testid="audience-bar"
            >
              <span class="text-caption text-grey-6">{{ t('stagePlot.audienceHint') }}</span>
              <q-btn
                dense
                no-caps
                color="primary"
                icon="check"
                :label="t('stagePlot.audienceFinish')"
                :disable="audiencePoints.length < 3"
                data-testid="audience-finish"
                @click="finishAudience"
              />
              <q-btn
                flat
                dense
                no-caps
                icon="undo"
                :label="t('cables.undoPoint')"
                :disable="!audiencePoints.length"
                @click="audiencePoints.pop()"
              />
              <q-btn
                flat
                dense
                no-caps
                :label="t('common.cancel')"
                @click="cancelAudience"
              />
            </div>
            <div
              v-if="plotFrame.show.camera.value"
              class="row items-center q-gutter-xs q-mb-xs"
              data-testid="camera-view-options"
            >
              <span class="text-caption text-grey-6">{{ t('workspace.layerCamera') }}</span>
              <q-btn-toggle
                v-model="plotFrame.cameraMode.value"
                dense
                no-caps
                unelevated
                toggle-color="primary"
                :options="[
                  { label: t('stagePlot.cameraViewRange'), value: 'range' },
                  { label: t('stagePlot.cameraViewChosen'), value: 'chosen' },
                ]"
              />
            </div>
            <div
              v-if="unplacedGear.length"
              class="row items-center q-gutter-xs q-mb-xs full-width"
              data-testid="unplaced-gear"
            >
              <span class="text-caption text-grey-6">{{ t('workspace.notOnPlot') }}</span>
              <q-chip
                v-for="gear in unplacedGear"
                :key="gear.id"
                dense
                clickable
                icon="add_location_alt"
                data-testid="place-gear"
                @click="placeGear(gear)"
              >
                {{ gear.name }}
              </q-chip>
            </div>
            <WorkspaceCanvas
              class="full-width"
              :devices="canvasDevices"
              :edges="canvasEdges"
              :selected-id="graph.selectedDeviceId"
              :zoom="zoom"
              :device-scale="deviceScale"
              :hand="handTool || spaceHeld"
              :frame="plotFrame.frame.value"
              :outlets="plotFrame.outlets.value"
              :show-outlets="plotFrame.show.outlets.value"
              :show-audience="plotFrame.show.audience.value"
              :coverage-image="plotFrame.coverageImage.value"
              :shapes="viewShapes"
              :cables="plotFrame.show.cables.value ? cableRows : []"
              :cableways="plotFrame.cablePlan.value.cableways"
              :draw-points="drawPoints"
              :drawing="drawingWay"
              :rerouting="!!rerouteKey"
              :reroute-waypoints="rerouteWaypoints"
              :active-cable-key="rerouteKey"
              :audience-draft="audiencePoints"
              :audience-drawing="drawingAudience"
              :connect-mode="connectMode"
              @reroute-point="addWaypoint"
              @audience-point="(p) => audiencePoints.push(p)"
              @draw-point="(p) => drawPoints.push(p)"
              @pan="(p) => (pan = p)"
              @move-outlet="moveOutlet"
              @select-outlet="selectOutlet"
              @select="select"
              @move="move"
              @connect="connectDevices"
            />
          </div>
          <ChannelListEditor
            v-else-if="graph.mode === 'lists'"
            :job-id="jobId"
          />
          <DeviceEditor
            v-else-if="graph.mode === 'devices'"
            :job-id="jobId"
          />
          <LightsEditor
            v-else-if="graph.mode === 'lights'"
            :job-id="jobId"
          />
          <VideoEditor
            v-else-if="graph.mode === 'video'"
            :job-id="jobId"
          />
          <RiggingEditor
            v-else-if="graph.mode === 'power'"
            :job-id="jobId"
          />
          <WorkspaceTable
            v-else
            :job-id="jobId"
            :devices="listDevices"
            :selected-id="graph.selectedDeviceId"
            @select="select"
            @request-booking="requestBooking"
          />
        </template>

        <CableRoutingPanel
          v-if="graph.mode === 'canvas'"
          :rows="cableRows"
          :settings="plotFrame.cablePlan.value.settings"
          :cableways="plotFrame.cablePlan.value.cableways"
          :drawing="drawingWay"
          :draw-points="drawPoints"
          :reroute-key="rerouteKey"
          @toggle-hidden="toggleCableHidden"
          @reroute="startReroute"
          @reset-route="resetRoute"
          @settings="saveCableSettings"
          @draw-start="startDrawWay"
          @draw-finish="finishDrawWay"
          @draw-undo="drawPoints.pop()"
          @draw-cancel="cancelDrawWay"
          @delete-way="removeCableway"
        />

        <div class="q-mt-md">
          <MultiDomainPatchDrawer :job-id="jobId" />
        </div>
      </div>

      <div
        v-if="$q.screen.gt.sm"
        class="col-md-4 col-lg-3"
      >
        <!-- The patch drawer sits under the map (left), so a tall inspector never leaves a gap
             between them; the inspector stays in view and scrolls on its own when it is long. -->
        <q-card
          flat
          bordered
          class="inspector-sticky"
        >
          <OutletInspector
            v-if="selectedOutlet"
            :outlet="selectedOutlet"
            :groups="plotFrame.groups.value"
            :venue-id="plotFrame.job.value.venue_id"
            :job-id="jobId"
            @close="selectedOutletId = null"
            @changed="plotFrame.load()"
          />
          <DeviceInspector
            v-else
            :job-id="jobId"
            :device="graph.selectedDevice"
            @request-booking="requestBooking"
            @remove="removeDevice"
          />
        </q-card>
      </div>
    </div>

    <q-dialog
      v-if="$q.screen.lt.md"
      :model-value="inspectorOpen"
      position="bottom"
      @update:model-value="(v) => !v && ((graph.selectedDeviceId = null), (selectedOutletId = null))"
    >
      <q-card style="width: 100%; max-height: 80vh; overflow: auto">
        <OutletInspector
          v-if="selectedOutlet"
          :outlet="selectedOutlet"
          :groups="plotFrame.groups.value"
          :venue-id="plotFrame.job.value.venue_id"
          :job-id="jobId"
          @close="selectedOutletId = null"
          @changed="plotFrame.load()"
        />
        <DeviceInspector
          v-else
          :job-id="jobId"
          :device="graph.selectedDevice"
          @request-booking="requestBooking"
          @remove="removeDevice"
        />
      </q-card>
    </q-dialog>

    <StockwireCatalogDrawer
      v-model="catalogOpen"
      :job-id="jobId"
      :stockwire-job-id="job?.stockwire_job_id || null"
    />
  </q-page>
</template>

<script setup>
import { apiErrorText } from '@/utils/errors';
import { isRevisionConflict } from '@/utils/graph';
import OutletInspector from '@/components/OutletInspector.vue';
import CableRoutingPanel from '@/components/CableRoutingPanel.vue';
import { buildCableRowsFromGraph } from '@/utils/graphLegacy';
import JobDetailsDialog from '@/components/JobDetailsDialog.vue';
import StockwireAvailabilityPanel from '@/components/StockwireAvailabilityPanel.vue';
import { useStockwireStore } from '@/stores/stockwire';
import StageVenueDialog from '@/components/StageVenueDialog.vue';
import ReportGenerationDialog from '@/components/ReportGenerationDialog.vue';
import { elementsFromGraph, legacyId } from '@/utils/graphLegacy';
import { usePlotFrame } from '@/composables/usePlotFrame';
import { GEAR_ELEMENTS, OBJECT_TYPES } from '@/utils/plotObjects';
import { useStagePlotStore } from '@/stores/stageplot';
import { fitWidthZoom, stageCentre, stagePosition } from '@/utils/plotFrame';
import { computed, onBeforeUnmount, onMounted, ref, watch, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { api } from '@/boot/api';
import { useGraphStore } from '@/stores/graph';
import { useJobSocket } from '@/composables/useJobSocket';
import {
  PRODUCT_MIME,
  deviceFromProduct,
  devicesShownAsElements,
  isPlotElement,
  isVirtual,
  linkRoleFor,
  phaseStatus,
  suggestPorts,
  visibleOnLayers,
} from '@/utils/workspace';
import ConflictDialog from '@/components/ConflictDialog.vue';
import DeviceInspector from '@/components/DeviceInspector.vue';
import MultiDomainPatchDrawer from '@/components/MultiDomainPatchDrawer.vue';
import StockwireCatalogDrawer from '@/components/StockwireCatalogDrawer.vue';
import ChannelListEditor from '@/components/ChannelListEditor.vue';
import DeviceEditor from '@/components/DeviceEditor.vue';
import LightsEditor from '@/components/LightsEditor.vue';
import VideoEditor from '@/components/VideoEditor.vue';
import RiggingEditor from '@/components/RiggingEditor.vue';
import WorkspaceCanvas from '@/components/WorkspaceCanvas.vue';
import WorkspaceTable from '@/components/WorkspaceTable.vue';

const LAYERS = [
  { key: 'audio', label: 'workspace.layerAudio' },
  { key: 'lighting', label: 'workspace.layerLighting' },
  { key: 'video', label: 'workspace.layerVideo' },
  { key: 'power', label: 'workspace.layerPower' },
];
const SIGNAL_LAYER = { audio: 'audio', dmx: 'lighting', video: 'video', power: 'power' };
const LEVEL_COLOR = { ok: 'positive', warn: 'warning', over: 'negative' };

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const $q = useQuasar();
const graph = useGraphStore();
const jobId = String(route.params.jobId);

const job = ref(null);
const catalogOpen = ref(false);
const availabilityOpen = ref(false);
const importing = ref(false);
// The order follows how a job is built: the plan, then each discipline (sound, lights, video,
// power and rigging), then the cross-cutting gear views.
const modeTabs = computed(() => [
  { label: t('workspace.modeCanvas'), value: 'canvas', icon: 'map' },
  { label: t('workspace.modeLists'), value: 'lists', icon: 'queue_music' },
  { label: t('workspace.modeLights'), value: 'lights', icon: 'lightbulb' },
  { label: t('workspace.modeVideo'), value: 'video', icon: 'videocam' },
  { label: t('workspace.modePower'), value: 'power', icon: 'bolt' },
  { label: t('workspace.modeDevices'), value: 'devices', icon: 'developer_board' },
  { label: t('workspace.modeList'), value: 'list', icon: 'table_rows' },
]);
const zoom = ref(0.3);
const deviceScale = ref(1);
// The hand tool pans a zoomed-in map by dragging; holding Space does the same until released.
const handTool = ref(false);
const spaceHeld = ref(false);
const pan = ref({ x: 0, y: 0 });
const typing = (event) => ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target?.tagName) || event.target?.isContentEditable;
function onKey(event) {
  if (event.code !== 'Space' || typing(event) || graph.mode !== 'canvas') return;
  event.preventDefault();
  spaceHeld.value = event.type === 'keydown';
}
const plotFrame = usePlotFrame(jobId);
const connectMode = ref(false);
const plugins = ref([]);
const layers = reactive({ audio: true, lighting: true, video: true, power: true });

const phases = computed(() => phaseStatus(graph.loads));
const listDevices = computed(() =>
  graph.devices
    .filter((d) => !isVirtual(d) && !isPlotElement(d) && visibleOnLayers(d, layers))
    .sort((a, b) => (a.domain === b.domain ? a.position - b.position : a.domain.localeCompare(b.domain))),
);
const shownAsElements = computed(() => devicesShownAsElements(graph.edges));
const canvasDevices = computed(() =>
  graph.devices.filter(
    (d) =>
      visibleOnLayers(d, layers) &&
      !isVirtual(d) &&
      !shownAsElements.value.has(d.id) &&
      d.canvas_x_cm != null &&
      d.canvas_y_cm != null,
  ),
);
// Gear is on the stage plot once it has a position. Anything else is offered as a chip to place,
// so the canvas never shows gear that is not part of the plot.
const unplacedGear = computed(() =>
  graph.devices.filter(
    (d) =>
      visibleOnLayers(d, layers) &&
      !isVirtual(d) &&
      !isPlotElement(d) &&
      !shownAsElements.value.has(d.id) &&
      (d.canvas_x_cm == null || d.canvas_y_cm == null),
  ),
);
// Camera and projector views of the placed plot elements (see utils/plotViews.js).
const viewShapes = computed(() => {
  const elements = elementsFromGraph(graph.devices, graph.edges);
  const byLegacy = new Map(graph.devices.map((d) => [legacyId(d), d]));
  return plotFrame.viewShapes(elements, (el) => byLegacy.get(el.linked_device_id)?.attributes || null);
});
const canvasEdges = computed(() =>
  graph.edges.filter((e) => e.signal !== 'link' && layers[SIGNAL_LAYER[e.signal]] !== false),
);
const inspectorOpen = computed(() => Boolean(graph.selectedDevice) || Boolean(selectedOutlet.value));

const modeKey = `sw_ws_mode_${jobId}`;
const errorText = (err) => apiErrorText(err);

let checkTimer = null;
function scheduleChecks() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(() => graph.refreshChecks(jobId).catch(() => {}), 400);
}

const socket = useJobSocket(jobId, (event) => {
  if (event.type?.startsWith('graph.')) {
    graph.applyRealtimeEvent(event);
    scheduleChecks();
  }
});

// The user's own changes after a conflict are sent again; if that fails they are told why (the
// dialog has already closed, so the draft is part of the message).
async function resolveConflict(resolution) {
  try {
    await graph.resolveConflict(resolution);
  } catch (err) {
    if (!isRevisionConflict(err)) {
      $q.notify({ type: 'negative', message: `${t('workspace.conflictFailed')}: ${errorText(err)}` });
    }
  }
}

function select(id) {
  selectedOutletId.value = null;
  graph.selectedDeviceId = id;
}

async function switchMode(mode) {
  graph.setMode(mode);
  try {
    localStorage.setItem(modeKey, graph.mode);
  } catch {
    /* storage unavailable */
  }
}

async function move({ id, x, y }) {
  try {
    await graph.updateDevice(jobId, id, { canvas_x_cm: x, canvas_y_cm: y });
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: errorText(err) });
  }
}

// Dropping a connection on a venue outlet marker plugs the gear into that outlet: the outlet's
// power group (or the outlet alone) becomes a source in the power tree and the gear is plugged
// into it. A speaker or screen element needs a device to take power; the server says if not.
async function plugIntoOutlet(srcId, outletId) {
  const gear = graph.devices.find((d) => d.id === srcId);
  try {
    const { node, connector } = await graph.outletSource(jobId, outletId);
    await graph.assignLoad(jobId, srcId, { power_node_id: node.id, power_connector: connector });
    $q.notify({ type: 'positive', message: t('workspace.pluggedInto', { name: gear?.name || '', outlet: node.name }) });
    plotFrame.load();
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

// Outlets belong to the venue; moving one on the map saves its place for every job in that venue.
async function moveOutlet({ id, x, y }) {
  const venueId = plotFrame.job.value?.venue_id;
  if (!venueId) return;
  try {
    await api.patch(`/venues/${venueId}/power-outlets/${id}`, { x_cm: x, y_cm: y });
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
  await plotFrame.load();
}

async function connectDevices({ srcId, dstId }) {
  if (String(dstId).startsWith('outlet:')) {
    await plugIntoOutlet(srcId, dstId.slice('outlet:'.length));
    return;
  }
  const src = graph.devices.find((d) => d.id === srcId);
  const dst = graph.devices.find((d) => d.id === dstId);
  if (isPlotElement(src)) {
    try {
      await graph.createEdge(jobId, {
        signal: 'link',
        src_device_id: srcId,
        src_port: 'link',
        dst_device_id: dstId,
        dst_port: linkRoleFor(dst),
      });
    } catch (err) {
      $q.notify({ type: 'negative', message: errorText(err) });
    }
    return;
  }
  const fit = suggestPorts(src, dst);
  if (!fit) {
    $q.notify({ type: 'negative', message: t('workspace.noFreePorts', { from: src.name, to: dst.name }) });
    return;
  }
  const payload = {
    signal: fit.signal,
    src_device_id: srcId,
    src_port: fit.srcPort,
    dst_device_id: dstId,
    dst_port: fit.dstPort,
    channels: 1,
  };
  try {
    await graph.createEdge(jobId, payload);
  } catch (err) {
    const detail = err.response?.data?.detail;
    if (detail?.code === 'invalid_connection') {
      $q.notify({
        type: 'negative',
        message: `${t('workspace.connectFailed')}: ${detail.issues.map((i) => i.message).join('; ')}`,
        actions: [
          {
            label: t('workspace.connectForce'),
            color: 'white',
            handler: () =>
              graph
                .createEdge(jobId, payload, { force: true })
                .catch((e) => $q.notify({ type: 'negative', message: errorText(e) })),
          },
        ],
      });
    } else {
      $q.notify({ type: 'negative', message: typeof detail === 'string' ? detail : err.message });
    }
  }
}

async function onProductDrop(event) {
  const raw = event.dataTransfer?.getData(PRODUCT_MIME);
  if (!raw) return;
  const products = JSON.parse(raw);
  const canvas = event.target.closest?.('[data-testid="workspace-canvas"]');
  const rect = canvas?.getBoundingClientRect();
  try {
    const payloads = products.map((product, index) => {
      const device = deviceFromProduct(product);
      if (rect && graph.mode === 'canvas') {
        const at = stagePosition(
          event.clientX + index * 20 - rect.left,
          event.clientY + index * 20 - rect.top,
          zoom.value,
          plotFrame.frame.value,
          pan.value,
        );
        device.canvas_x_cm = at.x;
        device.canvas_y_cm = at.y;
      }
      return device;
    });
    const created = await graph.createDevices(jobId, payloads);
    $q.notify({ type: 'positive', message: t('workspace.added', { n: created.length }) });
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

function fitCanvas() {
  const width = document.querySelector('[data-testid="workspace-canvas"]')?.clientWidth || 800;
  zoom.value = fitWidthZoom(plotFrame.frame.value, width);
}

async function placeGear(device) {
  const centre = stageCentre(plotFrame.frame.value);
  const offset = (graph.devices.filter((d) => d.canvas_x_cm != null).length % 5) * 20;
  try {
    await graph.updateDevice(jobId, device.id, {
      canvas_x_cm: centre.x + offset,
      canvas_y_cm: centre.y + offset,
    });
  } catch (err) {
    if (!isRevisionConflict(err)) $q.notify({ type: 'negative', message: errorText(err) });
  }
}

async function loadPlugins() {
  if (plugins.value.length) return;
  plugins.value = await graph.exportPlugins(jobId).catch(() => []);
}

async function exportList(list, plugin) {
  try {
    const { blob, filename } = await graph.exportList(jobId, list.id, plugin.key);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    $q.notify({ type: 'negative', message: t('workspace.exportFailed') });
  }
}

const importInput = ref(null);
const reportDialog = ref(false);
const stageVenueOpen = ref(false);

// Outlets belong to the venue. A job without a venue gets one (after a confirmation) made from its
// current stage and venue sizes, so adding an outlet here needs no detour through the venues.
async function ensureVenue() {
  const current = plotFrame.job.value;
  if (current?.venue_id) return current.venue_id;
  const name = current?.venue_name || current?.title || t('workspace.newVenue');
  const confirmed = await new Promise((resolve) => {
    $q.dialog({
      title: t('workspace.addOutletOnMap'),
      message: t('workspace.createVenueConfirm', { name }),
      cancel: true,
      persistent: true,
    })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false));
  });
  if (!confirmed) return null;
  const frame = plotFrame.frame.value;
  const { data: venue } = await api.post('/venues', {
    name,
    venue_width_cm: frame.venueW,
    venue_height_cm: frame.venueH,
    stage_x_cm: frame.stageX,
    stage_y_cm: frame.stageY,
    stage_width_cm: frame.stageW,
    stage_height_cm: frame.stageH,
    audience_polygon: frame.audience,
  });
  await api.put(`/jobs/${jobId}/venue`, { venue_id: venue.id });
  await reloadJob();
  return venue.id;
}

async function addOutletOnMap() {
  try {
    const venueId = await ensureVenue();
    if (!venueId) return;
    const centre = stageCentre(plotFrame.frame.value, 20);
    const { data: outlet } = await api.post(`/venues/${venueId}/power-outlets`, {
      name: `${t('workspace.venueOutlet')} ${plotFrame.outlets.value.length + 1}`,
      connector: 'schuko',
      x_cm: centre.x,
      y_cm: centre.y,
    });
    await plotFrame.load();
    plotFrame.show.outlets.value = true;
    selectOutlet(outlet.id);
    $q.notify({ type: 'positive', message: t('workspace.outletAdded', { name: outlet.name }) });
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

// A venue outlet picked on the map is shown in the inspector in place of a device.
const selectedOutletId = ref(null);
const selectedOutlet = computed(
  () => plotFrame.outlets.value.find((o) => o.id === selectedOutletId.value) || null,
);
function selectOutlet(id) {
  selectedOutletId.value = id;
  graph.selectedDeviceId = null;
}

// Cables are derived from the chains and routed along the cableways (utils/cables.js); only the
// settings and the cableways are stored, on the job. Drawing a cableway adds points with a click
// on the map and saves the way when finished.
const drawingWay = ref(false);

// The audience area (venue cm) is outlined with clicks on the map and saved on the job; cables
// avoid it. "Save as the venue's area" keeps it for the next job in that venue.
const drawingAudience = ref(false);
const audiencePoints = ref([]);
const startAudience = () => {
  cancelDrawWay();
  rerouteKey.value = null;
  audiencePoints.value = [];
  drawingAudience.value = true;
};
const cancelAudience = () => {
  drawingAudience.value = false;
  audiencePoints.value = [];
};
async function saveAudience(polygon) {
  try {
    await api.patch(`/jobs/${jobId}`, { audience_polygon: polygon });
    await plotFrame.load();
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}
async function finishAudience() {
  if (audiencePoints.value.length < 3) return;
  const polygon = audiencePoints.value;
  cancelAudience();
  await saveAudience(polygon);
}
async function saveAudienceToVenue() {
  try {
    await api.patch(`/venues/${plotFrame.job.value.venue_id}`, {
      audience_polygon: plotFrame.frame.value.audience,
    });
    $q.notify({ type: 'positive', message: t('workspace.audienceSavedToVenue') });
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}
const drawPoints = ref([]);
const cableRows = computed(() => {
  if (!graph.devices.length) return [];
  const frame = plotFrame.frame.value;
  return buildCableRowsFromGraph({
    devices: graph.devices,
    edges: graph.edges,
    plan: plotFrame.job.value?.cable_plan,
    audience: frame.audience,
    stageOffset: [frame.stageX, frame.stageY],
  });
});
const startDrawWay = () => {
  cancelAudience();
  rerouteKey.value = null;
  drawPoints.value = [];
  drawingWay.value = true;
};
const cancelDrawWay = () => {
  drawingWay.value = false;
  drawPoints.value = [];
};
function finishDrawWay() {
  if (drawPoints.value.length < 2) return;
  const plan = plotFrame.cablePlan.value;
  plotFrame.savePlan({
    ...plan,
    cableways: [...plan.cableways, { id: crypto.randomUUID(), points: drawPoints.value }],
  });
  cancelDrawWay();
}
const removeCableway = (id) => {
  const plan = plotFrame.cablePlan.value;
  plotFrame.savePlan({ ...plan, cableways: plan.cableways.filter((w) => w.id !== id) });
};
// A cable's route is stored per cable key in cable_plan.routes: { mode: 'auto'|'manual', waypoints,
// hidden }. The key is derived from the chain (utils/cables.js), so it survives a reload. Starting
// a reroute keeps the existing waypoints of a manual route; hiding is independent of the mode.
const rerouteKey = ref(null);
const rerouteRow = computed(() => cableRows.value.find((r) => r.key === rerouteKey.value) || null);
const rerouteWaypoints = computed(() => plotFrame.cablePlan.value.routes[rerouteKey.value]?.waypoints || []);
function updateRoute(key, patch) {
  const plan = plotFrame.cablePlan.value;
  const current = plan.routes[key] || { mode: 'auto', waypoints: [], hidden: false };
  plotFrame.savePlan({ ...plan, routes: { ...plan.routes, [key]: { ...current, ...patch } } });
}
const toggleCableHidden = (row) => updateRoute(row.key, { hidden: !row.hidden });
function startReroute(row) {
  cancelDrawWay();
  cancelAudience();
  rerouteKey.value = row.key;
  updateRoute(row.key, { mode: 'manual', waypoints: row.requestedMode === 'manual' ? row.waypoints : [] });
}
function resetRoute(row) {
  updateRoute(row.key, { mode: 'auto', waypoints: [] });
  if (rerouteKey.value === row.key) rerouteKey.value = null;
}
function addWaypoint(cm) {
  if (!rerouteKey.value) return;
  updateRoute(rerouteKey.value, { mode: 'manual', waypoints: [...rerouteWaypoints.value, cm] });
}
function undoWaypoint() {
  if (!rerouteKey.value) return;
  updateRoute(rerouteKey.value, { mode: 'manual', waypoints: rerouteWaypoints.value.slice(0, -1) });
}
const saveCableSettings = (patch) => {
  const plan = plotFrame.cablePlan.value;
  plotFrame.savePlan({ ...plan, settings: { ...plan.settings, ...patch } });
};
const jobDialog = ref(false);
const stockwireStore = useStockwireStore();

async function reloadJob() {
  try {
    job.value = (await api.get(`/jobs/${jobId}`)).data;
    await plotFrame.load();
  } catch {
    /* the header keeps what it had */
  }
}

// The tab is opened first and pointed at the link once it is known: a window opened after the
// wait would be blocked as a popup by iOS Safari and installed apps.
async function openInStockwire() {
  const tab = window.open('', '_blank');
  try {
    const url = await stockwireStore.jobDeeplink(jobId);
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (err) {
    tab?.close();
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}
const stagePlot = useStagePlotStore();
const objectLabel = (object) => (object.labelKey ? t(object.labelKey, object.label || object.type) : object.label);

async function stageVenueSaved() {
  await plotFrame.load();
  fitCanvas();
}

// A plot object (performer, table, riser, ...) is a plot element: it has a position and size and
// can be linked to a channel or device, but it is not gear. It is placed in the middle of the stage.
// Gear on the plot (speakers, cameras, projectors, lights, mixers ...) is an element linked to a
// device: an unplaced device of the type is taken, else one is made for types that need it. A
// speaker also gets the coverage it throws, which feeds the sound coverage layer.
async function addGearElement(gear) {
  const centre = stageCentre(plotFrame.frame.value, Math.max(gear.w, gear.h));
  try {
    const placed = new Set(stagePlot.elements.map((e) => e.linked_device_id).filter(Boolean));
    let device = gear.deviceType
      ? graph.devices.find((d) => d.kind === gear.deviceType && d.legacy_ref?.startsWith('device:') && !placed.has(legacyId(d)))
      : null;
    if (!device && gear.createDevice) {
      const count = graph.devices.filter((d) => d.kind === gear.deviceType).length;
      device = await graph.createAudioDevice(jobId, {
        name: `${objectLabel(gear)} ${count + 1}`,
        device_type: gear.deviceType,
      });
    }
    const created = await stagePlot.createElement(jobId, {
      element_type: gear.type,
      label: device?.name || objectLabel(gear),
      position_x: centre.x,
      position_y: centre.y,
      rotation: gear.rotation ?? 0,
      width_cm: gear.w,
      height_cm: gear.h,
      linked_device_id: device ? legacyId(device) : null,
      ...(gear.coverageAngle ? { coverage_angle_h: gear.coverageAngle, coverage_distance_m: gear.coverageDistance } : {}),
    });
    graph.selectedDeviceId = stagePlot.nodeOf(created.id)?.id || null;
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

async function addObject(object) {
  const centre = stageCentre(plotFrame.frame.value, Math.max(object.w, object.h));
  try {
    const created = await stagePlot.createElement(jobId, {
      element_type: object.type,
      label: objectLabel(object),
      position_x: centre.x,
      position_y: centre.y,
      width_cm: object.w,
      height_cm: object.h,
    });
    graph.selectedDeviceId = stagePlot.nodeOf(created.id)?.id || null;
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  }
}

// Import brings in what was made elsewhere: today a fixture patch (CSV, or an MVR export from
// Capture, MA, Vectorworks or WYSIWYG). Fixtures land in the lights editor like added ones.
async function importFixturesFile(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  importing.value = true;
  try {
    const result = await graph.importFixtures(jobId, file);
    $q.notify({
      type: result.errors?.length ? 'warning' : 'positive',
      message: result.errors?.length
        ? `${t('workspace.imported', { n: result.created })} ${t('workspace.importSkipped', { n: result.errors.length, why: result.errors.slice(0, 3).map((e) => e.message || e.error || e).join('; ') })}`
        : t('workspace.imported', { n: result.created }),
    });
    scheduleChecks();
  } catch (err) {
    $q.notify({ type: 'negative', message: errorText(err) });
  } finally {
    importing.value = false;
  }
}

async function requestBooking(device) {
  try {
    await graph.requestStockwireBooking(jobId, device.id);
    $q.notify({ type: 'positive', message: t('workspace.requestSent', { name: device.name }) });
  } catch (err) {
    const message =
      err.response?.status === 409
        ? t('workspace.requestNoJob')
        : `${t('workspace.requestFailed')}: ${errorText(err)}`;
    $q.notify({ type: 'negative', message });
  }
}

function removeDevice(device) {
  $q.dialog({
    title: t('workspace.remove'),
    message: device.name,
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await graph.deleteDevice(jobId, device.id);
      graph.selectedDeviceId = null;
      scheduleChecks();
    } catch (err) {
      if (!isRevisionConflict(err)) {
        $q.notify({ type: 'negative', message: t('workspace.removeFail') });
      }
    }
  });
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey, true);
  window.removeEventListener('keyup', onKey, true);
});

watch(
  () => graph.edges.length,
  () => scheduleChecks(),
);

// Coverage comes from the placed speakers and cameras, so it is recomputed when they change.
let coverageTimer = null;
watch(
  () =>
    graph.devices
      .filter((d) => d.canvas_x_cm != null)
      .map((d) => [d.id, d.canvas_x_cm, d.canvas_y_cm, d.canvas_rotation, d.revision].join(':'))
      .join('|'),
  () => {
    clearTimeout(coverageTimer);
    coverageTimer = setTimeout(() => {
      plotFrame.loadCoverage();
      plotFrame.loadCameraSpecs();
    }, 400);
  },
);

// fetchGraph reports its own failure in graph.error (shown as a banner with a retry); the stage
// frame reports its own too.
async function loadWorkspace() {
  await Promise.all([graph.fetchGraph(jobId), plotFrame.load()]);
}

onMounted(async () => {
  // capture phase: Quasar buttons stop Space from bubbling when one has focus
  window.addEventListener('keydown', onKey, true);
  window.addEventListener('keyup', onKey, true);
  try {
    const { data } = await api.get(`/jobs/${jobId}`);
    job.value = data;
  } catch (err) {
    $q.notify({ type: 'warning', message: `${t('workspace.jobLoadFailed')}: ${errorText(err)}` });
  }
  // ?view= opens a mode directly (the old page URLs redirect here with it); otherwise the mode
  // this browser used last
  const wanted = modeTabs.value.find((m) => m.value === route.query.view)?.value;
  try {
    graph.setMode(wanted || localStorage.getItem(modeKey) || 'canvas');
  } catch {
    graph.setMode(wanted || 'canvas');
  }
  graph.selectedDeviceId = null;
  await loadWorkspace();
  fitCanvas();
  scheduleChecks();
  socket.connect();
});
</script>

<style scoped>
.inspector-sticky {
  position: sticky;
  top: 8px;
  max-height: calc(100vh - 16px);
  overflow-y: auto;
}
</style>
