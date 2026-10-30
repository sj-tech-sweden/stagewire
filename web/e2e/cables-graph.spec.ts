import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';
import { buildCableRows } from '../src/utils/cables';
import { buildCableRowsFromGraph } from '../src/utils/graphLegacy';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function send(
  request: APIRequestContext,
  headers: Record<string, string>,
  method: 'post' | 'put',
  path: string,
  data: object,
) {
  const res = await request[method](`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

test('the cable list built from the graph equals the one built from the legacy data', async ({ page, request }) => {
  await login(page);
  const h = await authedHeaders(page);
  const post = (path: string, data: object) => send(request, h, 'post', path, data);
  const jobId = (await post('/jobs', { title: `E2E Cables ${Date.now()}` })).id as string;
  const job = `/jobs/${jobId}`;

  const box = await post(`${job}/devices`, { name: 'Stagebox', device_type: 'analog_stagebox' });
  const desk = await post(`${job}/devices`, { name: 'Desk', device_type: 'mixer' });
  const amp = await post(`${job}/devices`, { name: 'Amp', device_type: 'amp' });
  const cam = await post(`${job}/devices`, { name: 'Cam', device_type: 'ptz_camera' });
  const matrix = await post(`${job}/devices`, { name: 'Matrix', device_type: 'switcher' });
  const led = await post(`${job}/devices`, { name: 'LED proc', device_type: 'other' });

  const list = await post(`${job}/channel-lists`, { name: 'FOH' });
  const channels = [];
  for (const [number, label] of [[1, 'Vox'], [2, 'Keys']] as const) {
    const ch = await post(`${job}/channel-lists/${list.id}/channels`, { channel_number: number, source_label: label });
    for (const [position, dev, type] of [[0, box, 'analog_stagebox'], [1, desk, 'mixer']] as const) {
      await post(`${job}/channels/${ch.id}/patch-points`, {
        position,
        point_type: type,
        device_id: dev.id,
        connector: position === 0 ? 'XLR' : 'Dante',
      });
    }
    channels.push(ch);
  }
  const out = await post(`${job}/channel-lists/${list.id}/outputs`, { name: 'Mon 1' });
  const console_ = await post(`${job}/channel-lists/${list.id}/outputs/${out.id}/points`, {
    position: 0,
    point_type: 'mixer',
    device_id: desk.id,
  });
  const ampPoint = await post(`${job}/channel-lists/${list.id}/outputs/${out.id}/points`, {
    position: 1,
    point_type: 'amp',
    device_id: amp.id,
    connector: 'XLR',
  });
  await post(`${job}/channel-lists/${list.id}/outputs/${out.id}/points`, {
    position: 2,
    point_type: 'stage',
    device_id: box.id,
    parent_id: console_.id,
  });

  const vlist = await post(`${job}/video-lists`, { name: 'Video' });
  const vin = await post(`${job}/video-lists/${vlist.id}/inputs`, { source_label: 'Cam 1' });
  await send(request, h, 'put', `${job}/video-inputs/${vin.id}/patch-chain`, {
    steps: [{ device_id: cam.id }, { device_id: matrix.id, input_port: 'In 3' }],
  });
  const vout = await post(`${job}/video-lists/${vlist.id}/outputs`, { destination_label: 'LED wall' });
  await send(request, h, 'put', `${job}/video-outputs/${vout.id}/patch-chain`, {
    steps: [{ device_id: matrix.id }, { device_id: led.id, parent_index: 0, source_port: 'Out 1' }],
  });

  const el = (data: object) => post(`${job}/plot-elements`, { width_cm: 40, height_cm: 40, ...data });
  await el({ element_type: 'microphone', label: 'Vox mic', position_x: 100, position_y: 100, linked_channel_id: channels[0].id });
  await el({ element_type: 'performer', label: 'Keys player', position_x: 200, position_y: 100, linked_channel_id: channels[1].id });
  await el({ element_type: 'stagebox', position_x: 300, position_y: 300, linked_device_id: box.id });
  await el({ element_type: 'mixer', position_x: 600, position_y: 300, linked_device_id: desk.id });
  await el({ element_type: 'amp', position_x: 500, position_y: 500, linked_device_id: amp.id });
  await el({ element_type: 'speaker', label: 'Wedge', position_x: 700, position_y: 500, linked_output_point_id: ampPoint.id });
  await el({ element_type: 'camera', position_x: 50, position_y: 400, linked_video_input_id: vin.id, linked_device_id: cam.id });
  await el({ element_type: 'switcher', position_x: 400, position_y: 50, linked_device_id: matrix.id });
  await el({ element_type: 'led_wall', position_x: 450, position_y: 80, linked_device_id: led.id });

  const get = async (path: string) => (await request.get(`${API_BASE}/api/v1${path}`, { headers: h })).json();
  const plan = { cableways: [], routes: {}, settings: {} };
  const legacy = buildCableRows({
    lists: await get(`${job}/channel-lists`),
    devices: await get(`${job}/devices`),
    elements: await get(`${job}/plot-elements`),
    videoLists: await get(`${job}/video-lists`),
    plan,
    audience: [],
    stageOffset: [0, 0],
  });
  const graph = await get(`${job}/graph`);
  const fromGraph = buildCableRowsFromGraph({
    devices: graph.devices,
    edges: graph.edges,
    plan,
    audience: [],
    stageOffset: [0, 0],
  });

  expect(legacy.length).toBeGreaterThan(8);
  const key = (rows: { key: string }[]) => [...rows].sort((a, b) => (a.key < b.key ? -1 : 1));
  expect(key(fromGraph)).toEqual(key(legacy));
});
