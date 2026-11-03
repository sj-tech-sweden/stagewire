import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { catalogQuery } from '@/utils/workspace';

// How many products to pull (and thus how many availability calls to make) per request. Kept small
// so the date-ranged availability lookups stay fast; the drawer lazy-loads further pages on scroll.
const PAGE_SIZE = 50;

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    q: '',
    categories: [],
    manufacturers: [],
    inStockOnly: false,
    includeRentals: false,
    items: [],
    total: 0,
    facets: { category: {}, manufacturer: {} },
    dateRangeSupported: false,
    selected: {},
    loading: false,
    loadingMore: false,
    hasMore: false,
    page: 0,
    lastQuery: null,
    error: null,
  }),
  getters: {
    visibleItems: (state) =>
      state.inStockOnly ? state.items.filter((i) => (i.available_qty ?? 0) > 0) : state.items,
    selectedItems: (state) => state.items.filter((i) => state.selected[i.id]),
  },
  actions: {
    async search(stockwireJobId, { startDate = null, endDate = null } = {}) {
      this.lastQuery = { stockwireJobId, startDate, endDate };
      this.page = 0;
      this.items = [];
      this.hasMore = true;
      await this._fetchPage();
    },
    async loadMore() {
      if (!this.hasMore || this.loading || this.loadingMore) return;
      this.page += 1;
      await this._fetchPage();
    },
    async _fetchPage() {
      if (!this.lastQuery) return;
      const { stockwireJobId, startDate, endDate } = this.lastQuery;
      this.loadingMore = this.page > 0;
      this.loading = this.page === 0;
      this.error = null;
      try {
        const params = catalogQuery({
          q: this.q,
          categories: this.categories,
          manufacturers: this.manufacturers,
          jobId: stockwireJobId,
          limit: PAGE_SIZE,
          skip: this.page * PAGE_SIZE,
        });
        // A job rental window makes the search date-ranged: the backend swaps each product's current
        // stock for the minimum available quantity across that window.
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
        // Rentals (e.g. from Eventory) are hidden unless the user opts in.
        if (!this.includeRentals) params.set('exclude_rental', 'true');
        const { data } = await api.get(`/stockwire/catalog/search?${params.toString()}`);
        const items = data.items || [];
        this.items = this.page === 0 ? items : [...this.items, ...items];
        this.total = data.total || 0;
        this.facets = data.facets || { category: {}, manufacturer: {} };
        this.dateRangeSupported = Boolean(data.availability?.date_range_supported);
        this.hasMore = this.items.length < this.total;
      } catch (err) {
        this.error = err.response?.data?.detail || err.message || 'Search failed';
      } finally {
        this.loading = false;
        this.loadingMore = false;
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
