import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { applyGraphEvent, threeWayMerge } from '@/utils/graph';

const base = (jobId) => `/jobs/${jobId}/graph`;

function isRevisionConflict(error) {
  return (
    error.response?.status === 409 && error.response?.data?.detail?.code === 'revision_conflict'
  );
}

export const useGraphStore = defineStore('graph', {
  state: () => ({
    devices: [],
    edges: [],
    selectedDeviceId: null,
    mode: 'canvas',
    conflict: null,
    loading: false,
    error: null,
  }),
  getters: {
    selectedDevice: (state) => state.devices.find((d) => d.id === state.selectedDeviceId) || null,
    unbooked: (state) =>
      state.devices.filter((d) => d.stockwire_product_id && d.stockwire_booked === false),
    unplaced: (state) => state.devices.filter((d) => d.canvas_x_cm == null),
    devicesByDomain: (state) => (domain) => state.devices.filter((d) => d.domain === domain),
  },
  actions: {
    async fetchGraph(jobId) {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(base(jobId));
        this.devices = data.devices;
        this.edges = data.edges;
      } catch (err) {
        this.error = err.message || 'Failed to load graph';
      } finally {
        this.loading = false;
      }
    },
    applyRealtimeEvent(event) {
      if (!event?.type?.startsWith('graph.')) return;
      const next = applyGraphEvent({ devices: this.devices, edges: this.edges }, event);
      this.devices = next.devices;
      this.edges = next.edges;
    },
    async createDevice(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/devices`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createDevices(jobId, payloads) {
      const { data } = await api.post(`${base(jobId)}/devices/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    // Retries once with a field-level merge when the server row moved on; any
    // field both sides changed is surfaced in `conflict` for the user to settle.
    async updateDevice(jobId, id, changes, baseRow) {
      const start = baseRow || this.devices.find((d) => d.id === id);
      return this.versionedPatch(
        `${base(jobId)}/devices/${id}`,
        'device',
        { jobId, id },
        changes,
        start,
        'graph.device.upsert',
      );
    },
    async updateEdge(jobId, id, changes, baseRow) {
      const start = baseRow || this.edges.find((e) => e.id === id);
      return this.versionedPatch(
        `${base(jobId)}/edges/${id}`,
        'edge',
        { jobId, id },
        changes,
        start,
        'graph.edge.upsert',
      );
    },
    async versionedPatch(url, entityType, ids, changes, start, eventType, retried = false) {
      try {
        const { data } = await api.patch(url, {
          ...changes,
          expected_revision: start?.revision,
        });
        this.applyRealtimeEvent({ type: eventType, payload: data });
        this.conflict = null;
        return data;
      } catch (error) {
        if (!isRevisionConflict(error)) throw error;
        const current = error.response.data.detail.current;
        this.applyRealtimeEvent({ type: eventType, payload: current });
        const { merged, conflicts } = threeWayMerge(start, changes, current);
        if (conflicts.length === 0 && !retried) {
          return this.versionedPatch(url, entityType, ids, merged, current, eventType, true);
        }
        this.conflict = { entityType, ids, base: start, draft: changes, current, conflicts };
        throw error;
      }
    },
    // resolution maps each conflicting field to 'mine' or 'theirs'.
    async resolveConflict(resolution) {
      const conflict = this.conflict;
      if (!conflict) return null;
      const changes = {};
      for (const [field, value] of Object.entries(conflict.draft)) {
        const hit = conflict.conflicts.find((c) => c.field === field);
        if (!hit || resolution[field] === 'mine') changes[field] = value;
      }
      this.conflict = null;
      if (Object.keys(changes).length === 0) return conflict.current;
      const { entityType, ids } = conflict;
      return entityType === 'device'
        ? this.updateDevice(ids.jobId, ids.id, changes, conflict.current)
        : this.updateEdge(ids.jobId, ids.id, changes, conflict.current);
    },
    clearConflict() {
      this.conflict = null;
    },
    async deleteDevice(jobId, id) {
      const row = this.devices.find((d) => d.id === id);
      await api.delete(`${base(jobId)}/devices/${id}`, {
        params: { expected_revision: row?.revision },
      });
      this.applyRealtimeEvent({
        type: 'graph.device.delete',
        payload: {
          id,
          edge_ids: this.edges
            .filter((e) => e.src_device_id === id || e.dst_device_id === id)
            .map((e) => e.id),
        },
      });
    },
    async createEdge(jobId, payload, { force = false } = {}) {
      const { data } = await api.post(`${base(jobId)}/edges`, payload, { params: { force } });
      this.applyRealtimeEvent({ type: 'graph.edge.upsert', payload: data });
      return data;
    },
    async deleteEdge(jobId, id) {
      const row = this.edges.find((e) => e.id === id);
      await api.delete(`${base(jobId)}/edges/${id}`, {
        params: { expected_revision: row?.revision },
      });
      this.applyRealtimeEvent({ type: 'graph.edge.delete', payload: { id } });
    },
    async requestStockwireBooking(jobId, id) {
      const { data } = await api.post(`${base(jobId)}/devices/${id}/request-stockwire`);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async trace(jobId, id, direction, signal) {
      const { data } = await api.get(`${base(jobId)}/devices/${id}/trace`, {
        params: { direction, signal },
      });
      return data;
    },
    setMode(mode) {
      this.mode = mode === 'list' ? 'list' : 'canvas';
    },
  },
});
