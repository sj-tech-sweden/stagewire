import { test, expect } from '@playwright/test';
import { isShareViewLocation, isShareViewPath } from '../../src/utils/shareView';

test('only /jobs/:id/view is the share view', () => {
  expect(isShareViewPath('/jobs/12/view')).toBe(true);
  expect(isShareViewPath('/jobs/12')).toBe(false);
  expect(isShareViewPath('/login')).toBe(false);
});

test('share view is recognised in history and hash mode, ignoring the query string', () => {
  expect(isShareViewLocation({ pathname: '/jobs/1/view', hash: '' })).toBe(true);
  expect(isShareViewLocation({ pathname: '/', hash: '#/jobs/1/view?token=abc' })).toBe(true);
  expect(isShareViewLocation({ pathname: '/', hash: '#/jobs/1' })).toBe(false);
  expect(isShareViewLocation({ pathname: '/jobs/1', hash: '' })).toBe(false);
});
