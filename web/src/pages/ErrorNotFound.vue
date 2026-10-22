<template>
  <q-page class="q-pa-md flex flex-center">
    <div class="text-center">
      <div class="text-h4 text-grey">
        404
      </div>
      <div class="text-subtitle1 text-grey">
        Page not found
      </div>
      <q-btn
        color="primary"
        label="Go home"
        to="/"
        class="q-mt-md"
      />
    </div>
  </q-page>
</template>

<script>
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'ErrorNotFound',
});
</script>
