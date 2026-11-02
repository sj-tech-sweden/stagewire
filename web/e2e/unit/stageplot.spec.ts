import { test, expect } from '@playwright/test';
import { elementFromNode, elementsFromGraph, splitElementChanges } from '../../src/utils/graphLegacy';

const node = (over = {}) => ({
  id: 'n1',
  job_id: 'j',
  kind: 'plot_element',
  legacy_ref: 'stage_plot_elements:e1',
  created_at: '2026-01-01',
  canvas_x_cm: 10,
  canvas_y_cm: 20,
  canvas_rotation: 90,
  attributes: { element_type: 'speaker_main', label: 'Main L', width_cm: 40, coverage_angle_h: 60 },
  ...over,
});

test('a plot element node is shown with its legacy id, geometry and linked legacy ids', () => {
  const element = elementFromNode(node(), { channel: 'ch1', output_point: 'op1' });
  expect(element).toMatchObject({
    id: 'e1',
    element_type: 'speaker_main',
    label: 'Main L',
    position_x: 10,
    position_y: 20,
    rotation: 90,
    width_cm: 40,
    height_cm: 60,
    coverage_angle_h: 60,
    linked_channel_id: 'ch1',
    linked_output_point_id: 'op1',
    linked_device_id: null,
    power_node_id: null,
  });
});

test('a native element keeps an imported legacy id and otherwise uses its node id', () => {
  const imported = node({ legacy_ref: null, attributes: { legacy_id: 'e9', element_type: 'stage' } });
  expect(elementFromNode(imported).id).toBe('e9');
  const fresh = node({ legacy_ref: null, attributes: { element_type: 'stage' } });
  expect(elementFromNode(fresh).id).toBe('n1');
});

test('elements come from plot_element nodes only, with links read from the link edges', () => {
  const devices = [node(), { id: 'd', kind: 'mixer', legacy_ref: 'audio_devices:d1', attributes: {} }];
  const edges = [
    { signal: 'link', src_device_id: 'n1', attributes: { role: 'device', legacy_target: 'd1' } },
    { signal: 'audio', src_device_id: 'n1', attributes: { legacy_target: 'ignored' } },
  ];
  const elements = elementsFromGraph(devices, edges);
  expect(elements.map((e) => [e.id, e.linked_device_id])).toEqual([['e1', 'd1']]);
});

test('a hung element shows the legacy id of its rigging point node', () => {
  const point = { id: 'p-node', legacy_ref: 'rigging_points:p1', attributes: {} };
  const hung = node({ attributes: { element_type: 'custom', rigging_point_id: 'p-node' } });
  const element = elementFromNode(hung, {}, new Map([['p-node', point]]));
  expect(element.rigging_point_id).toBe('p1');
});

test('an element edit is split into node changes and links', () => {
  expect(
    splitElementChanges({
      label: 'Vox',
      position_x: 5,
      rotation: 45,
      width_cm: 30,
      image_url: '',
      focal_mm: null,
      linked_channel_id: null,
      linked_device_id: 'd1',
    }),
  ).toEqual({
    node: {
      canvas_x_cm: 5,
      canvas_rotation: 45,
      attributes: { label: 'Vox', width_cm: 30, image_url: '', focal_mm: null },
    },
    links: { linked_channel_id: null, linked_device_id: 'd1' },
  });
  expect(splitElementChanges({ linked_video_input_id: 'v1' })).toEqual({
    node: {},
    links: { linked_video_input_id: 'v1' },
  });
});
