<template>
  <q-page padding>
    <VenueRigTabs :venue-id="venueId" />
    <RiggingPanel :owner="owner" />
  </q-page>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import RiggingPanel from '@/components/RiggingPanel.vue';
import VenueRigTabs from '@/components/VenueRigTabs.vue';

const route = useRoute();
const venueId = route.params.venueId;
const owner = computed(() => ({ kind: 'venue', id: venueId }));
</script>
