import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useVenuesStore = defineStore('venues', {
  state: () => ({
    venues: [],
    loading: false,
    error: null,
  }),
  actions: {
    async fetchVenues() {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get('/venues');
        this.venues = data;
      } catch (err) {
        this.error = err.message || 'Failed to load venues';
      } finally {
        this.loading = false;
      }
    },
    async createVenue(payload) {
      const { data } = await api.post('/venues', payload);
      this.venues.push(data);
      this.venues.sort((a, b) => a.name.localeCompare(b.name));
      return data;
    },
    async updateVenue(id, payload) {
      const { data } = await api.patch(`/venues/${id}`, payload);
      const i = this.venues.findIndex((v) => v.id === id);
      if (i !== -1) this.venues[i] = data;
      return data;
    },
    async deleteVenue(id) {
      await api.delete(`/venues/${id}`);
      this.venues = this.venues.filter((v) => v.id !== id);
    },
    async propagateVenue(id, scope) {
      const { data } = await api.post(`/venues/${id}/propagate`, { scope });
      await this.fetchVenues();
      return data;
    },
    async assignJobVenue(jobId, venueId) {
      const { data } = await api.put(`/jobs/${jobId}/venue`, { venue_id: venueId || null });
      return data;
    },
  },
});
