import { onUnmounted } from 'vue';
import { api } from '@/boot/api';

export function useJobSocket(jobId, onEvent) {
  let ws = null;
  let retry = null;
  let closed = false;

  function connect() {
    const token = localStorage.getItem('sw_access_token');
    if (!token || ws) return;
    const base = (api.defaults.baseURL || '').replace(/^http/, 'ws');
    ws = new WebSocket(`${base}/ws/jobs/${jobId}?token=${encodeURIComponent(token)}`);
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      ws = null;
      if (!closed) retry = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws?.close();
  }

  function disconnect() {
    closed = true;
    if (retry) clearTimeout(retry);
    ws?.close();
    ws = null;
  }

  onUnmounted(disconnect);
  return { connect, disconnect };
}
