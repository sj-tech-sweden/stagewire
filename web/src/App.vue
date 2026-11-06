<template>
  <router-view />
</template>

<script setup>
import { watch } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useStockwireStore } from '@/stores/stockwire';

// Load the stockwire integration flag once the user is authenticated so every component can gate
// its stockwire-dependent UI on `stockwire.isEnabled`. The watcher fires immediately (covers a fresh
// load where the token is already present) and again after a successful login.
const auth = useAuthStore();
const stockwire = useStockwireStore();

watch(
  () => auth.isAuthenticated,
  (authed) => {
    if (authed) stockwire.loadIntegration();
  },
  { immediate: true },
);
</script>
