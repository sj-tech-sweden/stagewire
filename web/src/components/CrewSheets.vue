<template>
  <!-- Read-only Sound / Lights / Video sheets for the crew view. One component per tab; every row is
       a card-like list item so it works on a phone (no wide tables). Nothing here edits anything. -->
  <div :data-testid="`crew-${section}`">
    <div
      v-if="empty"
      class="text-grey-5 q-pa-md text-center"
      :data-testid="`crew-${section}-empty`"
    >
      {{ t('workspace.share.nothingHere') }}
    </div>

    <!-- SOUND ------------------------------------------------------------------------------------ -->
    <template v-else-if="section === 'sound'">
      <q-select
        v-if="sound.length > 1"
        v-model="listIdx"
        dense
        outlined
        dark
        emit-value
        map-options
        class="q-mb-sm"
        :options="sound.map((e, i) => ({ label: e.list.name, value: i }))"
      />
      <q-tabs
        v-model="soundTab"
        dense
        align="left"
        class="text-grey-4"
        no-caps
      >
        <q-tab
          name="inputs"
          :label="t('workspace.share.inputs')"
          data-testid="crew-sound-tab-inputs"
        />
        <q-tab
          name="buses"
          :label="t('workspace.share.buses')"
          data-testid="crew-sound-tab-buses"
        />
        <q-tab
          name="patch"
          :label="t('workspace.share.soundPatch')"
          data-testid="crew-sound-tab-patch"
        />
        <q-tab
          name="console"
          :label="t('workspace.share.console')"
          data-testid="crew-sound-tab-console"
        />
      </q-tabs>
      <q-separator dark />

      <q-list
        v-if="soundTab === 'inputs'"
        separator
        dark
        data-testid="crew-inputs"
      >
        <q-item
          v-for="r in inputRows"
          :key="r.id"
          dense
        >
          <q-item-section side>
            <span class="text-weight-bold">{{ r.number }}</span>
          </q-item-section>
          <q-item-section>
            <q-item-label>
              {{ r.name || '—' }}
              <q-icon
                v-if="r.phantom"
                name="bolt"
                size="1rem"
                color="warning"
                title="+48V"
              />
            </q-item-label>
            <q-item-label
              v-if="r.source || r.stand"
              caption
            >
              {{ [r.source, r.stand].filter(Boolean).join(' · ') }}
            </q-item-label>
            <q-item-label
              v-if="r.notes"
              caption
            >
              {{ r.notes }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <span class="text-caption">{{ r.patch || '—' }}</span>
            <span
              v-if="r.directOut"
              class="text-caption text-grey-5"
            >→ {{ r.directOut }}</span>
          </q-item-section>
        </q-item>
      </q-list>

      <q-list
        v-else-if="soundTab === 'buses'"
        separator
        dark
        data-testid="crew-buses"
      >
        <q-item
          v-for="b in busRows"
          :key="b.id"
        >
          <q-item-section>
            <q-item-label>{{ b.name }}</q-item-label>
            <q-item-label caption>
              {{ b.mode }} · {{ b.role }}
            </q-item-label>
            <q-item-label
              v-for="(o, i) in b.outputs"
              :key="i"
              caption
            >
              {{ o }}
            </q-item-label>
            <q-item-label
              v-if="b.notes"
              caption
            >
              {{ b.notes }}
            </q-item-label>
          </q-item-section>
        </q-item>
      </q-list>

      <q-list
        v-else-if="soundTab === 'patch'"
        separator
        dark
        dense
        data-testid="crew-patch"
      >
        <q-item
          v-for="s in socketRows"
          :key="s.key"
        >
          <q-item-section>
            <q-item-label>{{ s.device }} · {{ s.direction === 'out' ? t('console.outWord') : 'In' }} {{ s.socket }}</q-item-label>
            <q-item-label caption>
              {{ s.port }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <span class="text-white">{{ s.who }}</span>
          </q-item-section>
        </q-item>
      </q-list>

      <div
        v-else
        data-testid="crew-console"
        class="q-pt-sm"
      >
        <div
          v-if="consoleInfo.profile"
          class="text-subtitle2"
        >
          {{ consoleInfo.profile }}
        </div>
        <template v-if="consoleInfo.hasSurface">
          <div
            v-for="layer in consoleInfo.layers"
            :key="layer.layer"
            class="q-mt-sm"
          >
            <div class="text-caption text-grey-5">
              {{ t('workspace.share.layer', { n: layer.layer }) }}
            </div>
            <div
              v-for="bank in layer.banks"
              :key="bank.id"
              class="q-mb-xs"
            >
              <div class="text-caption text-weight-medium">
                {{ bank.label }}
              </div>
              <div class="crew-faders">
                <div
                  v-for="f in bank.faders"
                  :key="f.fader"
                  class="crew-fader"
                >
                  <span class="text-grey-6">{{ f.fader }}</span> {{ f.label || '' }}
                </div>
              </div>
            </div>
          </div>
        </template>
        <div
          v-if="consoleInfo.dcas.length"
          class="q-mt-md"
        >
          <div class="text-subtitle2">
            DCA
          </div>
          <div
            v-for="d in consoleInfo.dcas"
            :key="d.number"
            class="text-caption"
          >
            {{ d.number }} {{ d.name }}: {{ d.members.join(', ') || '—' }}
          </div>
        </div>
        <div
          v-if="consoleInfo.fx.length"
          class="q-mt-md"
        >
          <div class="text-subtitle2">
            FX
          </div>
          <div
            v-for="e in consoleInfo.fx"
            :key="e.id"
            class="text-caption"
          >
            {{ e.name || e.type }}: {{ e.sends.join(', ') || '—' }}
          </div>
        </div>
      </div>
    </template>

    <!-- LIGHTS: the DMX address list, per universe in address order -------------------------------- -->
    <template v-else-if="section === 'lights'">
      <q-input
        v-model="filter"
        dense
        outlined
        dark
        clearable
        class="q-mb-sm"
        :placeholder="t('workspace.share.search')"
        data-testid="crew-lights-search"
      />
      <div
        v-for="u in universes"
        :key="u.universe"
        class="q-mb-md"
      >
        <div class="text-subtitle2">
          {{ u.universe ? `${t('workspace.share.universe')} ${u.universe}` : t('workspace.share.noUniverse') }}
        </div>
        <q-list
          separator
          dark
          dense
          data-testid="crew-universe"
        >
          <q-item
            v-for="f in u.fixtures"
            :key="f.id"
          >
            <q-item-section side>
              <span
                class="text-weight-bold"
                :class="{ 'text-negative': f.conflict || f.overflow }"
              >{{ f.range || '—' }}</span>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ f.name }}</q-item-label>
              <q-item-label caption>
                {{ [f.type, f.mode, f.footprint ? `${f.footprint} ch` : '', f.location].filter(Boolean).join(' · ') }}
              </q-item-label>
              <q-item-label
                v-if="f.purpose || f.notes"
                caption
              >
                {{ [f.purpose, f.notes].filter(Boolean).join(' · ') }}
              </q-item-label>
            </q-item-section>
            <q-item-section
              v-if="f.conflict || f.overflow"
              side
            >
              <q-icon
                name="warning"
                color="negative"
                :title="f.conflict ? t('workspace.share.dmxConflict') : t('workspace.share.dmxOverflow')"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </div>
    </template>

    <!-- VIDEO: inputs and outputs per list -------------------------------------------------------- -->
    <template v-else>
      <div
        v-for="l in videoLists"
        :key="l.id"
        class="q-mb-md"
      >
        <div class="text-subtitle2">
          {{ l.name }}
        </div>
        <div class="text-caption text-grey-5">
          {{ t('workspace.share.inputs') }}
        </div>
        <q-list
          separator
          dark
          dense
          data-testid="crew-video-inputs"
        >
          <q-item
            v-for="i in l.inputs"
            :key="i.id"
          >
            <q-item-section side>
              <span class="text-weight-bold">{{ i.number }}</span>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ i.label || '—' }}</q-item-label>
              <q-item-label caption>
                {{ [i.type, i.connector, i.signal].filter(Boolean).join(' · ') }}
              </q-item-label>
              <q-item-label
                v-if="i.notes"
                caption
              >
                {{ i.notes }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
        <div class="text-caption text-grey-5 q-mt-sm">
          {{ t('workspace.share.outputs') }}
        </div>
        <q-list
          separator
          dark
          dense
          data-testid="crew-video-outputs"
        >
          <q-item
            v-for="o in l.outputs"
            :key="o.id"
          >
            <q-item-section side>
              <span class="text-weight-bold">{{ o.number }}</span>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ o.label || '—' }}</q-item-label>
              <q-item-label caption>
                {{ [o.destination !== o.label ? o.destination : '', o.connector, o.signal].filter(Boolean).join(' · ') }}
              </q-item-label>
              <q-item-label
                v-if="o.notes"
                caption
              >
                {{ o.notes }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { crewBusRows, crewConsole, crewInputRows, crewSocketRows, crewUniverses, crewVideo } from '@/utils/crewSheets';

const props = defineProps({
  // 'sound' | 'lights' | 'video'
  section: { type: String, required: true },
  // the crew-sheets payload ({sound, lights, video})
  sheets: { type: Object, default: () => ({}) },
});
const { t } = useI18n();

const sound = computed(() => props.sheets.sound || []);
const listIdx = ref(0);
const entry = computed(() => sound.value[listIdx.value] || sound.value[0] || null);
const soundTab = ref('inputs');
const inputRows = computed(() => crewInputRows(entry.value));
const busRows = computed(() => crewBusRows(entry.value, { out: t('console.outWord') }));
const socketRows = computed(() => crewSocketRows(entry.value));
const consoleInfo = computed(() => crewConsole(entry.value));

const filter = ref('');
const universes = computed(() => {
  const q = String(filter.value || '').trim().toLowerCase();
  const rows = (props.sheets.lights || []).filter(
    (f) => !q || [f.device_name, f.fixture_type, f.location, f.purpose, f.notes].join(' ').toLowerCase().includes(q),
  );
  return crewUniverses(rows);
});
const videoLists = computed(() => crewVideo(props.sheets.video));

const empty = computed(() => {
  if (props.section === 'sound') return !sound.value.length;
  if (props.section === 'lights') return !(props.sheets.lights || []).length;
  return !(props.sheets.video?.lists || []).length;
});
</script>

<style scoped>
.crew-faders { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 2px; }
.crew-fader { font-size: 0.75rem; padding: 2px 4px; background: rgba(255, 255, 255, 0.06); border-radius: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
