<template>
  <router-view />
</template>

<script setup>
import { watch } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useStockwireStore } from '@/stores/stockwire';
import { useNetboxStore } from '@/stores/netbox';

// Load the integration flags once the user is authenticated so every component can gate its
// integration-dependent UI on `*.isEnabled`. The watcher fires immediately (covers a fresh load
// where the token is already present) and again after a successful login.
const auth = useAuthStore();
const stockwire = useStockwireStore();
const netbox = useNetboxStore();

watch(
  () => auth.isAuthenticated,
  (authed) => {
    if (authed) {
      stockwire.loadIntegration();
      netbox.loadIntegration();
    }
  },
  { immediate: true },
);
</script>
