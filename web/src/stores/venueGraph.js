import { defineStore } from 'pinia';
import { api } from '@/boot/api';

// A venue's Standard Base Rig is a graph (devices + edges) owned by the venue rather than a job.
// This store mirrors the shape of the job graph store enough to drive WorkspaceCanvas, but it saves
// the whole rig in one PUT (the backend replaces the rig server-side) instead of issuing per-entity
// PATCH calls. Edits are kept in memory and flagged dirty until the user saves.
const base = (venueId) => `/venues/${venueId}/graph`;

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
    connect(srcId, dstId) {
      if (srcId === dstId) return null;
      const edge = {
        id: newId(),
        signal: 'audio',
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
    removeEdge(id) {
      this.edges = this.edges.filter((e) => e.id !== id);
      this.dirty = true;
    },
    async save() {
      const payload = { devices: this.devices, edges: this.edges };
      const { data } = await api.put(base(this.venueId), payload);
      this.devices = data.devices || [];
      this.edges = data.edges || [];
      this.dirty = false;
      return data;
    },
  },
});
