import { createScope } from '@emdash/shared/concurrency';
import {
  createInProcessWire,
  defineContract,
  liveModel,
  liveState,
  procedure,
  type LiveModelClientHandle,
} from '@emdash/wire/rpc';
import { cell, expose, observe, remote } from '@emdash/wire/state';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  domainClient,
  getWireConnection,
  resetWireConnection,
  seedWireConnection,
} from './connection';
import { seedSliceWire } from './testing';

const echoContract = defineContract({
  greet: procedure({ input: z.object({ name: z.string() }), output: z.string() }),
});

type EchoClient = { greet(input: { name: string }): Promise<string> };

const echoImpl = {
  greet: ({ name }: { name: string }) => `hello ${name}`,
};

// Mirrors production wiring: slice contracts nested under their domain key,
// exactly like desktopDomainContracts feeds desktopWireContract.
function createEchoWire() {
  return createInProcessWire(defineContract({ echo: echoContract }), { echo: echoImpl });
}

afterEach(() => {
  resetWireConnection();
});

describe('wire connection seam', () => {
  it('throws synchronously on unseeded access', () => {
    expect(() => getWireConnection()).toThrowError(/no connection seeded/);
    expect(() => domainClient<EchoClient>('echo', echoContract)).toThrowError(
      /no connection seeded/
    );
  });

  it('throws on double seed', () => {
    const wire = createEchoWire();
    seedWireConnection(async () => wire.connection);
    expect(() => seedWireConnection(async () => wire.connection)).toThrowError(/already seeded/);
  });

  it('memoizes the connection and domain clients until reset', async () => {
    const wireA = createEchoWire();
    let sourceCalls = 0;
    seedWireConnection(async () => {
      sourceCalls += 1;
      return wireA.connection;
    });

    const first = getWireConnection();
    expect(getWireConnection()).toBe(first);
    await first;
    expect(sourceCalls).toBe(1);

    const clientA = domainClient<EchoClient>('echo', echoContract);
    expect(domainClient<EchoClient>('echo', echoContract)).toBe(clientA);

    resetWireConnection();
    expect(() => getWireConnection()).toThrowError(/no connection seeded/);

    const wireB = createEchoWire();
    seedWireConnection(async () => wireB.connection);
    expect(getWireConnection()).not.toBe(first);
    expect(domainClient<EchoClient>('echo', echoContract)).not.toBe(clientA);

    await wireA.dispose();
    await wireB.dispose();
  });

  it('routes a domain client identically to the aggregate client', async () => {
    const wire = createEchoWire();
    seedWireConnection(async () => wire.connection);

    const echo = await domainClient<EchoClient>('echo', echoContract);
    const viaDomain = await echo.greet({ name: 'seam' });
    const viaAggregate = await wire.client.echo.greet({ name: 'seam' });

    expect(viaDomain).toBe('hello seam');
    expect(viaDomain).toBe(viaAggregate);

    await wire.dispose();
  });

  // Regression: live topics are encoded from contract def ids, so the domain
  // client must be built from the domain-nested contract — a bare pathPrefix
  // would prefix call paths only and leave live topics unroutable.
  it('streams a live model through a domain client', async () => {
    const liveContract = defineContract({
      counters: liveModel({
        key: z.object({ id: z.string() }),
        states: { value: liveState({ data: z.number() }) },
      }),
    });
    const source = cell(1);
    const handle = seedSliceWire('live', liveContract, {
      counters: expose(defineContract({ live: liveContract }).live.counters, { value: source }),
    });

    type LiveClient = { counters: LiveModelClientHandle<typeof liveContract.counters> };
    const live = await domainClient<LiveClient>('live', liveContract);
    const model = remote(liveContract.counters, live.counters, { lingerMs: 15_000 });
    const state = model({ id: 'a' }).states.value;
    const observerScope = createScope({ label: 'test-observer' });
    const seen: Array<number | undefined> = [];
    observe(state, (snapshot) => seen.push(snapshot.value), { scope: observerScope });
    await vi.waitFor(() => expect(seen).toContain(1));

    source.set(2);
    await vi.waitFor(() => expect(seen).toContain(2));

    await observerScope.dispose();
    await model.dispose();
    await handle.dispose();
  });

  it('seedSliceWire serves a slice with no renderer host', async () => {
    const handle = seedSliceWire('echo', echoContract, echoImpl);

    const echo = await domainClient<EchoClient>('echo', echoContract);
    await expect(echo.greet({ name: 'slice' })).resolves.toBe('hello slice');

    await handle.dispose();
    expect(() => getWireConnection()).toThrowError(/no connection seeded/);
  });
});
