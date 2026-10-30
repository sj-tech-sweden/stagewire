import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { CONNECTOR_CHOICES } from '@/utils/workspace';

// The one list every connector field offers: the built-in presets (utils/workspace.js) followed
// by the kinds people have added (global, stored by the API in `connector_kinds`).
export const useConnectorKindsStore = defineStore('connectorKinds', {
  state: () => ({ custom: [], loaded: false }),
  getters: {
    options: (state) => {
      const known = new Set(CONNECTOR_CHOICES.map((c) => c.value));
      return [
        ...CONNECTOR_CHOICES,
        ...state.custom.filter((k) => !known.has(k.key)).map((k) => ({ value: k.key, label: k.label })),
      ];
    },
  },
  actions: {
    async fetch() {
      if (this.loaded) return;
      try {
        this.custom = (await api.get('/connector-kinds')).data;
      } finally {
        this.loaded = true;
      }
    },
    // Adds a kind (or finds the one with the same key) and returns the key to store on the field.
    async add(label) {
      const { data } = await api.post('/connector-kinds', { label });
      if (!this.custom.some((k) => k.id === data.id)) this.custom.push(data);
      return data.key;
    },
    async remove(id) {
      await api.delete(`/connector-kinds/${id}`);
      this.custom = this.custom.filter((k) => k.id !== id);
    },
  },
});
