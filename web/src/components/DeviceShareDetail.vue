<template>
  <div class="text-white">
    <div
      v-if="device.notes"
      class="text-caption text-grey-5 q-mb-xs"
    >
      {{ device.notes }}
    </div>

    <!-- Network: IP/subnet/VLAN/protocols, with a quick-launch link to the device web UI. -->
    <section
      v-if="network"
      class="q-mb-sm"
    >
      <div class="text-caption text-grey-5 text-uppercase">
        {{ t('workspace.share.networkGroup') }}
      </div>
      <div class="row q-gutter-x-md q-gutter-y-xs">
        <div v-if="network.ip">
          <span class="text-grey-5">IP:</span>
          <a
            :href="`http://${network.ip}`"
            target="_blank"
            rel="noopener"
            class="text-primary"
          >
            {{ network.ip }}
          </a>
        </div>
        <div v-if="network.subnet">
          <span class="text-grey-5">Mask:</span> {{ network.subnet }}
        </div>
        <div v-if="network.vlan != null">
          <span class="text-grey-5">VLAN:</span> {{ network.vlan }}
        </div>
      </div>
      <div
        v-if="network.protocols.length"
        class="q-mt-xs"
      >
        <q-chip
          v-for="p in network.protocols"
          :key="p"
          dense
          size="sm"
          color="primary"
          text-color="white"
          class="text-capitalize"
        >
          {{ p }}
        </q-chip>
      </div>
    </section>

    <!-- Power: how the device draws power (inlet / phase where known). -->
    <section
      v-if="power"
      class="q-mb-sm"
    >
      <div class="text-caption text-grey-5 text-uppercase">
        {{ t('workspace.share.power') }}
      </div>
      <div v-if="power.inletLabel">
        <span class="text-grey-5">Inlet:</span> {{ power.inletLabel }}
      </div>
    </section>

    <!-- DMX: universe / start address / footprint for lighting fixtures. -->
    <section
      v-if="dmx"
      class="q-mb-sm"
    >
      <div class="text-caption text-grey-5 text-uppercase">
        {{ t('workspace.share.dmx') }}
      </div>
      <div class="row q-gutter-x-md">
        <div v-if="dmx.universe != null">
          <span class="text-grey-5">Univ:</span> {{ dmx.universe }}
        </div>
        <div v-if="dmx.start != null">
          <span class="text-grey-5">Start:</span> {{ dmx.start }}
        </div>
        <div v-if="dmx.footprint != null">
          <span class="text-grey-5">Ch:</span> {{ dmx.footprint }}
        </div>
      </div>
    </section>

    <!-- Channels / ports: the day-of-show wiring reference. -->
    <section
      v-if="device.ports && device.ports.length"
      class="q-mb-sm"
    >
      <div class="text-caption text-grey-5 text-uppercase">
        {{ t('workspace.share.channels') }}
      </div>
      <div
        v-for="port in device.ports"
        :key="port.id"
        class="row q-gutter-x-sm text-caption"
      >
        <span class="text-grey-5">{{ port.id }}</span>
        <span v-if="port.connector">{{ port.connector }}</span>
        <span
          v-if="port.signal"
          class="text-capitalize"
        >{{ port.signal }}</span>
        <span v-if="port.channels">· {{ port.channels }}ch</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { powerInletLabel } from '@/utils/workspace';

const { t } = useI18n();
const props = defineProps({
  device: { type: Object, required: true },
});

const attrs = computed(() => props.device.attributes || {});

const network = computed(() => {
  const ip = attrs.value.network_ip;
  const subnet = attrs.value.network_subnet;
  const vlan = attrs.value.network_vlan;
  const protocols = attrs.value.network_protocols || [];
  if (!ip && !subnet && vlan == null && protocols.length === 0) return null;
  return { ip, subnet, vlan, protocols };
});

const power = computed(() => {
  const inlet = attrs.value.power_inlet;
  if (!inlet) return null;
  return { inlet, inletLabel: powerInletLabel(inlet) };
});

const dmx = computed(() => {
  const universe = attrs.value.universe;
  const start = attrs.value.dmx_start;
  const footprint = attrs.value.footprint;
  if (universe == null && start == null && footprint == null) return null;
  return { universe, start, footprint };
});
</script>
