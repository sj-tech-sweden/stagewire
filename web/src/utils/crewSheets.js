// Pure helpers behind the crew view's read-only Sound / Lights / Video tabs. They take the payload of
// `GET /jobs/{id}/crew-sheets` (see api/app/domains/share/router.py) and shape it into rows the
// components render as lists or cards; nothing here edits anything.

import { endpointLabel, endpointSides } from './workspace';

const text = (v) => String(v ?? '').trim();

// "Rio · 5" for a socket ref, using the soft patch's own device names; '' when unpatched.
function socketText(ref, deviceNames) {
  if (!ref) return '';
  return `${deviceNames.get(ref.device_id) || '?'} · ${ref.socket}`;
}

function deviceNamesOf(entry) {
  return new Map((entry?.soft_patch?.ports || []).map((p) => [p.device_id, p.device_name]));
}

// The input list: one row per channel in channel order, with the socket it is patched to.
export function crewInputRows(entry) {
  const names = deviceNamesOf(entry);
  const strips = new Map((entry?.soft_patch?.channels || []).map((c) => [c.id, c]));
  return [...(entry?.list?.channels || [])]
    .sort((a, b) => (a.channel_number || 0) - (b.channel_number || 0))
    .map((c) => {
      const soft = strips.get(c.id) || {};
      return {
        id: c.id,
        number: c.channel_number,
        name: text(c.source_label),
        source: [text(c.input_type), text(c.device)].filter(Boolean).join(' · '),
        stand: text(c.stand_type),
        phantom: !!c.phantom_power,
        stereo: !!c.is_stereo_linked,
        notes: text(c.notes),
        patch: socketText(soft.dsp_source ?? c.dsp_source, names),
        directOut: socketText(soft.direct_out ?? c.direct_out, names),
      };
    });
}

// The buses / mixes with where each leaves from ("Rio · Out 3–4 (L, R)"; a one-sided endpoint says its side).
export function crewBusRows(entry, { out = 'Out' } = {}) {
  const names = deviceNamesOf(entry);
  return [...(entry?.list?.outputs || [])]
    .sort((a, b) => (a.position || 0) - (b.position || 0))
    .map((o) => ({
      id: o.id,
      name: text(o.name),
      mode: o.mode || 'mono',
      role: o.role || 'aux',
      notes: text(o.notes),
      outputs: (o.out_endpoints || []).map((e) => {
        const side = e.side ? ` (${e.side})` : (e.refs || []).length > 1 ? ` (${endpointSides(e, o.mode)})` : '';
        return `${endpointLabel(e, names, { out })}${side}`;
      }),
    }));
}

// Every patched socket, sorted by device then port then socket: "Rio · Out 5 → Kick".
export function crewSocketRows(entry) {
  const channels = new Map((entry?.list?.channels || []).map((c) => [c.id, c]));
  const buses = new Map((entry?.list?.outputs || []).map((o) => [o.id, o]));
  const label = (c) => `${c.channel_number ?? ''} ${text(c.source_label)}`.trim();
  const rows = [];
  for (const s of entry?.soft_patch?.sockets || []) {
    const who = [];
    for (const id of s.dsp_source_channel_ids || (s.dsp_source_channel_id ? [s.dsp_source_channel_id] : [])) {
      if (channels.has(id)) who.push(label(channels.get(id)));
    }
    if (s.direct_out_channel_id && channels.has(s.direct_out_channel_id)) who.push(label(channels.get(s.direct_out_channel_id)));
    if (s.out_socket_bus_id && buses.has(s.out_socket_bus_id)) {
      who.push(`${text(buses.get(s.out_socket_bus_id).name)}${s.out_socket_side ? ` ${s.out_socket_side}` : ''}`);
    }
    if (!who.length) continue;
    rows.push({ key: s.key, device: s.device_name, port: s.port_id, direction: s.direction, socket: s.socket, who: who.join(', ') });
  }
  return rows.sort(
    (a, b) => a.device.localeCompare(b.device) || a.port.localeCompare(b.port) || a.socket - b.socket,
  );
}

// Console facts for the crew: the surface (layers -> banks -> labelled faders), DCAs and FX.
export function crewConsole(entry) {
  const summary = entry?.console || {};
  const strips = new Map((entry?.fader_map?.strips || []).map((s) => [s.id, s]));
  const nameOf = (id) => {
    const s = strips.get(id);
    return s ? `${s.number ? `${s.number} ` : ''}${text(s.label)}`.trim() : '';
  };
  const layers = (entry?.fader_map?.layers || []).map((layer) => ({
    layer: layer.layer,
    banks: layer.banks.map((bank) => ({
      id: bank.id,
      label: bank.label,
      faders: bank.strips.map((cell) => ({ fader: cell.fader, label: cell.id ? `${cell.number ? `${cell.number} ` : ''}${text(cell.label)}`.trim() : '' })),
    })),
  }));
  const dcas = Object.entries(summary.dcas || {})
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([n, d]) => ({ number: Number(n), name: text(d.name), members: (d.members || []).map(nameOf).filter(Boolean) }));
  const fx = (summary.fx || []).map((e) => ({ id: e.id, name: text(e.name), type: e.type, sends: (e.sends || []).map(nameOf).filter(Boolean) }));
  return {
    profile: summary.profile?.name || '',
    hasSurface: !!entry?.fader_map?.enabled,
    layers,
    dcas,
    fx,
  };
}

// Fixtures grouped per universe, in address order, each with its occupied range ("17–34").
export function crewUniverses(fixtures) {
  const groups = new Map();
  for (const f of fixtures || []) {
    const key = f.universe ?? 0; // 0 = not yet given a universe
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }
  return [...groups.entries()]
    .sort((a, b) => (a[0] || 9999) - (b[0] || 9999))
    .map(([universe, list]) => ({
      universe,
      fixtures: list
        .slice()
        .sort((a, b) => (a.dmx_address ?? 9999) - (b.dmx_address ?? 9999) || a.position - b.position)
        .map((f) => ({
          id: f.id,
          name: text(f.device_name) || text(f.fixture_type) || '—',
          type: text(f.fixture_type),
          mode: text(f.channel_mode),
          address: f.dmx_address ?? null,
          range: f.dmx_address && f.footprint > 1 ? `${f.dmx_address}–${f.dmx_address + f.footprint - 1}` : f.dmx_address ? String(f.dmx_address) : '',
          footprint: f.footprint ?? null,
          location: text(f.location),
          purpose: text(f.purpose),
          notes: text(f.notes),
          conflict: !!f.dmx_conflict,
          overflow: !!f.dmx_overflow,
        })),
    }));
}

// Video: per list, its inputs and outputs in number order with the signal summary.
export function crewVideo(video) {
  const signal = (r) => [r.resolution, r.frame_rate, r.signal_format].map(text).filter(Boolean).join(' · ');
  return (video?.lists || []).map((l) => ({
    id: l.id,
    name: text(l.name),
    inputs: [...(l.inputs || [])]
      .sort((a, b) => (a.input_number || 0) - (b.input_number || 0))
      .map((i) => ({ id: i.id, number: i.input_number, label: text(i.source_label), type: text(i.source_type), connector: text(i.connector), signal: signal(i), notes: text(i.notes) })),
    outputs: [...(l.outputs || [])]
      .sort((a, b) => (a.output_number || 0) - (b.output_number || 0))
      .map((o) => ({ id: o.id, number: o.output_number, label: text(o.name) || text(o.destination_label), destination: text(o.destination_label), connector: text(o.connector), signal: signal(o), notes: text(o.notes) })),
  }));
}
