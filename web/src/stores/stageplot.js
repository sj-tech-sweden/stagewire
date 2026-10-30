import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { useGraphStore } from '@/stores/graph';
import {
  elementFromNode,
  elementLinks,
  elementsFromGraph,
  splitElementChanges,
} from '@/utils/graphLegacy';

// The plot's elements are the graph's plot_element nodes, shown in the shape the plot was
// written for (legacy element id, position_x, linked_*_id).
export const useStagePlotStore = defineStore('stageplot', {
  state: () => ({
    loading: false,
    error: null,
  }),
  getters: {
    elements() {
      const graph = useGraphStore();
      return elementsFromGraph(graph.devices, graph.edges);
    },
  },
  actions: {
    nodeOf(id) {
      const graph = useGraphStore();
      return graph.devices.find((d) => d.legacy_ref === `stage_plot_elements:${id}`) || null;
    },
    elementOf(jobId, node) {
      const graph = useGraphStore();
      const fresh = graph.devices.find((d) => d.id === node.id) || node;
      const links = elementLinks(graph.edges).get(node.id) || {};
      return elementFromNode(fresh, links, new Map(graph.devices.map((d) => [d.id, d])));
    },
    async fetchElements(jobId) {
      const graph = useGraphStore();
      this.loading = true;
      this.error = null;
      try {
        await graph.backfill(jobId);
      } catch (err) {
        this.error = err.message || 'Failed to load stage plot';
      } finally {
        this.loading = false;
      }
    },
    async createElement(jobId, payload) {
      const graph = useGraphStore();
      const { node, links } = splitElementChanges(payload);
      const created = await graph.createDevice(jobId, {
        domain: 'other',
        kind: 'plot_element',
        name: payload.label || payload.element_type || 'element',
        attributes: { label: payload.label || '', ...node.attributes },
        canvas_x_cm: node.canvas_x_cm ?? 0,
        canvas_y_cm: node.canvas_y_cm ?? 0,
        canvas_rotation: node.canvas_rotation ?? 0,
      });
      const set = Object.fromEntries(Object.entries(links).filter(([, value]) => value));
      if (Object.keys(set).length) await this.putLinks(jobId, created.id, set);
      return this.elementOf(jobId, created);
    },
    async putLinks(jobId, nodeId, links) {
      const graph = useGraphStore();
      await api.put(`/jobs/${jobId}/graph/plot-elements/${nodeId}/links`, links);
      await graph.fetchGraph(jobId);
    },
    async updateElement(jobId, id, payload) {
      const graph = useGraphStore();
      const node = this.nodeOf(id);
      if (!node) throw new Error('Plot element not found');
      const { node: changes, links } = splitElementChanges(payload);
      if (Object.keys(changes).length) await graph.updateDevice(jobId, node.id, changes);
      if (Object.keys(links).length) await this.putLinks(jobId, node.id, links);
      return this.elementOf(jobId, node);
    },
    async deleteElement(jobId, id) {
      const graph = useGraphStore();
      const node = this.nodeOf(id);
      if (node) await graph.deleteDevice(jobId, node.id);
    },
  },
});
