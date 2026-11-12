import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { applyGraphEvent, isRevisionConflict, threeWayMerge } from '@/utils/graph';
import {
  deviceCreateBody,
  deviceForm,
  deviceTypeFromCategory,
  fillFormFromSpecs,
  isVirtual,
  POWERED_AUDIO_TYPES,
  signalForType,
} from '@/utils/workspace';

const base = (jobId) => `/jobs/${jobId}/graph`;

// The same graph store backs both jobs and venues (venues-as-template-jobs). When the scope is a
// venue we point at the venue graph routes instead of the job ones; callers keep passing the id,
// but the URL is derived from the active scope so a job never leaks into a venue request.
function baseFor(store, id) {
  return store.scopeKind === 'venue' ? store.graphBase : base(id);
}

export const useGraphStore = defineStore('graph', {
  state: () => ({
    jobId: null,
    // Active scope for the incremental graph routes: a job or a venue. A venue rig reuses the
    // job graph editing UX, so the same store serves both; `scopeKind`/`scopeId` pick the prefix.
    scopeKind: 'job',
    scopeId: null,
    devices: [],
    edges: [],
    selectedDeviceId: null,
    mode: 'canvas',
    conflict: null,
    netboxAlert: null,
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
    graphBase: (state) =>
      state.scopeKind === 'venue'
        ? `/venues/${state.scopeId}/graph`
        : `/jobs/${state.scopeId}/graph`,
    channelLists: (state) =>
      state.devices.filter((d) => d.kind === 'channel_list').sort((a, b) => a.position - b.position),
    videoLists: (state) =>
      state.devices.filter((d) => d.kind === 'video_list').sort((a, b) => a.position - b.position),
    unplaced: (state) => state.devices.filter((d) => d.canvas_x_cm == null && !isVirtual(d)),
    devicesByDomain: (state) => (domain) => state.devices.filter((d) => d.domain === domain),
  },
  actions: {
    setScope(kind, id) {
      this.scopeKind = kind;
      this.scopeId = id;
    },
    async fetchGraph(id, kind = 'job') {
      if (this.scopeId !== id || this.scopeKind !== kind) {
        this.devices = [];
        this.edges = [];
        this.issues = [];
        this.effective = {};
      }
      this.setScope(kind, id);
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(this.graphBase);
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
      // A NetBox sync event that flags a conflict (e.g. the IP was deleted or
      // reassigned away from this device) raises a transient alert the UI shows
      // as a warning banner on the affected device.
      if (event.type === 'graph.device.netbox' && event.payload?.status === 'conflict') {
        this.netboxAlert = {
          deviceId: event.payload.device_id,
          jobId: event.payload.job_id,
          message: event.payload.message || 'NetBox IP conflict',
        };
      }
      const next = applyGraphEvent({ devices: this.devices, edges: this.edges }, event);
      this.devices = next.devices;
      this.edges = next.edges;
    },
    async createDevice(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/devices`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createDevices(jobId, payloads) {
      const { data } = await api.post(`${baseFor(this, jobId)}/devices/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    // Retries once with a field-level merge when the server row moved on; any
    // field both sides changed is surfaced in `conflict` for the user to settle.
    async updateDevice(jobId, id, changes, baseRow) {
      const start = baseRow || this.devices.find((d) => d.id === id);
      return this.versionedPatch(
        `${baseFor(this, jobId)}/devices/${id}`,
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
        `${baseFor(this, jobId)}/edges/${id}`,
        'edge',
        { jobId, id },
        changes,
        start,
        'graph.edge.upsert',
      );
    },
    async versionedPatch(url, entityType, ids, changes, start, eventType, attempt = 0) {
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
        // An empty conflict list means the user's edit did not actually collide with the
        // server's row — it was only an optimistic-concurrency race (typically two rapid
        // field edits on the same device firing before the first response lands). Never open
        // the conflict dialog for that; retry against the latest row instead, bounded so a
        // pathological storm of concurrent editors cannot loop forever.
        if (conflicts.length === 0) {
          if (attempt >= 5) return current;
          return this.versionedPatch(url, entityType, ids, merged, current, eventType, attempt + 1);
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
      await api.delete(`${baseFor(this, jobId)}/devices/${id}`, {
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
      const { data } = await api.post(`${baseFor(this, jobId)}/edges`, payload, { params: { force } });
      this.applyRealtimeEvent({ type: 'graph.edge.upsert', payload: data });
      return data;
    },
    async deleteEdge(jobId, id) {
      const row = this.edges.find((e) => e.id === id);
      await api.delete(`${baseFor(this, jobId)}/edges/${id}`, {
        params: { expected_revision: row?.revision },
      });
      this.applyRealtimeEvent({ type: 'graph.edge.delete', payload: { id } });
    },
    async requestStockwireBooking(jobId, id) {
      const { data } = await api.post(`${baseFor(this, jobId)}/devices/${id}/request-stockwire`);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    // Binds a physical Stockwire inventory asset to this device. The server records the code
    // locally (so the link survives offline) and, when the integration is enabled, resolves
    // tag/serial/description. The returned device is applied as a realtime upsert event.
    async bindStockwireAsset(jobId, id, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/devices/${id}/bind-asset`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async unbindStockwireAsset(jobId, id) {
      const device = this.devices.find((item) => item.id === id);
      const { data } = await api.delete(`${baseFor(this, jobId)}/devices/${id}/asset-binding`, {
        params: { expected_revision: device?.revision },
      });
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async trace(jobId, id, direction, signal) {
      const { data } = await api.get(`${baseFor(this, jobId)}/devices/${id}/trace`, {
        params: { direction, signal },
      });
      return data;
    },
    async refreshChecks(jobId) {
      const [issues, loads] = await Promise.all([
        api.get(`${baseFor(this, jobId)}/validate`),
        api.get(`${baseFor(this, jobId)}/power-load`),
      ]);
      this.issues = issues.data;
      this.loads = loads.data;
    },
    async backfill(jobId) {
      const { data } = await api.post(`${baseFor(this, jobId)}/backfill`);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    async createList(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/lists`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createChannels(jobId, listId, payloads) {
      const { data } = await api.post(`${baseFor(this, jobId)}/lists/${listId}/channels/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    async createOutputs(jobId, listId, payloads) {
      const { data } = await api.post(`${baseFor(this, jobId)}/lists/${listId}/outputs/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    async createOutput(jobId, listId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/lists/${listId}/outputs`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    // The same chain on many channels at once (bulk add patched into one device): the chains are
    // written one by one, then the graph is fetched once instead of after every chain.
    async setChannelChains(jobId, channelIds, steps) {
      for (const id of channelIds) {
        await api.put(`${baseFor(this, jobId)}/channels/${id}/chain`, { steps });
      }
      await this.fetchGraph(this.scopeId, this.scopeKind);
    },
    async replaceChain(jobId, kind, nodeId, steps) {
      const route =
        {
          output: 'outputs',
          universe: 'universes',
          video_input: 'video-inputs',
          video_output: 'video-outputs',
        }[kind] || 'channels';
      const url = `${baseFor(this, jobId)}/${route}/${nodeId}/chain`;
      const { data } = await api.put(url, { steps });
      // the server synced; refetch so devices created for the chain and edge changes all arrive
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    async createVideoList(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/video-lists`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    // kind is 'inputs' or 'outputs'
    async createVideoRows(jobId, listId, kind, payloads) {
      const { data } = await api.post(`${baseFor(this, jobId)}/video-lists/${listId}/${kind}/batch`, payloads);
      data.forEach((payload) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload }));
      return data;
    },
    async fillVideoFromSwitcher(jobId, listId) {
      const { data } = await api.post(`${baseFor(this, jobId)}/video-lists/${listId}/fill-from-switcher`);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    async fetchRiggingSummary(jobId) {
      const { data } = await api.get(`${baseFor(this, jobId)}/rigging/summary`);
      return data;
    },
    async createRiggingPoint(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/rigging-points`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createPowerNode(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/power-nodes`, payload);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    // The source node for a venue outlet (its power group, or the outlet alone), made on first use.
    async outletSource(jobId, outletId) {
      const { data } = await api.post(`${baseFor(this, jobId)}/venue-power/outlets/${outletId}/source`);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    async movePowerNode(jobId, nodeId, payload) {
      await api.put(`${baseFor(this, jobId)}/power-nodes/${nodeId}/parent`, payload);
      await this.fetchGraph(this.scopeId, this.scopeKind);
    },
    async insertExtension(jobId, nodeId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/power-nodes/${nodeId}/extension`, payload);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    async addPowerFeed(jobId, nodeId, payload) {
      await api.post(`${baseFor(this, jobId)}/power-nodes/${nodeId}/feeds`, payload);
      await this.fetchGraph(this.scopeId, this.scopeKind);
    },
    async assignLoad(jobId, nodeId, payload) {
      const { data } = await api.put(`${baseFor(this, jobId)}/loads/${nodeId}`, payload);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    // A device made from a Stockwire product: its connectors, power inlet, weight and power come
    // from /stockwire/products/{id}/device-specs (a product without specs still makes a device).
    async createDeviceFromProduct(jobId, product) {
      let specs = {};
      if (product.id) {
        try {
          specs = (await api.get(`/stockwire/products/${product.id}/device-specs`)).data;
        } catch {
          specs = {};
        }
      }
      const form = deviceForm(null);
      form.device_type = deviceTypeFromCategory(product.category);
      fillFormFromSpecs(form, product, specs);
      // Passive source gear (microphones, mic stands, DIs, instruments) takes no power by default.
      // An explicit product spec (e.g. a powered speaker) still wins over this default.
      if (
        !form.power_inlet &&
        signalForType(form.device_type) === 'audio' &&
        !POWERED_AUDIO_TYPES.has(form.device_type)
      ) {
        form.power_inlet = 'none';
      }
      form.name = form.name || product.name;
      return this.createAudioDevice(jobId, deviceCreateBody(form));
    },
    async createAudioDevice(jobId, body) {
      const { data } = await api.post(`${baseFor(this, jobId)}/audio-devices`, body);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createFixture(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/fixtures`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async createFixturesBulk(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/fixtures/bulk`, payload);
      data.forEach((node) => this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: node }));
      return data;
    },
    async createUniverse(jobId, payload) {
      const { data } = await api.post(`${baseFor(this, jobId)}/universes`, payload);
      this.applyRealtimeEvent({ type: 'graph.device.upsert', payload: data });
      return data;
    },
    async setUniverseSource(jobId, universeId, deviceId, port) {
      await api.put(`${baseFor(this, jobId)}/universes/${universeId}/source`, { device_id: deviceId, port });
      await this.fetchGraph(this.scopeId, this.scopeKind);
    },
    async importFixtures(jobId, file) {
      const form = new FormData();
      form.append('file', file);
      const { data } = await api.post(`/jobs/${jobId}/fixtures/import`, form);
      await this.fetchGraph(this.scopeId, this.scopeKind);
      return data;
    },
    async fetchEffective(jobId) {
      const { data } = await api.get(`${baseFor(this, jobId)}/effective`);
      this.effective = data;
    },
    async exportPlugins(jobId) {
      const { data } = await api.get(`${baseFor(this, jobId)}/export-plugins`);
      return data;
    },
    async exportList(jobId, listId, plugin) {
      const response = await api.get(`${baseFor(this, jobId)}/lists/${listId}/export`, {
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
