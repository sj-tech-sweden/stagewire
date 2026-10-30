import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { applyGraphEvent, isRevisionConflict, threeWayMerge } from '@/utils/graph';
import { isVirtual } from '@/utils/workspace';

const base = (jobId) => `/jobs/${jobId}/graph`;

export const useGraphStore = defineStore('graph', {
  state: () => ({
    jobId: null,
    devices: [],
    edges: [],
    selectedDeviceId: null,
    mode: 'canvas',
    conflict: null,
    issues: [],
    effective: {},
    loads: { L1: 0, L2: 0, L3: 0, imbalance_pct: 0 },
    loading: false,
    error: null,
  }),
  getters: {
    selectedDevice: (state) => state.devices.find((d) => d.id === state.selectedDeviceId) || null,
    unbooked: (state) =>
      state.devices.filter((d) => d.stockwire_product_id && d.stockwire_booked === false),
    channelLists: (state) =>
      state.devices.filter((d) => d.kind === 'channel_list').sort((a, b) => a.position - b.position),
    videoLists: (state) =>
      state.devices.filter((d) => d.kind === 'video_list').sort((a, b) => a.position - b.position),
    unplaced: (state) => state.devices.filter((d) => d.canvas_x_cm == null && !isVirtual(d)),
    devicesByDomain: (state) => (domain) => state.devices.filter((d) => d.domain === domain),
  },
  actions: {
    async fetchGraph(jobId) {
      if (this.jobId !== jobId) {
        this.devices = [];
        this.edges = [];
        this.issues = [];
        this.effective = {};
      }
      this.jobId = jobId;
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
    async refreshChecks(jobId) {
      const [issues, loads] = await Promise.all([
        api.get(`${base(jobId)}/validate`),
        api.get(`${base(jobId)}/power-load`),
      ]);
      this.issues = issues.data;
      this.loads = loads.data;
    },
    async backfill(jobId) {
      const { data } = await api.post(`${base(jobId)}/backfill`);
      await this.fetchGraph(jobId);
      return data;
    },
    async createList(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/lists`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createChannels(jobId, listId, payloads) {
      const { data } = await api.post(`${base(jobId)}/lists/${listId}/channels/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    async createOutputs(jobId, listId, payloads) {
      const { data } = await api.post(`${base(jobId)}/lists/${listId}/outputs/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    async createOutput(jobId, listId, payload) {
      const { data } = await api.post(`${base(jobId)}/lists/${listId}/outputs`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async replaceChain(jobId, kind, nodeId, steps) {
      const route =
        {
          output: 'outputs',
          universe: 'universes',
          video_input: 'video-inputs',
          video_output: 'video-outputs',
        }[kind] || 'channels';
      const url = `${base(jobId)}/${route}/${nodeId}/chain`;
      const { data } = await api.put(url, { steps });
      // the server synced; refetch so devices created for the chain and edge changes all arrive
      await this.fetchGraph(jobId);
      return data;
    },
    async createVideoList(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/video-lists`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    // kind is 'inputs' or 'outputs'
    async createVideoRows(jobId, listId, kind, payloads) {
      const { data } = await api.post(`${base(jobId)}/video-lists/${listId}/${kind}/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    async fillVideoFromSwitcher(jobId, listId) {
      const { data } = await api.post(`${base(jobId)}/video-lists/${listId}/fill-from-switcher`);
      await this.fetchGraph(jobId);
      return data;
    },
    async fetchRiggingSummary(jobId) {
      const { data } = await api.get(`${base(jobId)}/rigging/summary`);
      return data;
    },
    async createRiggingPoint(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/rigging-points`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createPowerNode(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/power-nodes`, payload);
      await this.fetchGraph(jobId);
      return data;
    },
    // The source node for a venue outlet (its power group, or the outlet alone), made on first use.
    async outletSource(jobId, outletId) {
      const { data } = await api.post(`${base(jobId)}/venue-power/outlets/${outletId}/source`);
      await this.fetchGraph(jobId);
      return data;
    },
    async movePowerNode(jobId, nodeId, payload) {
      await api.put(`${base(jobId)}/power-nodes/${nodeId}/parent`, payload);
      await this.fetchGraph(jobId);
    },
    async insertExtension(jobId, nodeId, payload) {
      const { data } = await api.post(`${base(jobId)}/power-nodes/${nodeId}/extension`, payload);
      await this.fetchGraph(jobId);
      return data;
    },
    async addPowerFeed(jobId, nodeId, payload) {
      await api.post(`${base(jobId)}/power-nodes/${nodeId}/feeds`, payload);
      await this.fetchGraph(jobId);
    },
    async assignLoad(jobId, nodeId, payload) {
      const { data } = await api.put(`${base(jobId)}/loads/${nodeId}`, payload);
      await this.fetchGraph(jobId);
      return data;
    },
    async createAudioDevice(jobId, body) {
      const { data } = await api.post(`${base(jobId)}/audio-devices`, body);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createFixture(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/fixtures`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createFixturesBulk(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/fixtures/bulk`, payload);
      data.forEach((node) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: node }));
      return data;
    },
    async createUniverse(jobId, payload) {
      const { data } = await api.post(`${base(jobId)}/universes`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async setUniverseSource(jobId, universeId, deviceId, port) {
      await api.put(`${base(jobId)}/universes/${universeId}/source`, { device_id: deviceId, port });
      await this.fetchGraph(jobId);
    },
    async importFixtures(jobId, file) {
      const form = new FormData();
      form.append('file', file);
      const { data } = await api.post(`/jobs/${jobId}/fixtures/import`, form);
      await this.fetchGraph(jobId);
      return data;
    },
    async fetchEffective(jobId) {
      const { data } = await api.get(`${base(jobId)}/effective`);
      this.effective = data;
    },
    async exportPlugins(jobId) {
      const { data } = await api.get(`${base(jobId)}/export-plugins`);
      return data;
    },
    async exportList(jobId, listId, plugin) {
      const response = await api.get(`${base(jobId)}/lists/${listId}/export`, {
        params: { plugin },
        responseType: 'blob',
      });
      const match = /filename="([^"]+)"/.exec(response.headers['content-disposition'] || '');
      return { blob: response.data, filename: match ? match[1] : `${plugin}.bin` };
    },
    setMode(mode) {
      this.mode = ['list', 'lists', 'devices', 'lights', 'video', 'power'].includes(mode) ? mode : 'canvas';
    },
  },
});
