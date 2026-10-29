import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useChannelsStore = defineStore('channels', {
  state: () => ({
    lists: [],
    channels: [],
    selectedListId: null,
    loading: false,
    error: null,
    conflict: null,
  }),
  getters: {
    selectedList: (state) => state.lists.find((l) => l.id === state.selectedListId) || null,
  },
  actions: {
    async fetchLists(jobId) {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(`/jobs/${jobId}/channel-lists`);
        this.lists = data;
        this.selectedListId = data.length ? data[0].id : null;
        this.channels = [];
        if (this.selectedListId) {
          await this.fetchChannels(jobId, this.selectedListId);
        }
      } catch (err) {
        this.error = err.message || 'Failed to load channel lists';
      } finally {
        this.loading = false;
      }
    },
    async fetchChannels(jobId, listId) {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(`/jobs/${jobId}/channel-lists/${listId}/channels`);
        this.channels = data;
      } catch (err) {
        this.error = err.message || 'Failed to load channels';
      } finally {
        this.loading = false;
      }
    },
    async selectList(jobId, listId) {
      this.selectedListId = listId;
      await this.fetchChannels(jobId, listId);
    },
    async createList(jobId, name, mixer = {}) {
      const { data } = await api.post(`/jobs/${jobId}/channel-lists`, {
        name,
        position: this.lists.length,
        mixer_product_id: mixer.mixer_product_id || null,
        mixer_product_name: mixer.mixer_product_name || null,
        mixer_inputs: mixer.mixer_inputs ?? null,
        mixer_buses: mixer.mixer_buses ?? null,
      });
      this.upsertList(data);
      this.selectedListId = data.id;
      this.channels = [];
      return data;
    },
    async renameList(jobId, listId, name, mixer = {}) {
      const { data } = await api.patch(`/jobs/${jobId}/channel-lists/${listId}`, {
        name,
        mixer_product_id: mixer.mixer_product_id ?? null,
        mixer_product_name: mixer.mixer_product_name ?? null,
        mixer_inputs: mixer.mixer_inputs ?? null,
        mixer_buses: mixer.mixer_buses ?? null,
      });
      const list = this.lists.find((l) => l.id === listId);
      if (list) {
        list.name = data.name;
        list.mixer_product_id = data.mixer_product_id;
        list.mixer_product_name = data.mixer_product_name;
        list.mixer_inputs = data.mixer_inputs;
        list.mixer_buses = data.mixer_buses;
      }
      return data;
    },
    async deleteList(jobId, listId) {
      await api.delete(`/jobs/${jobId}/channel-lists/${listId}`);
      this.lists = this.lists.filter((l) => l.id !== listId);
      if (this.selectedListId === listId) {
        this.selectedListId = this.lists.length ? this.lists[0].id : null;
        this.channels = [];
        if (this.selectedListId) {
          await this.fetchChannels(jobId, this.selectedListId);
        }
      }
    },
    async createChannel(jobId, listId, payload) {
      const { data } = await api.post(
        `/jobs/${jobId}/channel-lists/${listId}/channels`,
        payload,
      );
      this.upsertChannel(data);
      return data;
    },
    async updateChannel(jobId, id, payload) {
      const current = this.channels.find((channel) => channel.id === id);
      try {
        const { data } = await api.patch(`/jobs/${jobId}/channels/${id}`, {
          ...payload,
          expected_revision: current?.revision,
        });
        this.upsertChannel(data);
        this.conflict = null;
        return data;
      } catch (error) {
        this.recordConflict(error, 'channel', { jobId, id }, payload);
        throw error;
      }
    },
    async deleteChannel(jobId, id) {
      const current = this.channels.find((channel) => channel.id === id);
      try {
        await api.delete(`/jobs/${jobId}/channels/${id}`, {
          params: { expected_revision: current?.revision },
        });
      } catch (error) {
        this.recordConflict(error, 'channel-delete', { jobId, id }, null);
        throw error;
      }
      this.channels = this.channels.filter((c) => c.id !== id);
      this.conflict = null;
    },
    async createPatchPoint(jobId, channelId, payload) {
      const { data } = await api.post(
        `/jobs/${jobId}/channels/${channelId}/patch-points`,
        payload,
      );
      this.upsertPatchPointInChannel(channelId, data);
      return data;
    },
    async updatePatchPoint(jobId, channelId, pointId, payload) {
      const current = this.channels
        .find((channel) => channel.id === channelId)
        ?.patch_points?.find((point) => point.id === pointId);
      try {
        const { data } = await api.patch(
          `/jobs/${jobId}/channels/${channelId}/patch-points/${pointId}`,
          { ...payload, expected_revision: current?.revision },
        );
        this.upsertPatchPointInChannel(channelId, data);
        this.conflict = null;
        return data;
      } catch (error) {
        this.recordConflict(
          error,
          'channel-patch-point',
          { jobId, channelId, pointId },
          payload,
        );
        throw error;
      }
    },
    async deletePatchPoint(jobId, channelId, pointId) {
      const current = this.channels
        .find((channel) => channel.id === channelId)
        ?.patch_points?.find((point) => point.id === pointId);
      try {
        await api.delete(`/jobs/${jobId}/channels/${channelId}/patch-points/${pointId}`, {
          params: { expected_revision: current?.revision },
        });
      } catch (error) {
        this.recordConflict(
          error,
          'channel-patch-point-delete',
          { jobId, channelId, pointId },
          null,
        );
        throw error;
      }
      const ch = this.channels.find((c) => c.id === channelId);
      if (ch && Array.isArray(ch.patch_points)) {
        ch.patch_points = ch.patch_points.filter((p) => p.id !== pointId);
      }
      this.conflict = null;
    },
    upsertChannel(channel) {
      const idx = this.channels.findIndex((c) => c.id === channel.id);
      if (!Array.isArray(channel.patch_points)) channel.patch_points = [];
      if (idx !== -1) {
        const current = this.channels[idx];
        const patchPoints = this.mergeVersionedRows(current.patch_points, channel.patch_points);
        this.channels[idx] =
          channel.revision < current.revision
            ? { ...current, patch_points: patchPoints }
            : { ...channel, patch_points: patchPoints };
      }
      else this.channels.push(channel);
    },
    mergeVersionedRows(currentRows = [], incomingRows = []) {
      const incomingById = new Map(incomingRows.map((row) => [row.id, row]));
      const merged = currentRows
        .filter((row) => incomingById.has(row.id))
        .map((row) => {
          const incoming = incomingById.get(row.id);
          return incoming.revision >= row.revision ? incoming : row;
        });
      const currentIds = new Set(currentRows.map((row) => row.id));
      return [...merged, ...incomingRows.filter((row) => !currentIds.has(row.id))];
    },
    upsertPatchPointInChannel(channelId, point) {
      const ch = this.channels.find((c) => c.id === channelId);
      if (!ch) return;
      if (!Array.isArray(ch.patch_points)) ch.patch_points = [];
      const idx = ch.patch_points.findIndex((p) => p.id === point.id);
      if (idx !== -1) {
        if (point.revision >= ch.patch_points[idx].revision) ch.patch_points[idx] = point;
      }
      else ch.patch_points.push(point);
      ch.patch_points.sort((a, b) => (a.position || 0) - (b.position || 0));
    },
    async createOutput(jobId, listId, payload) {
      const { data } = await api.post(
        `/jobs/${jobId}/channel-lists/${listId}/outputs`,
        payload,
      );
      this.upsertOutputInList(listId, data);
      return data;
    },
    async updateOutput(jobId, listId, outputId, payload) {
      const current = this.lists
        .find((list) => list.id === listId)
        ?.outputs?.find((output) => output.id === outputId);
      try {
        const { data } = await api.patch(
          `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}`,
          { ...payload, expected_revision: current?.revision },
        );
        this.upsertOutputInList(listId, data);
        this.conflict = null;
        return data;
      } catch (error) {
        this.recordConflict(error, 'output', { jobId, listId, outputId }, payload);
        throw error;
      }
    },
    async deleteOutput(jobId, listId, outputId) {
      const current = this.lists
        .find((list) => list.id === listId)
        ?.outputs?.find((output) => output.id === outputId);
      try {
        await api.delete(`/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}`, {
          params: { expected_revision: current?.revision },
        });
      } catch (error) {
        this.recordConflict(error, 'output-delete', { jobId, listId, outputId }, null);
        throw error;
      }
      const list = this.lists.find((l) => l.id === listId);
      if (list && Array.isArray(list.outputs)) {
        list.outputs = list.outputs.filter((o) => o.id !== outputId);
      }
      this.conflict = null;
    },
    async createOutputPoint(jobId, listId, outputId, payload) {
      const { data } = await api.post(
        `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}/points`,
        payload,
      );
      this.upsertOutputPointInOutput(listId, outputId, data);
      return data;
    },
    async updateOutputPoint(jobId, listId, outputId, pointId, payload) {
      const current = this.lists
        .find((list) => list.id === listId)
        ?.outputs?.find((output) => output.id === outputId)
        ?.points?.find((point) => point.id === pointId);
      try {
        const { data } = await api.patch(
          `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}/points/${pointId}`,
          { ...payload, expected_revision: current?.revision },
        );
        this.upsertOutputPointInOutput(listId, outputId, data);
        this.conflict = null;
        return data;
      } catch (error) {
        this.recordConflict(
          error,
          'output-patch-point',
          { jobId, listId, outputId, pointId },
          payload,
        );
        throw error;
      }
    },
    async deleteOutputPoint(jobId, listId, outputId, pointId) {
      const current = this.lists
        .find((list) => list.id === listId)
        ?.outputs?.find((output) => output.id === outputId)
        ?.points?.find((point) => point.id === pointId);
      try {
        await api.delete(
          `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}/points/${pointId}`,
          { params: { expected_revision: current?.revision } },
        );
      } catch (error) {
        this.recordConflict(
          error,
          'output-patch-point-delete',
          { jobId, listId, outputId, pointId },
          null,
        );
        throw error;
      }
      const list = this.lists.find((l) => l.id === listId);
      if (list && Array.isArray(list.outputs)) {
        const out = list.outputs.find((o) => o.id === outputId);
        if (out && Array.isArray(out.points)) {
          out.points = out.points.filter((p) => p.id !== pointId);
        }
        this.conflict = null;
      }
    },
    upsertOutputInList(listId, output) {
      const list = this.lists.find((l) => l.id === listId);
      if (!list) return;
      if (!Array.isArray(list.outputs)) list.outputs = [];
      const idx = list.outputs.findIndex((o) => o.id === output.id);
      if (idx !== -1) {
        const current = list.outputs[idx];
        const points = this.mergeVersionedRows(current.points, output.points);
        list.outputs[idx] =
          output.revision < current.revision
            ? { ...current, points }
            : { ...output, points };
      }
      else list.outputs.push(output);
      list.outputs.sort((a, b) => (a.position || 0) - (b.position || 0));
    },
    upsertOutputPointInOutput(listId, outputId, point) {
      const list = this.lists.find((l) => l.id === listId);
      if (!list) return;
      if (!Array.isArray(list.outputs)) list.outputs = [];
      const out = list.outputs.find((o) => o.id === outputId);
      if (!out) return;
      if (!Array.isArray(out.points)) out.points = [];
      const idx = out.points.findIndex((p) => p.id === point.id);
      if (idx !== -1) {
        if (point.revision >= out.points[idx].revision) out.points[idx] = point;
      }
      else out.points.push(point);
      out.points.sort((a, b) => (a.position || 0) - (b.position || 0));
    },
    upsertList(list) {
      const idx = this.lists.findIndex((l) => l.id === list.id);
      if (idx !== -1) {
        const current = this.lists[idx];
        const outputs = this.mergeVersionedRows(current.outputs || [], list.outputs || []).map(
          (output) => {
            const previous = current.outputs?.find((row) => row.id === output.id);
            return previous
              ? { ...output, points: this.mergeVersionedRows(previous.points, output.points) }
              : output;
          },
        );
        this.lists[idx] = { ...list, outputs };
      }
      else this.lists.push(list);
      if (!this.selectedListId) this.selectedListId = list.id;
    },
    recordConflict(error, entityType, ids, draft) {
      const detail = error.response?.data?.detail;
      if (error.response?.status !== 409 || detail?.code !== 'revision_conflict') return;
      const current = detail.current;
      if (entityType === 'channel' && current) this.upsertChannel(current);
      if (entityType === 'channel-patch-point' && current) {
        this.upsertPatchPointInChannel(ids.channelId, current);
      }
      if (entityType === 'output' && current) this.upsertOutputInList(ids.listId, current);
      if (entityType === 'output-patch-point' && current) {
        this.upsertOutputPointInOutput(ids.listId, ids.outputId, current);
      }
      this.conflict = { entityType, ids, draft, current };
    },
    async reapplyConflict() {
      const conflict = this.conflict;
      if (!conflict?.current || !conflict.draft) return;
      this.conflict = null;
      const { entityType, ids, draft } = conflict;
      if (entityType === 'channel') return this.updateChannel(ids.jobId, ids.id, draft);
      if (entityType === 'channel-patch-point') {
        return this.updatePatchPoint(ids.jobId, ids.channelId, ids.pointId, draft);
      }
      if (entityType === 'output') {
        return this.updateOutput(ids.jobId, ids.listId, ids.outputId, draft);
      }
      if (entityType === 'output-patch-point') {
        return this.updateOutputPoint(
          ids.jobId,
          ids.listId,
          ids.outputId,
          ids.pointId,
          draft,
        );
      }
    },
    clearConflict() {
      this.conflict = null;
    },
    removeListLocal(listId) {
      this.lists = this.lists.filter((l) => l.id !== listId);
      if (this.selectedListId === listId) {
        this.selectedListId = this.lists.length ? this.lists[0].id : null;
        this.channels = [];
      }
    },
    async fetchExportPlugins(jobId, listId) {
      const { data } = await api.get(
        `/jobs/${jobId}/channel-lists/${listId}/export-plugins`,
      );
      return data;
    },
    async downloadExport(jobId, listId, plugin) {
      const { data, headers } = await api.get(
        `/jobs/${jobId}/channel-lists/${listId}/export`,
        { params: { plugin }, responseType: 'blob' },
      );
      return { data, headers };
    },
    applyRealtimeEvent(event) {
      const { type, payload } = event;
      if (type === 'channel.upsert') this.upsertChannel(payload);
      else if (type === 'channel.delete') {
        this.channels = this.channels.filter((c) => c.id !== payload.id);
      } else if (type === 'list.upsert') this.upsertList(payload);
      else if (type === 'list.delete') this.removeListLocal(payload.id);
    },
  },
});
