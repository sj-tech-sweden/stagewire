import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { catalogQuery } from '@/utils/workspace';

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    q: '',
    categories: [],
    manufacturers: [],
    inStockOnly: false,
    items: [],
    total: 0,
    facets: { category: {}, manufacturer: {} },
    dateRangeSupported: false,
    selected: {},
    loading: false,
    error: null,
  }),
  getters: {
    visibleItems: (state) =>
      state.inStockOnly ? state.items.filter((i) => (i.available_qty ?? 0) > 0) : state.items,
    selectedItems: (state) => state.items.filter((i) => state.selected[i.id]),
  },
  actions: {
    async search(stockwireJobId) {
      this.loading = true;
      this.error = null;
      try {
        const params = catalogQuery({
          q: this.q,
          categories: this.categories,
          manufacturers: this.manufacturers,
          jobId: stockwireJobId,
          limit: 200,
        });
        const { data } = await api.get(`/stockwire/catalog/search?${params.toString()}`);
        this.items = data.items || [];
        this.total = data.total || 0;
        this.facets = data.facets || { category: {}, manufacturer: {} };
        this.dateRangeSupported = Boolean(data.availability?.date_range_supported);
      } catch (err) {
        this.error = err.response?.data?.detail || err.message || 'Search failed';
      } finally {
        this.loading = false;
      }
    },
    toggle(id) {
      this.selected = { ...this.selected, [id]: !this.selected[id] };
    },
    clearSelection() {
      this.selected = {};
    },
    async caseChildren(caseDeviceId) {
      const { data } = await api.get(`/stockwire/catalog/cases/${caseDeviceId}/children`);
      return data.items || [];
    },
  },
});
