<template>
  <q-page padding>
    <VenueRigTabs :venue-id="venueId" />
    <LightingPanel :owner="owner" />
  </q-page>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import LightingPanel from '@/components/LightingPanel.vue';
import VenueRigTabs from '@/components/VenueRigTabs.vue';

const route = useRoute();
const venueId = route.params.venueId;
const owner = computed(() => ({ kind: 'venue', id: venueId }));
</script>
