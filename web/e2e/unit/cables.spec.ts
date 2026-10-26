import { test, expect } from '@playwright/test';
import { buildCableRows, cableTypeCsv, cableTypeOrder, deriveCables } from '../../src/utils/cables';

const lists = [
  {
    id: 'list',
    channels: [],
    outputs: [
      {
        id: 'out',
        name: 'Left',
        points: [
          { id: 'p1', position: 0, device_id: 'mixer', connector: 'xlr' },
          { id: 'p2', position: 1, device_id: 'stagebox', parent_id: 'p1', connector: 'speakon' },
          { id: 'p3', position: 2, device_id: 'amp', parent_id: 'p2', connector: 'speakon' },
        ],
      },
    ],
  },
];

const devices = [
  { id: 'mixer', name: 'Mixer' },
  { id: 'stagebox', name: 'Stagebox' },
  { id: 'amp', name: 'Amp rack' },
];

const elements = [
  {
    id: 'spk',
    element_type: 'speaker_main',
    label: 'Main L',
    position_x: 100,
    position_y: 100,
    width_cm: 42,
    height_cm: 72,
    linked_output_point_id: 'p3',
  },
  {
    id: 'mon',
    element_type: 'monitor',
    label: 'Wedge',
    position_x: 400,
    position_y: 100,
    width_cm: 46,
    height_cm: 36,
    linked_output_point_id: 'p1',
  },
  {
    id: 'unlinked',
    element_type: 'speaker_sub',
    label: 'Sub',
    position_x: 500,
    position_y: 300,
    width_cm: 60,
    height_cm: 60,
  },
  {
    id: 'rack',
    element_type: 'custom',
    label: 'Rack',
    position_x: 0,
    position_y: 200,
    width_cm: 40,
    height_cm: 40,
    linked_device_id: 'amp',
  },
  {
    id: 'desk',
    element_type: 'custom',
    label: 'FOH desk',
    position_x: 0,
    position_y: 400,
    width_cm: 80,
    height_cm: 40,
    linked_device_id: 'mixer',
  },
];

test('output chains end in a cable to each linked speaker or monitor', () => {
  const cables = deriveCables(lists, elements);
  const speakerCables = cables.filter((c) => c.kind === 'speaker');

  expect(speakerCables.map((c) => c.key).sort()).toEqual(['spk:mon', 'spk:spk']);
  const main = speakerCables.find((c) => c.key === 'spk:spk');
  expect(main).toMatchObject({ fromDeviceId: 'amp', fromPointId: 'p3', toElementId: 'spk' });
  const wedge = speakerCables.find((c) => c.key === 'spk:mon');
  expect(wedge).toMatchObject({ fromDeviceId: 'mixer', toElementId: 'mon' });

  const chainLinks = cables.filter((c) => c.kind === 'link' && c.channelId === 'out');
  expect(chainLinks.map((c) => [c.fromDeviceId, c.toDeviceId])).toEqual([
    ['mixer', 'stagebox'],
    ['stagebox', 'amp'],
  ]);
});

test('an unlinked speaker gets no output cable', () => {
  const cables = deriveCables(lists, elements);
  expect(cables.some((c) => c.toElementId === 'unlinked')).toBe(false);
});

test('speaker cables are placed on the plot and named after the speaker', () => {
  const rows = buildCableRows({ lists, devices, elements, plan: null });
  const main = rows.find((r) => r.key === 'spk:spk');
  expect(main?.placed).toBe(true);
  expect(main?.toName).toBe('Main L');
  expect(main?.fromName).toBe('Amp rack');
  expect(main?.pathM).toBeGreaterThan(0);

  const wedge = rows.find((r) => r.key === 'spk:mon');
  expect(wedge?.fromName).toBe('Mixer');
  expect(wedge?.placed).toBe(true);
});

test('a speaker linked to a device does not move that device on the plot', () => {
  const withStrayLink = elements.map((e) =>
    e.id === 'spk' ? { ...e, linked_device_id: 'amp' } : e,
  );
  const rows = buildCableRows({ lists, devices, elements: withStrayLink, plan: null });
  const main = rows.find((r) => r.key === 'spk:spk');
  // The amp's position is its rack element's centre (0,200 with 40 cm sides).
  expect(main?.points[0]).toEqual([20, 220]);
});

