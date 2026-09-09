import { createScope } from '@emdash/shared/concurrency';
import { client, connect, memoryTransportPair, serve } from '@emdash/wire/rpc';
import { flushStateTurn, observe, optimistic, remote, snapshot } from '@emdash/wire/state';
import { api, createCounterController, createCounterProvider } from './server';

async function main(): Promise<void> {
  const scope = createScope({ label: 'state-kernel-example' });

  // Server side: kernel cells exposed as a live model behind a controller.
  const provider = createCounterProvider({ scope });
  const controller = createCounterController(provider);
  const pair = memoryTransportPair();
  const stop = serve(pair.right, controller);

  // Client side: `remote()` turns the live model client handle into a keyed
  // family of members whose states are kernel readables.
  const contractClient = client(api, connect(pair.left));
  const model = remote(api.counter, contractClient.counter, { scope });
  const member = model({ id: 'demo' });

  observe(
    member.states.value,
    (current) => {
      console.log('observed:', current.status, current.value);
    },
    { scope }
  );

  await waitFor(() => snapshot(member.states.value).value?.count === 0);
  console.log('seeded snapshot:', snapshot(member.states.value).value);

  // Optimistic mutation: the view applies the draft immediately and reconciles
  // once the authoritative cursor settles.
  const view = optimistic(member.states.value);
  const result = await view.run(member.mutations.increment, { by: 2 }, (draft, input) => {
    draft.count += input.by;
  });
  console.log('mutation result:', result.success ? 'ok' : result.error);

  await waitFor(() => snapshot(member.states.value).value?.count === 2);
  console.log('settled snapshot:', snapshot(member.states.value).value);

  await model.dispose();
  stop();
  pair.left.close();
  pair.right.close();
  await provider.dispose();
  await scope.dispose();
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    flushStateTurn();
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error('Timed out waiting for state-kernel example condition');
}

void main();
