import { defineStore } from 'pinia';
import { api } from '@/boot/api';

// A venue's Standard Base Rig is a graph (devices + edges) owned by the venue rather than a job.
// This store mirrors the shape of the job graph store enough to drive WorkspaceCanvas, but it saves
// the whole rig in one PUT (the backend replaces the rig server-side) instead of issuing per-entity
// PATCH calls. Edits are kept in memory and flagged dirty until the user saves.
const base = (venueId) => `/venues/${venueId}/graph`;

// Map a device domain to the signal tab the patch table groups its links under.
const DOMAIN_SIGNAL = {
  audio: 'audio',
  lighting: 'dmx',
  video: 'video',
  power: 'power',
};

const newId = () =>
  (crypto.randomUUID && crypto.randomUUID()) ||
  `dev-${Math.random().toString(16).slice(2)}-${Date.now()}`;

export const useVenueGraphStore = defineStore('venueGraph', {
  state: () => ({
    venueId: null,
    devices: [],
    edges: [],
    selectedId: null,
    dirty: false,
    loading: false,
    error: null,
  }),
  getters: {
    selectedDevice: (state) => state.devices.find((d) => d.id === state.selectedId) || null,
    connectedEdges: (state) => (id) =>
      state.edges.filter((e) => e.src_device_id === id || e.dst_device_id === id),
  },
  actions: {
    async fetchGraph(venueId) {
      if (this.venueId !== venueId) {
        this.devices = [];
        this.edges = [];
        this.selectedId = null;
        this.dirty = false;
      }
      this.venueId = venueId;
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(base(venueId));
        this.devices = data.devices || [];
        this.edges = data.edges || [];
        this.dirty = false;
      } catch (err) {
        this.error = err.message || 'Failed to load base rig';
      } finally {
        this.loading = false;
      }
    },
    addDevice({ domain, kind, name, x = 0, y = 0 }) {
      const device = {
        id: newId(),
        domain,
        kind: kind || '',
        name: name || 'Device',
        notes: '',
        position: this.devices.length,
        attributes: {},
        ports: [],
        canvas_x_cm: x,
        canvas_y_cm: y,
        canvas_rotation: 0,
        stockwire_product_id: null,
        stockwire_product_name: null,
        stockwire_device_id: null,
        stockwire_booked: null,
      };
      this.devices.push(device);
      this.selectedId = device.id;
      this.dirty = true;
      return device;
    },
    moveDevice(id, x, y) {
      const device = this.devices.find((d) => d.id === id);
      if (!device) return;
      device.canvas_x_cm = x;
      device.canvas_y_cm = y;
      this.dirty = true;
    },
    updateDevice(id, changes) {
      const device = this.devices.find((d) => d.id === id);
      if (!device) return;
      Object.assign(device, changes);
      this.dirty = true;
    },
    removeDevice(id) {
      this.devices = this.devices.filter((d) => d.id !== id);
      this.edges = this.edges.filter(
        (e) => e.src_device_id !== id && e.dst_device_id !== id,
      );
      if (this.selectedId === id) this.selectedId = null;
      this.dirty = true;
    },
    // A link drawn on the canvas between two devices: an edge with no chosen ports yet.
    // The signal is derived from the source device's domain so the patch table groups it
    // under the right tab (audio / dmx / video / power), rather than always "audio".
    connect(srcId, dstId) {
      if (srcId === dstId) return null;
      const src = this.devices.find((d) => d.id === srcId);
      const signal = DOMAIN_SIGNAL[src?.domain] || 'audio';
      const edge = {
        id: newId(),
        signal,
        src_device_id: srcId,
        src_port: '',
        dst_device_id: dstId,
        dst_port: '',
        channels: 1,
        phase: null,
        cable_label: '',
        notes: '',
        attributes: {},
      };
      this.edges.push(edge);
      this.dirty = true;
      return edge;
    },
    updateEdge(id, changes) {
      const edge = this.edges.find((e) => e.id === id);
      if (!edge) return;
      Object.assign(edge, changes);
      this.dirty = true;
    },
    removeEdge(id) {
      this.edges = this.edges.filter((e) => e.id !== id);
      this.dirty = true;
    },
    async save() {
      // The Channel List editor commits its changes straight to the DB through the incremental
      // graph routes (it uses the `graph` store, not this whole-graph store). A whole-graph
      // replace would otherwise delete those lists, so re-fetch the server rig first and carry
      // forward any list/channel/output devices this store doesn't already hold locally.
      const { data: server } = await api.get(base(this.venueId));
      const localIds = new Set(this.devices.map((d) => d.id));
      const listKinds = new Set([
        'channel_list',
        'channel',
        'output',
        'video_list',
        'video_input',
        'video_output',
      ]);
      const preserved = (server.devices || []).filter(
        (d) => !localIds.has(d.id) && listKinds.has(d.kind),
      );
      const preservedIds = new Set(preserved.map((d) => d.id));
      const preservedEdges = (server.edges || []).filter(
        (e) =>
          !this.edges.some((le) => le.id === e.id) &&
          preserved.some((p) => p.id === e.src_device_id || p.id === e.dst_device_id),
      );
      const payload = {
        devices: [...this.devices, ...preserved],
        edges: [...this.edges, ...preservedEdges],
      };
      const { data } = await api.put(base(this.venueId), payload);
      this.devices = data.devices || [];
      this.edges = data.edges || [];
      this.dirty = false;
      return data;
    },
  },
});
