import { onUnmounted } from 'vue';
import { api } from '@/boot/api';

// Venue base-rig realtime socket. Mirrors useJobSocket but connects to the venue
// room (/ws/venues/{venueId}) so NetBox IP-assignment / conflict events push to the
// venue editor the same way job events push to the job workspace. Venues are edited by
// authenticated admins only, so we use the session token (no crew share-token fallback).
export function useVenueSocket(venueId, onEvent, onStatus = null) {
  let ws = null;
  let retry = null;
  let closed = false;

  function connect() {
    const token = localStorage.getItem('sw_access_token');
    if (!token || ws || !venueId) return;
    const base = (api.defaults.baseURL || '').replace(/^http/, 'ws');
    ws = new WebSocket(`${base}/ws/venues/${venueId}?token=${encodeURIComponent(token)}`);
    ws.onopen = () => onStatus?.('open');
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data));
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      onStatus?.('closed');
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
