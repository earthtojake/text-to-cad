import { createLiveLogReplicaCache } from '@emdash/wire/live';
import { client, connect, memoryTransportPair, serve } from '@emdash/wire/rpc';
import { api, appendLine, createLogController } from './server';

async function main(): Promise<void> {
  const controller = createLogController();
  const pair = memoryTransportPair();
  const stop = serve(pair.right, controller);
  const contractClient = client(api, connect(pair.left));

  // The replica cache keeps one ReplicaLog per build id, seeded from the
  // snapshot and kept current from appends over the wire.
  const cache = createLiveLogReplicaCache(api.buildLog, contractClient.buildLog);
  const lease = cache.acquire({ buildId: 'build-1' });
  const replica = await lease.ready();
  replica.onAppend((chunk) => console.log('log append:', JSON.stringify(chunk)));

  appendLine('build-1', 'first line');
  appendLine('build-1', 'second line');
  appendLine('build-1', 'third line');
  await settle();

  console.log('replica text:', JSON.stringify(replica.text()));

  await lease.release();
  await cache.dispose();
  stop();
  pair.left.close();
  pair.right.close();
}

async function settle(): Promise<void> {
  for (let turn = 0; turn < 4; turn += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

void main();
