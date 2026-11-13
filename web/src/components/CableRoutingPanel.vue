<template>
  <q-expansion-item
    icon="cable"
    :label="t('cables.title')"
    :caption="caption"
    class="q-mt-md"
    header-class="bg-grey-9 text-white"
    data-testid="cable-routing"
  >
    <q-card flat>
      <q-card-section>
        <div class="row items-center q-gutter-sm q-mb-sm">
          <q-btn
            v-if="!drawing"
            outline
            dense
            no-caps
            color="primary"
            icon="timeline"
            :label="t('cables.drawWay')"
            data-testid="draw-cableway"
            @click="emit('draw-start')"
          />
          <template v-else>
            <span class="text-caption text-grey-6">{{ t('cables.drawHint') }}</span>
            <q-btn
              dense
              no-caps
              color="primary"
              icon="check"
              :label="t('cables.finishWay')"
              :disable="drawPoints.length < 2"
              data-testid="finish-cableway"
              @click="emit('draw-finish')"
            />
            <q-btn
              flat
              dense
              no-caps
              icon="undo"
              :label="t('cables.undoPoint')"
              :disable="!drawPoints.length"
              @click="emit('draw-undo')"
            />
            <q-btn
              flat
              dense
              no-caps
              :label="t('common.cancel')"
              @click="emit('draw-cancel')"
            />
          </template>
          <q-space />
          <q-btn
            flat
            dense
            no-caps
            icon="download"
            :label="t('cables.exportCsv')"
            :disable="!rows.length"
            @click="exportCsv"
          />
        </div>

        <div class="text-subtitle2 q-mb-xs">
          {{ t('cables.routingTitle') }}
        </div>
        <div class="row q-col-gutter-sm q-mb-md">
          <q-input
            :model-value="settings.slack_pct"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            min="0"
            :label="t('cables.slackPct')"
            data-testid="cable-slack-pct"
            @change="(v) => emit('settings', { slack_pct: Number(v) || 0 })"
          />
          <q-input
            :model-value="settings.slack_m"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            min="0"
            step="0.5"
            :label="t('cables.slackM')"
            @change="(v) => emit('settings', { slack_m: Number(v) || 0 })"
          />
          <q-input
            :model-value="settings.cableway_factor"
            class="col-6 col-sm-3"
            dense
            outlined
            type="number"
            min="0"
            max="1"
            step="0.1"
            :label="t('cables.cablewayFactor')"
            data-testid="cable-way-factor"
            @change="(v) => emit('settings', { cableway_factor: Math.min(1, Math.max(0, Number(v) || 0)) })"
          />
          <q-input
            :model-value="(settings.standard_lengths_m || []).join(', ')"
            class="col-12 col-sm-3"
            dense
            outlined
            :label="t('cables.standardLengths')"
            data-testid="cable-standard-lengths"
            @change="(v) => emit('settings', { standard_lengths_m: lengths(v) })"
          />
        </div>

        <div class="text-subtitle2 q-mb-xs">
          {{ t('cables.waysTitle') }}
        </div>
        <div
          v-if="!cableways.length"
          class="text-grey-6 q-mb-sm"
        >
          {{ t('cables.noWays') }}
        </div>
        <div
          v-for="(way, i) in cableways"
          :key="way.id"
          class="row items-center q-gutter-sm"
          data-testid="cableway"
        >
          <div class="col">
            {{ t('cables.wayLabel', { n: i + 1 }) }}
            <span class="text-grey-6">({{ way.points.length }} {{ t('cables.points') }})</span>
          </div>
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="delete"
            :aria-label="t('cables.deleteWay')"
            :disable="drawing"
            @click="emit('delete-way', way.id)"
          />
        </div>

        <div class="text-subtitle2 q-mt-md q-mb-xs">
          {{ t('cables.order') }}
        </div>
        <div
          v-if="!rows.length"
          class="text-grey-6"
        >
          {{ t('cables.none') }}
        </div>
        <AdaptiveTable
          v-else
          table-id="cable-routing"
          flat
          dense
          bordered
          :rows="rows"
          :columns="columns"
          row-key="key"
          :rows-per-page-options="[0]"
          hide-bottom
          class="sticky-header-table"
          style="max-height: 40vh"
          data-testid="cable-table"
        >
          <template #body="bp">
            <q-tr
              :props="bp"
              :class="{ 'bg-grey-9': rerouteKey === bp.row.key }"
              :data-testid="`cable-row-${bp.row.index}`"
            >
              <q-td
                v-for="col in bp.cols"
                :key="col.name"
                :props="{ ...bp, col, value: undefined }"
                :class="col.name === 'actions' ? 'no-wrap' : ''"
              >
                <template v-if="col.name === 'from'">
                  {{ bp.row.fromName }}
                </template>
                <template v-else-if="col.name === 'to'">
                  {{ bp.row.toName }}
                </template>
                <template v-else-if="col.name === 'route'">
                  <span v-if="bp.row.placed">{{ t(`cables.route.${bp.row.mode}`) }}</span>
                  <span
                    v-else
                    class="text-warning"
                  >{{ t('cables.notPlaced') }}</span>
                  <q-icon
                    v-if="bp.row.crossesAudience"
                    name="warning"
                    color="warning"
                  >
                    <q-tooltip>{{ t('cables.crossesAudience') }}</q-tooltip>
                  </q-icon>
                </template>
                <template v-else-if="col.name === 'pathM'">
                  {{ bp.row.pathM ?? '–' }}
                </template>
                <template v-else-if="col.name === 'neededM'">
                  {{ bp.row.requiredM ?? '–' }}
                </template>
                <template v-else-if="col.name === 'lengthClass'">
                  {{ bp.row.placed ? (bp.row.assignedM === null ? t('cables.overMax') : `${bp.row.assignedM} m`) : '–' }}
                </template>
                <template v-else-if="col.name === 'actions'">
                  <q-btn
                    flat
                    dense
                    round
                    :icon="bp.row.hidden ? 'visibility_off' : 'visibility'"
                    :aria-label="bp.row.hidden ? t('cables.showCable') : t('cables.hideCable')"
                    data-testid="cable-hide"
                    @click="emit('toggle-hidden', bp.row)"
                  >
                    <q-tooltip>{{ t('cables.hideTip') }}</q-tooltip>
                  </q-btn>
                  <q-btn
                    flat
                    dense
                    round
                    icon="alt_route"
                    :color="rerouteKey === bp.row.key ? 'primary' : undefined"
                    :disable="!bp.row.placed"
                    :aria-label="t('cables.rerouteAction')"
                    data-testid="cable-reroute"
                    @click="emit('reroute', bp.row)"
                  >
                    <q-tooltip>{{ bp.row.placed ? t('cables.rerouteTip') : t('cables.rerouteDisabledTip') }}</q-tooltip>
                  </q-btn>
                  <q-btn
                    v-if="bp.row.requestedMode === 'manual'"
                    flat
                    dense
                    round
                    icon="auto_fix_high"
                    :aria-label="t('cables.autoRouteAction')"
                    data-testid="cable-auto-route"
                    @click="emit('reset-route', bp.row)"
                  >
                    <q-tooltip>{{ t('cables.autoRouteTip') }}</q-tooltip>
                  </q-btn>
                </template>
              </q-td>
            </q-tr>
          </template>
        </AdaptiveTable>
      </q-card-section>
    </q-card>
  </q-expansion-item>
