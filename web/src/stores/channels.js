import { defineStore } from 'pinia';
import { api } from 'boot/api';

export const useChannelsStore = defineStore('channels', {
  state: () => ({
    lists: [],
    channels: [],
    selectedListId: null,
    loading: false,
    error: null,
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
      const { data } = await api.patch(`/jobs/${jobId}/channels/${id}`, payload);
      const idx = this.channels.findIndex((c) => c.id === id);
      if (idx !== -1) this.channels[idx] = data;
      return data;
    },
    async deleteChannel(jobId, id) {
      await api.delete(`/jobs/${jobId}/channels/${id}`);
      this.channels = this.channels.filter((c) => c.id !== id);
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
      const { data } = await api.patch(
        `/jobs/${jobId}/channels/${channelId}/patch-points/${pointId}`,
        payload,
      );
      this.upsertPatchPointInChannel(channelId, data);
      return data;
    },
    async deletePatchPoint(jobId, channelId, pointId) {
      await api.delete(
        `/jobs/${jobId}/channels/${channelId}/patch-points/${pointId}`,
      );
      const ch = this.channels.find((c) => c.id === channelId);
      if (ch && Array.isArray(ch.patch_points)) {
        ch.patch_points = ch.patch_points.filter((p) => p.id !== pointId);
      }
    },
    upsertChannel(channel) {
      const idx = this.channels.findIndex((c) => c.id === channel.id);
      if (!Array.isArray(channel.patch_points)) channel.patch_points = [];
      if (idx !== -1) this.channels[idx] = channel;
      else this.channels.push(channel);
    },
    upsertPatchPointInChannel(channelId, point) {
      const ch = this.channels.find((c) => c.id === channelId);
      if (!ch) return;
      if (!Array.isArray(ch.patch_points)) ch.patch_points = [];
      const idx = ch.patch_points.findIndex((p) => p.id === point.id);
      if (idx !== -1) ch.patch_points[idx] = point;
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
      const { data } = await api.patch(
        `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}`,
        payload,
      );
      this.upsertOutputInList(listId, data);
      return data;
    },
    async deleteOutput(jobId, listId, outputId) {
      await api.delete(
        `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}`,
      );
      const list = this.lists.find((l) => l.id === listId);
      if (list && Array.isArray(list.outputs)) {
        list.outputs = list.outputs.filter((o) => o.id !== outputId);
      }
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
      const { data } = await api.patch(
        `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}/points/${pointId}`,
        payload,
      );
      this.upsertOutputPointInOutput(listId, outputId, data);
      return data;
    },
    async deleteOutputPoint(jobId, listId, outputId, pointId) {
      await api.delete(
        `/jobs/${jobId}/channel-lists/${listId}/outputs/${outputId}/points/${pointId}`,
      );
      const list = this.lists.find((l) => l.id === listId);
      if (list && Array.isArray(list.outputs)) {
        const out = list.outputs.find((o) => o.id === outputId);
        if (out && Array.isArray(out.points)) {
          out.points = out.points.filter((p) => p.id !== pointId);
        }
      }
    },
    upsertOutputInList(listId, output) {
      const list = this.lists.find((l) => l.id === listId);
      if (!list) return;
      if (!Array.isArray(list.outputs)) list.outputs = [];
      const idx = list.outputs.findIndex((o) => o.id === output.id);
      if (idx !== -1) list.outputs[idx] = output;
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
      if (idx !== -1) out.points[idx] = point;
      else out.points.push(point);
      out.points.sort((a, b) => (a.position || 0) - (b.position || 0));
    },
    upsertList(list) {
      const idx = this.lists.findIndex((l) => l.id === list.id);
      if (idx !== -1) this.lists[idx] = list;
      else this.lists.push(list);
      if (!this.selectedListId) this.selectedListId = list.id;
    },
    removeListLocal(listId) {
      this.lists = this.lists.filter((l) => l.id !== listId);
      if (this.selectedListId === listId) {
        this.selectedListId = this.lists.length ? this.lists[0].id : null;
        this.channels = [];
      }
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
