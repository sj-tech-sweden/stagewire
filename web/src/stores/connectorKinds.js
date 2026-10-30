import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { CONNECTOR_CHOICES } from '@/utils/workspace';

// The one list every connector field offers: the built-in presets (utils/workspace.js) followed
// by the kinds people have added (global, stored by the API in `connector_kinds`).
export const useConnectorKindsStore = defineStore('connectorKinds', {
  state: () => ({ custom: [], loaded: false, power: [] }),
  getters: {
    // Power connectors with what the power tree needs (amps, phases): the built-in catalog plus
    // the power kinds people added.
    powerOptions: (state) => state.power.map((c) => ({ value: c.key, label: c.label, custom: c.custom })),
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
      // only a successful load counts, so a failed one is tried again by the next field
      this.custom = (await api.get('/connector-kinds')).data;
      this.loaded = true;
    },
    async fetchPower() {
      this.power = (await api.get('/power-connectors')).data;
    },
    // A new power connector needs its rating: amps per phase (0 = fixed installation, rated by
    // hand) and 1 or 3 phases. It joins both the power catalog and the shared connector list.
    async addPower({ label, amps, phases }) {
      const { data } = await api.post('/connector-kinds', { label, power: true, amps, phases });
      if (!this.custom.some((k) => k.id === data.id)) this.custom.push(data);
      await this.fetchPower();
      return data.key;
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
