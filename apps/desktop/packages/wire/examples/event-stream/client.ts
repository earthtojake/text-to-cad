import { createEventStreamHost } from '@emdash/wire/live';
import {
  client,
  connect,
  createController,
  defineContract,
  eventStream,
  memoryTransportPair,
  serve,
} from '@emdash/wire/rpc';
import { z } from 'zod';

const api = defineContract({
  fileEvents: eventStream({
    key: z.object({ rootPath: z.string() }),
    event: z.object({
      kind: z.enum(['create', 'update', 'delete']),
      path: z.string(),
    }),
  }),
});

async function main(): Promise<void> {
  const host = createEventStreamHost(api.fileEvents);
  const controller = createController(api, { fileEvents: host });
  const pair = memoryTransportPair();
  const stop = serve(pair.right, controller);
  const contractClient = client(api, connect(pair.left));

  const unsubscribe = await contractClient.fileEvents.subscribe(
    { rootPath: '/repo' },
    {
      onEvent: (event) => console.log('event:', event.kind, event.path),
      onGap: () => console.log('gap: refresh file tree'),
    }
  );

  await new Promise((resolve) => setTimeout(resolve, 0));
  host.emit({ rootPath: '/repo' }, { kind: 'create', path: '/repo/package.json' });
  host.emit({ rootPath: '/repo' }, { kind: 'update', path: '/repo/src/index.ts' });

  await new Promise((resolve) => setTimeout(resolve, 0));
  unsubscribe();
  stop();
  pair.left.close();
  pair.right.close();
}

void main();
