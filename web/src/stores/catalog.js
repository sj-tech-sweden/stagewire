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
    async search(stockwireJobId, { startDate = null, endDate = null } = {}) {
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
        // A job rental window makes the search date-ranged: the backend swaps each product's
        // current stock for its minimum available quantity across that window.
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
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
    async cases() {
      const { data } = await api.get('/stockwire/catalog/cases');
      return data.items || [];
    },
    async caseChildren(caseDeviceId) {
      const { data } = await api.get(`/stockwire/catalog/cases/${caseDeviceId}/children`);
      return data.items || [];
    },
  },
});
