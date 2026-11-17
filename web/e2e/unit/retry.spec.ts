import { test, expect } from '@playwright/test';
import { withRetry } from '../../src/utils/retry';

test('a call that fails transiently is retried until it succeeds', async () => {
  let calls = 0;
  const result = await withRetry(
    async () => {
      calls += 1;
      if (calls < 3) throw new Error('transient');
      return 'ok';
    },
    { delay: 1 },
  );
  expect(result).toBe('ok');
  expect(calls).toBe(3);
});

test('after the last attempt the final error is rethrown, with no attempts beyond the limit', async () => {
  let calls = 0;
  await expect(
    withRetry(
      async () => {
        calls += 1;
        throw new Error(`failure ${calls}`);
      },
      { attempts: 3, delay: 1 },
    ),
  ).rejects.toThrow('failure 3');
  expect(calls).toBe(3);
});