test('an unplaced end names the device that needs placing', () => {
  const rows = buildCableRows({
    lists,
    devices,
    elements: elements.filter((e) => e.id !== 'rack'),
    plan: null,
  });
  const main = rows.find((r) => r.key === 'spk:spk');
  expect(main?.placed).toBe(false);
  expect(main?.missingName).toBe('Amp rack');
});

test('a rotated speaker is connected at its drawn centre', () => {
  const rotated = elements.map((e) =>
    e.id === 'spk' ? { ...e, rotation: 180, position_x: 100, position_y: 100 } : e,
  );
  const rows = buildCableRows({ lists, devices, elements: rotated, plan: null });
  const main = rows.find((r) => r.key === 'spk:spk');
  // Rotated 180 degrees about the top-left corner, the 42 x 72 box centre is at (100 - 21, 100 - 36).
  expect(main?.points[main.points.length - 1]).toEqual([79, 64]);
});

test('two cableways that meet give one connected route', () => {
  const plan = {
    cableways: [
      { id: 'a', points: [[0, 0], [100, 0]] },
      { id: 'b', points: [[100, 0], [100, 300]] },
    ],
    routes: {},
  };
  const amp = { id: 'rack', element_type: 'custom', position_x: 0, position_y: 0, width_cm: 0, height_cm: 0, rotation: 0, linked_device_id: 'amp' };
  const spk = { id: 'spk', element_type: 'speaker_main', linked_output_point_id: 'p3', position_x: 100, position_y: 300, width_cm: 0, height_cm: 0, rotation: 0 };
  const routed = buildCableRows({ lists, devices, elements: [amp, spk], plan }).find((r) => r.key === 'spk:spk');
  expect(routed?.placed).toBe(true);
  expect(routed?.mode).toBe('auto');
  expect(routed?.points).toContainEqual([100, 0]);
  expect(routed?.pathM).toBeCloseTo(4, 1);
});

test('a camera cable runs from the camera to its switcher, then down the chain', () => {
  const videoLists = [
    {
      id: 'vlist',
      inputs: [
        {
          id: 'cam1',
          input_number: 1,
          source_label: 'Cam 1',
          patch_points: [
            { id: 'v1', position: 0, device_id: 'mixer', connector: 'sdi' },
            { id: 'v2', position: 1, device_id: 'amp', connector: 'hdmi' },
          ],
        },
      ],
    },
  ];
  const camera = {
    id: 'camEl',
    element_type: 'camera',
    label: 'Cam 1',
    position_x: 0,
    position_y: 0,
    width_cm: 40,
    height_cm: 30,
    rotation: 0,
    linked_video_input_id: 'cam1',
  };
  const cables = deriveCables([], [camera], videoLists);
  expect(cables.map((c) => [c.kind, c.fromElementId, c.fromDeviceId, c.toDeviceId])).toEqual([
    ['source', 'camEl', null, 'mixer'],
    ['link', null, 'mixer', 'amp'],
  ]);
  const rows = buildCableRows({ lists: [], devices, elements: [camera], plan: null, videoLists });
  expect(rows[0]?.fromName).toBe('Cam 1');
  expect(rows[0]?.toName).toBe('Mixer');
});

function routeBetween(from: [number, number], to: [number, number], cableways: unknown[]) {
  const elements = [
    { id: 'rack', element_type: 'custom', position_x: from[0], position_y: from[1], width_cm: 0, height_cm: 0, rotation: 0, linked_device_id: 'amp' },
    { id: 'spk', element_type: 'speaker_main', linked_output_point_id: 'p3', position_x: to[0], position_y: to[1], width_cm: 0, height_cm: 0, rotation: 0 },
  ];
  const plan = { cableways, routes: {}, settings: {} };
  return buildCableRows({ lists, devices, elements, plan }).find((r) => r.key === 'spk:spk');
}

test('a cable does not go across the room to a far cableway when the direct run is short', () => {
  const far = [{ id: 'far', points: [[0, 0], [1000, 0]] }];
  const row = routeBetween([400, 500], [420, 520], far);
  expect(row?.mode).toBe('direct');
  expect(row?.pathM).toBeCloseTo(0.28, 2);
});

test('a camera next to the switcher goes straight to it, not out to a nearby cableway and back', () => {
  const tray = [{ id: 'tray', points: [[0, 0], [1000, 0]] }];
  const row = routeBetween([600, 100], [620, 120], tray);
  expect(row?.mode).toBe('direct');
  expect(row?.pathM).toBeCloseTo(0.28, 2);
});

