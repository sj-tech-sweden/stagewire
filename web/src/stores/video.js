import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useVideoStore = defineStore('video', {
  state: () => ({
    lists: [],
    loading: false,
    error: null,
  }),
  getters: {
    allInputs: (state) => state.lists.flatMap((l) => l.inputs || []),
  },
  actions: {
    async fetchLists(jobId) {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(`/jobs/${jobId}/video-lists`);
        this.lists = data || [];
      } catch (err) {
        this.error = err.message || 'Failed to load video inputs';
      } finally {
        this.loading = false;
      }
    },
    async createList(jobId, name) {
      const { data } = await api.post(`/jobs/${jobId}/video-lists`, { name });
      this.lists.push({ ...data, inputs: data.inputs || [] });
      return data;
    },
    async updateList(jobId, listId, payload) {
      const { data } = await api.patch(`/jobs/${jobId}/video-lists/${listId}`, payload);
      this.patchList(listId, {
        name: data.name,
        switcher_product_id: data.switcher_product_id,
        switcher_product_name: data.switcher_product_name,
        switcher_inputs: data.switcher_inputs,
        switcher_outputs: data.switcher_outputs,
      });
      return data;
    },
    async bulkCreateInputs(jobId, listId, payload) {
      const { data } = await api.post(`/jobs/${jobId}/video-lists/${listId}/inputs/bulk`, payload);
      const list = this.lists.find((l) => l.id === listId);
      if (list) list.inputs = [...(list.inputs || []), ...data];
      return data;
    },
    async bulkCreateOutputs(jobId, listId, payload) {
      const { data } = await api.post(`/jobs/${jobId}/video-lists/${listId}/outputs/bulk`, payload);
      const list = this.lists.find((l) => l.id === listId);
      if (list) list.outputs = [...(list.outputs || []), ...data];
      return data;
    },
    async updateOutput(jobId, outputId, payload) {
      const { data } = await api.patch(`/jobs/${jobId}/video-outputs/${outputId}`, payload);
      this.patchOutput(outputId, (out) => ({ ...out, ...data, patch_points: out.patch_points }));
      return data;
    },
    async deleteOutput(jobId, outputId) {
      await api.delete(`/jobs/${jobId}/video-outputs/${outputId}`);
      for (const list of this.lists) {
        list.outputs = (list.outputs || []).filter((o) => o.id !== outputId);
      }
    },
    async createOutputPatchPoint(jobId, outputId, payload) {
      const { data } = await api.post(`/jobs/${jobId}/video-outputs/${outputId}/patch-points`, payload);
      this.patchOutput(outputId, (out) => ({
        ...out,
        patch_points: [...(out.patch_points || []), data],
      }));
      return data;
    },
    async updateOutputPatchPoint(jobId, outputId, pointId, payload) {
      const { data } = await api.patch(
        `/jobs/${jobId}/video-outputs/${outputId}/patch-points/${pointId}`,
        payload,
      );
      this.patchOutput(outputId, (out) => ({
        ...out,
        patch_points: (out.patch_points || []).map((p) => (p.id === pointId ? data : p)),
      }));
      return data;
    },
    async deleteOutputPatchPoint(jobId, outputId, pointId) {
      await api.delete(`/jobs/${jobId}/video-outputs/${outputId}/patch-points/${pointId}`);
      this.patchOutput(outputId, (out) => ({
        ...out,
        patch_points: (out.patch_points || []).filter((p) => p.id !== pointId),
      }));
    },
    patchOutput(outputId, update) {
      for (const list of this.lists) {
        const i = (list.outputs || []).findIndex((x) => x.id === outputId);
        if (i !== -1) {
          list.outputs[i] = update(list.outputs[i]);
          return;
        }
      }
    },
    async deleteList(jobId, listId) {
      await api.delete(`/jobs/${jobId}/video-lists/${listId}`);
      this.lists = this.lists.filter((l) => l.id !== listId);
    },
    async createInput(jobId, listId, payload = {}) {
      const { data } = await api.post(`/jobs/${jobId}/video-lists/${listId}/inputs`, payload);
      const list = this.lists.find((l) => l.id === listId);
      if (list) list.inputs = [...(list.inputs || []), { ...data, patch_points: [] }];
      return data;
    },
    async updateInput(jobId, inputId, payload) {
      const { data } = await api.patch(`/jobs/${jobId}/video-inputs/${inputId}`, payload);
      this.patchInput(inputId, (input) => ({ ...input, ...data, patch_points: input.patch_points }));
      return data;
    },
    async deleteInput(jobId, inputId) {
      await api.delete(`/jobs/${jobId}/video-inputs/${inputId}`);
      for (const list of this.lists) {
        list.inputs = (list.inputs || []).filter((i) => i.id !== inputId);
      }
    },
    async createPatchPoint(jobId, inputId, payload) {
      const { data } = await api.post(`/jobs/${jobId}/video-inputs/${inputId}/patch-points`, payload);
      this.patchInput(inputId, (input) => ({
        ...input,
        patch_points: [...(input.patch_points || []), data],
      }));
      return data;
    },
    async updatePatchPoint(jobId, inputId, pointId, payload) {
      const { data } = await api.patch(
        `/jobs/${jobId}/video-inputs/${inputId}/patch-points/${pointId}`,
        payload,
      );
      this.patchInput(inputId, (input) => ({
        ...input,
        patch_points: (input.patch_points || []).map((p) => (p.id === pointId ? data : p)),
      }));
      return data;
    },
    async deletePatchPoint(jobId, inputId, pointId) {
      await api.delete(`/jobs/${jobId}/video-inputs/${inputId}/patch-points/${pointId}`);
      this.patchInput(inputId, (input) => ({
        ...input,
        patch_points: (input.patch_points || []).filter((p) => p.id !== pointId),
      }));
    },
    patchList(listId, changes) {
      const list = this.lists.find((l) => l.id === listId);
      if (list) Object.assign(list, changes);
    },
    patchInput(inputId, update) {
      for (const list of this.lists) {
        const i = (list.inputs || []).findIndex((x) => x.id === inputId);
        if (i !== -1) {
          list.inputs[i] = update(list.inputs[i]);
          return;
        }
      }
    },
  },
});
