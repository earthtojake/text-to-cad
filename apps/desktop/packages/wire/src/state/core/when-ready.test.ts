import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it } from 'vitest';
import { cell } from './cell';
import { snapshot } from './node';
import { flushStateTurn } from './scheduler';
import { whenReady } from './when-ready';

describe('whenReady', () => {
  it('resolves immediately when the node is already settled', async () => {
    const scope = createScope();
    const source = cell('ready');

    await expect(whenReady(source, { scope })).resolves.toMatchObject({
      value: 'ready',
      status: 'live',
    });
    await scope.dispose();
  });

  it('resolves with the first non-loading snapshot', async () => {
    const scope = createScope();
    const source = cell('initial');
    source.set('initial', { status: 'loading' });
    const ready = whenReady(source, { scope });

    source.set('next');
    flushStateTurn();

    await expect(ready).resolves.toMatchObject({ value: 'next', status: 'live' });
    await scope.dispose();
  });

  it('returns error snapshots to the caller', async () => {
    const scope = createScope();
    const source = cell('initial');
    source.set('initial', { status: 'loading' });
    const error = new Error('failed');
    const ready = whenReady(source, { scope });

    source.set('initial', { status: 'error', error });
    flushStateTurn();

    await expect(ready).resolves.toMatchObject({ status: 'error', error });
    await scope.dispose();
  });

  it('resolves with the latest snapshot when the scope disposes', async () => {
    const scope = createScope();
    const source = cell('initial');
    source.set('initial', { status: 'loading' });
    const ready = whenReady(source, { scope });

    await scope.dispose();

    await expect(ready).resolves.toEqual(snapshot(source));
  });
});
