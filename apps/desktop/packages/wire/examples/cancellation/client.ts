import {
  createController,
  client,
  connect,
  defineContract,
  memoryTransportPair,
  procedure,
  serve,
} from '@emdash/wire/rpc';
import { z } from 'zod';

const api = defineContract({
  slow: procedure({
    input: z.object({ label: z.string() }),
    output: z.string(),
  }),
});

async function main(): Promise<void> {
  await runCallerCancellation();
  await runDisconnectCancellation();
}

async function runCallerCancellation(): Promise<void> {
  const pair = memoryTransportPair();
  const controller = createController(api, {
    slow: async ({ label }, meta) => {
      await abortableDelay(100, meta.signal);
      return `finished ${label}`;
    },
  });
  serve(pair.right, controller);
  const contractClient = client(api, connect(pair.left));
  const abort = new AbortController();

  const result = contractClient
    .slow({ label: 'cancelled' }, { signal: abort.signal })
    .catch((error: unknown) => error);
  abort.abort();

  console.log('caller cancelled:', await result);
}

async function runDisconnectCancellation(): Promise<void> {
  let aborted = false;
  let started = false;
  const pair = memoryTransportPair();
  const controller = createController(api, {
    slow: async ({ label }, meta) => {
      started = true;
      meta.signal?.addEventListener('abort', () => {
        aborted = true;
      });
      await abortableDelay(100, meta.signal);
      return `finished ${label}`;
    },
  });
  serve(pair.right, controller);
  const contractClient = client(api, connect(pair.left));

  const result = contractClient.slow({ label: 'disconnect' }).catch((error) => error);
  await waitFor(() => started);
  pair.disconnect();

  console.log('disconnect result:', await result);
  await waitFor(() => aborted);
  console.log('server saw abort after disconnect:', aborted);
}

function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new Error('aborted'));
      },
      { once: true }
    );
  });
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error('Timed out waiting for condition');
}

void main();