</template>

<script setup>
import { computed } from 'vue';
import AdaptiveTable from '@/components/AdaptiveTable.vue';
import { useI18n } from 'vue-i18n';
import { cableTypeCsv, cablesToCsv } from '@/utils/cables';

// How cables are laid out on the plan: the slack added to each run, the standard lengths a run is
// rounded up to, how strongly runs prefer cableways, and the cableways themselves (drawn on the
// map). Cables are derived from the signal chains and routed along the cableways automatically;
// the settings live on the job (cable_plan) like on the stage plot page.
const props = defineProps({
  rows: { type: Array, default: () => [] },
  settings: { type: Object, required: true },
  cableways: { type: Array, default: () => [] },
  drawing: { type: Boolean, default: false },
  drawPoints: { type: Array, default: () => [] },
  // the cable whose manual waypoints are being placed on the map
  rerouteKey: { type: String, default: null },
});
// Layout meta per column (see utils/columnLayout.js); the row's buttons are the actions column.
const columns = computed(() => [
  { name: 'from', label: t('workspace.colFrom'), align: 'left', min: 130, width: 180, grow: 2, required: true },
  { name: 'to', label: t('workspace.colTo'), align: 'left', min: 130, width: 180, grow: 2 },
  { name: 'route', label: t('cables.routeColumn'), align: 'left', min: 120, width: 150, grow: 1 },
  { name: 'pathM', label: t('cables.pathM'), align: 'right', min: 80, width: 96, grow: 0 },
  { name: 'neededM', label: t('cables.neededM'), align: 'right', min: 80, width: 96, grow: 0 },
  { name: 'lengthClass', label: t('cables.lengthClass'), align: 'right', min: 90, width: 110, grow: 0 },
  { name: 'actions', label: '', align: 'right', min: 120, width: 130, grow: 0 },
]);

const emit = defineEmits(['settings', 'draw-start', 'draw-finish', 'draw-undo', 'draw-cancel', 'delete-way', 'toggle-hidden', 'reroute', 'reset-route']);
const { t } = useI18n();

const caption = computed(() => `${props.rows.length} · ${props.cableways.length} ${t('cables.waysTitle').toLowerCase()}`);

function lengths(text) {
  return String(text)
    .split(',')
    .map((v) => Number(v.trim()))
    .filter((v) => v > 0)
    .sort((a, b) => a - b);
}

function exportCsv() {
  const blob = new Blob([`${cablesToCsv(props.rows)}\n\n${cableTypeCsv(props.rows)}`], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'cables.csv';
  link.click();
  URL.revokeObjectURL(url);
}
</script>
