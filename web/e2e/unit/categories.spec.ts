import { test, expect } from '@playwright/test';
import { categoryOfDeviceType, categoryOfElement } from '../../src/utils/categories';

test('elements and devices sort into sound, video, stage and other', () => {
  expect(categoryOfElement({ element_type: 'microphone' })).toBe('sound');
  expect(categoryOfElement({ element_type: 'performer' })).toBe('stage');
  expect(categoryOfElement({ element_type: 'camera' })).toBe('video');
  expect(categoryOfElement({ element_type: 'custom', linked_device_id: 'd1' }, 'projector')).toBe('video');
  expect(categoryOfElement({ element_type: 'custom', linked_device_id: 'd2' }, 'mixer')).toBe('sound');
  expect(categoryOfElement({ element_type: 'custom' })).toBe('other');
  expect(categoryOfDeviceType('switcher')).toBe('video');
  expect(categoryOfDeviceType('digital_stagebox')).toBe('sound');
  expect(categoryOfDeviceType('network')).toBe('other');
  expect(categoryOfDeviceType('patchbay')).toBe('other');
  expect(categoryOfDeviceType('something_new')).toBe('other');
});
