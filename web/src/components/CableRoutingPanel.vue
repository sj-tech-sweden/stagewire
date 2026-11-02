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
        <q-markup-table
          v-else
          flat
          dense
          bordered
          class="sticky-header-table"
          style="max-height: 40vh"
          data-testid="cable-table"
        >
          <thead>
            <tr>
              <th class="text-left">
                {{ t('workspace.colFrom') }}
              </th>
              <th class="text-left">
                {{ t('workspace.colTo') }}
              </th>
              <th class="text-left">
                {{ t('cables.routeColumn') }}
              </th>
              <th class="text-right">
                {{ t('cables.pathM') }}
              </th>
              <th class="text-right">
                {{ t('cables.neededM') }}
              </th>
              <th class="text-right">
                {{ t('cables.lengthClass') }}
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.key"
              :class="{ 'bg-grey-9': rerouteKey === row.key }"
              :data-testid="`cable-row-${row.index}`"
            >
              <td>{{ row.fromName }}</td>
              <td>{{ row.toName }}</td>
              <td>
                <span v-if="row.placed">{{ t(`cables.route.${row.mode}`) }}</span>
                <span
                  v-else
                  class="text-warning"
                >{{ t('cables.notPlaced') }}</span>
                <q-icon
                  v-if="row.crossesAudience"
                  name="warning"
                  color="warning"
                >
                  <q-tooltip>{{ t('cables.crossesAudience') }}</q-tooltip>
                </q-icon>
              </td>
              <td class="text-right">
                {{ row.pathM ?? '–' }}
              </td>
              <td class="text-right">
                {{ row.requiredM ?? '–' }}
              </td>
              <td class="text-right">
                {{ row.placed ? (row.assignedM === null ? t('cables.overMax') : `${row.assignedM} m`) : '–' }}
              </td>
              <td class="text-right no-wrap">
                <q-btn
                  flat
                  dense
                  round
                  :icon="row.hidden ? 'visibility_off' : 'visibility'"
                  :aria-label="row.hidden ? t('cables.showCable') : t('cables.hideCable')"
                  data-testid="cable-hide"
                  @click="emit('toggle-hidden', row)"
                >
                  <q-tooltip>{{ t('cables.hideTip') }}</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  dense
                  round
                  icon="alt_route"
                  :color="rerouteKey === row.key ? 'primary' : undefined"
                  :disable="!row.placed"
                  :aria-label="t('cables.rerouteAction')"
                  data-testid="cable-reroute"
                  @click="emit('reroute', row)"
                >
                  <q-tooltip>{{ row.placed ? t('cables.rerouteTip') : t('cables.rerouteDisabledTip') }}</q-tooltip>
                </q-btn>
                <q-btn
                  v-if="row.requestedMode === 'manual'"
                  flat
                  dense
                  round
                  icon="auto_fix_high"
                  :aria-label="t('cables.autoRouteAction')"
                  data-testid="cable-auto-route"
                  @click="emit('reset-route', row)"
                >
                  <q-tooltip>{{ t('cables.autoRouteTip') }}</q-tooltip>
                </q-btn>
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>
    </q-card>
  </q-expansion-item>
</template>

<script setup>
import { computed } from 'vue';
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
