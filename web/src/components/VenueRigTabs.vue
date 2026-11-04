<template>
  <q-tabs
    class="text-primary q-mb-md"
    align="left"
    dense
    no-caps
    active-color="primary"
  >
    <q-route-tab
      :to="`/venues/${venueId}/base-rig`"
      :label="t('venues.rigTabs.stagePlot')"
      icon="map"
      exact
    />
    <q-route-tab
      :to="`/venues/${venueId}/devices`"
      :label="t('venues.rigTabs.devices')"
      icon="device_hub"
      exact
    />
    <q-route-tab
      :to="`/venues/${venueId}/lighting`"
      :label="t('venues.rigTabs.lighting')"
      icon="light_mode"
      exact
    />
    <q-route-tab
      :to="`/venues/${venueId}/rigging`"
      :label="t('venues.rigTabs.rigging')"
      icon="handyman"
      exact
    />
    <q-route-tab
      :to="`/venues/${venueId}/video`"
      :label="t('venues.rigTabs.video')"
      icon="videocam"
      exact
    />
  </q-tabs>
</template>

<script setup>
import { useI18n } from 'vue-i18n';

const props = defineProps({
  venueId: { type: String, required: true },
});

const { t } = useI18n({ useScope: 'global' });
</script>
