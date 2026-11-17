// Retry an async call with exponential backoff: waits `delay`, then `2 * delay`, and so on between
// attempts. The last error is rethrown once every attempt has failed, so callers decide what a
// final failure means. There is no wait after the last attempt.
export async function withRetry(fn, { attempts = 3, delay = 1000 } = {}) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delay * 2 ** attempt));
      }
    }
  }
  throw lastError;
}
