import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useDevicesStore = defineStore('devices', {
  state: () => ({
    devices: [],
    loading: false,
    error: null,
  }),
  getters: {
    byId: (state) => (id) => state.devices.find((d) => d.id === id) || null,
    options: (state) =>
      state.devices.map((d) => ({ value: d.id, label: d.name || '—' })),
  },
  actions: {
    async fetchDevices(jobId) {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(`/jobs/${jobId}/devices`);
        this.devices = data || [];
      } catch (err) {
        this.error = err.message || 'Failed to load devices';
      } finally {
        this.loading = false;
      }
    },
    async createDevice(jobId, payload) {
      const { data } = await api.post(`/jobs/${jobId}/devices`, payload);
      this.devices.push(data);
      return data;
    },
    async updateDevice(jobId, id, payload) {
      const { data } = await api.patch(`/jobs/${jobId}/devices/${id}`, payload);
      const i = this.devices.findIndex((d) => d.id === id);
      if (i !== -1) this.devices[i] = data;
      return data;
    },
    async deleteDevice(jobId, id) {
      await api.delete(`/jobs/${jobId}/devices/${id}`);
      this.devices = this.devices.filter((d) => d.id !== id);
    },
    async assignPatchPoint(jobId, point, deviceId, direction) {
      const { data } = await api.patch(
        `/jobs/${jobId}/channels/${point.channel_id}/patch-points/${point.id}`,
        { device_id: deviceId || null, direction: direction || null },
      );
      return data;
    },
  },
});
