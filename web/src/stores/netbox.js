import { defineStore } from 'pinia';
import { api } from '@/boot/api';

// NetBox IPAM/DCIM integration store. Mirrors the Stockwire store: it owns the
// integration config (so every NetBox-dependent control can be hidden when the
// integration is disabled) and proxies the device-mirroring / IP-assignment
// calls. When disabled, the integration never touches the network.
export const useNetboxStore = defineStore('netbox', {
  state: () => ({
    integration: {
      enabled: false,
      base_url: '',
      has_api_token: false,
      tenant_slug: '',
      site_slug: '',
      device_role_slug: 'stagewire',
      device_type_id: null,
      default_device_status: 'staged',
      public_url: '',
      webhook_ready: false,
    },
    availableIps: [],
    vlans: [],
    prefixes: [],
    loading: false,
  }),
  getters: {
    // Drives hiding of every NetBox-connected control across the app. The Settings
    // NetBox tab stays visible so the integration can be re-enabled.
    isEnabled: (state) => !!state.integration.enabled,
  },
  actions: {
    async loadIntegration() {
      const { data } = await api.get('/netbox');
      this.integration = data;
      return data;
    },
    async saveIntegration(payload) {
      const { data } = await api.put('/netbox', payload);
      this.integration = data;
      return data;
    },
    async test() {
      const { data } = await api.post('/netbox/test');
      return data;
    },
    async provision() {
      const { data } = await api.post('/netbox/provision');
      return data;
    },
    async syncJob(jobId) {
      const { data } = await api.post(`/netbox/sync-job/${jobId}`, {});
      return data;
    },
    async queryIps(prefix) {
      if (!prefix) return [];
      this.loading = true;
      try {
        const { data } = await api.get('/netbox/available-ips', { params: { prefix } });
        this.availableIps = data;
        return data;
      } finally {
        this.loading = false;
      }
    },
    async assignIp({ device_id, prefix, address }) {
      const { data } = await api.post('/netbox/assign-ip', { device_id, prefix, address });
      return data;
    },
    async loadVlans() {
      const { data } = await api.get('/netbox/vlans');
      this.vlans = data;
      return data;
    },
    async loadPrefixes(vlanId) {
      const { data } = await api.get('/netbox/prefixes', { params: { vlan_id: vlanId } });
      this.prefixes = data;
      return data;
    },
  },
});