test('a cableway is used when it saves real distance', () => {
  const tray = [{ id: 'tray', points: [[0, 0], [1000, 0]] }];
  const row = routeBetween([0, 50], [1000, 50], tray);
  expect(row?.mode).toBe('auto');
  expect(row?.points).toContainEqual([0, 0]);
  expect(row?.pathM).toBeCloseTo(11, 1);
});

function routeWithAudience(from: [number, number], to: [number, number], audience: number[][]) {
  const elements = [
    { id: 'rack', element_type: 'custom', position_x: from[0], position_y: from[1], width_cm: 0, height_cm: 0, rotation: 0, linked_device_id: 'amp' },
    { id: 'spk', element_type: 'speaker_main', linked_output_point_id: 'p3', position_x: to[0], position_y: to[1], width_cm: 0, height_cm: 0, rotation: 0 },
  ];
  return buildCableRows({ lists, devices, elements, plan: null, audience, stageOffset: [0, 0] }).find(
    (r) => r.key === 'spk:spk',
  );
}

test('a cable goes around a block of audience when the detour is reasonable', () => {
  const block = [[400, -300], [600, -300], [600, 300], [400, 300]];
  const row = routeWithAudience([0, 0], [1000, 0], block);
  // Either side is the same length; the route must use both corners of one side.
  const sideY = row?.points.find((p) => p[0] === 400)?.[1];
  expect(Math.abs(sideY ?? 0)).toBe(300);
  expect(row?.points).toContainEqual([600, sideY]);
  expect(row?.crossesAudience).toBe(false);
  expect(row?.pathM).toBeCloseTo(12, 1);
});

test('a cable crosses a thin strip of audience when going around is far longer', () => {
  const strip = [[480, -5000], [520, -5000], [520, 5000], [480, 5000]];
  const row = routeWithAudience([0, 0], [1000, 0], strip);
  expect(row?.mode).toBe('direct');
  expect(row?.crossesAudience).toBe(true);
  expect(row?.pathM).toBeCloseTo(10, 1);
});

test('cables are counted per type and length class', () => {
  const rows = [
    { placed: true, connector: 'xlr', assignedM: 5 },
    { placed: true, connector: 'xlr', assignedM: 5 },
    { placed: true, connector: 'xlr', assignedM: 10 },
    { placed: true, connector: 'sdi', assignedM: 20 },
    { placed: true, connector: '', assignedM: 3 },
    { placed: true, connector: 'speakon', assignedM: null },
    { placed: false, connector: 'xlr', assignedM: null },
  ];
  const groups = cableTypeOrder(rows);
  expect(groups.map((g) => g.type)).toEqual(['sdi', 'speakon', 'xlr', 'unspecified']);
  expect(groups.find((g) => g.type === 'xlr')).toMatchObject({
    total: 3,
    lengths: [
      { length: 5, count: 2 },
      { length: 10, count: 1 },
    ],
  });
  expect(groups.find((g) => g.type === 'speakon')?.lengths).toEqual([{ length: 'over', count: 1 }]);
  expect(cableTypeCsv(rows).split('\n')[0]).toBe('Cable type,Length class (m),Count');
});

test('the cableway preference decides when a tray is used', () => {
  const tray = [{ id: 'tray', points: [[0, 0], [1000, 0]] }];
  const elements = [
    { id: 'rack', element_type: 'custom', position_x: 0, position_y: 300, width_cm: 0, height_cm: 0, rotation: 0, linked_device_id: 'amp' },
    { id: 'spk', element_type: 'speaker_main', linked_output_point_id: 'p3', position_x: 1000, position_y: 300, width_cm: 0, height_cm: 0, rotation: 0 },
  ];
  const plan = (factor: number) => ({ cableways: tray, routes: {}, settings: { cableway_factor: factor } });
  const strong = buildCableRows({ lists, devices, elements, plan: plan(0.2) }).find((r) => r.key === 'spk:spk');
  expect(strong?.mode).toBe('auto');
  const weak = buildCableRows({ lists, devices, elements, plan: plan(0.5) }).find((r) => r.key === 'spk:spk');
  expect(weak?.mode).toBe('direct');
});
