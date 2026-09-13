import { describe, expect, it } from 'vitest';
import { contributeScopedStore, scopedStoreToken, ScopedStoreHost } from './scoped-store-host';

describe('ScopedStoreHost', () => {
  it('constructs typed stores in contribution order with dependency lookup', () => {
    const firstToken = scopedStoreToken<{ value: number }>('first');
    const secondToken = scopedStoreToken<{ doubled: number }>('second');
    const host = new ScopedStoreHost({ initial: 3 }, [
      contributeScopedStore({
        token: firstToken,
        create: ({ initial }: { initial: number }) => ({ value: initial }),
      }),
      contributeScopedStore({
        token: secondToken,
        create: (_context: { initial: number }, stores) => ({
          doubled: stores.get(firstToken).value * 2,
        }),
      }),
    ]);

    expect(host.get(secondToken).doubled).toBe(6);
  });

  it('activates once and disposes in reverse order by default', () => {
    const events: string[] = [];
    const firstToken = scopedStoreToken<{ id: string }>('first');
    const secondToken = scopedStoreToken<{ id: string }>('second');
    const contribution = (id: string, token: typeof firstToken) =>
      contributeScopedStore({
        token,
        create: () => ({ id }),
        activate: (store) => events.push(`activate:${store.id}`),
        dispose: (store) => events.push(`dispose:${store.id}`),
      });
    const host = new ScopedStoreHost({}, [
      contribution('first', firstToken),
      contribution('second', secondToken),
    ]);

    host.activate();
    host.activate();
    host.dispose();
    host.dispose();

    expect(events).toEqual([
      'activate:first',
      'activate:second',
      'dispose:second',
      'dispose:first',
    ]);
  });

  it('memoizes contribution readiness', async () => {
    const events: string[] = [];
    const token = scopedStoreToken<{ id: string }>('ready');
    const host = new ScopedStoreHost({}, [
      contributeScopedStore({
        token,
        create: () => ({ id: 'store' }),
        ready: async (store) => {
          await Promise.resolve();
          events.push(`ready:${store.id}`);
        },
      }),
    ]);

    const firstReady = host.ready();
    expect(host.ready()).toBe(firstReady);
    await firstReady;
    await host.ready();

    expect(events).toEqual(['ready:store']);
  });

  it('only disposes stores created before construction fails', () => {
    const events: string[] = [];
    const firstToken = scopedStoreToken<object>('first');
    const failingToken = scopedStoreToken<object>('failing');
    const skippedToken = scopedStoreToken<object>('skipped');

    expect(
      () =>
        new ScopedStoreHost({}, [
          contributeScopedStore({
            token: firstToken,
            create: () => {
              events.push('create:first');
              return {};
            },
            dispose: () => events.push('dispose:first'),
          }),
          contributeScopedStore({
            token: failingToken,
            create: () => {
              events.push('create:failing');
              throw new Error('factory failed');
            },
            dispose: () => events.push('dispose:failing'),
          }),
          contributeScopedStore({
            token: skippedToken,
            create: () => {
              events.push('create:skipped');
              return {};
            },
            dispose: () => events.push('dispose:skipped'),
          }),
        ])
    ).toThrow('factory failed');
    expect(events).toEqual(['create:first', 'create:failing', 'dispose:first']);
  });

  it('rejects duplicate tokens', () => {
    const token = scopedStoreToken<object>('duplicate');
    const contribution = contributeScopedStore({
      token,
      create: () => ({}),
    });

    expect(() => new ScopedStoreHost({}, [contribution, contribution])).toThrow(
      "Duplicate scoped store token 'duplicate'"
    );
  });
});
