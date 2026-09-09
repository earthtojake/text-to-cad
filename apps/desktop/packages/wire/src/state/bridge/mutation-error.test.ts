import { ok } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import { mapMutationErrors } from './mutation-error';

describe('mapMutationErrors', () => {
  it('maps expected thrown errors to mutation results', async () => {
    const result = await mapMutationErrors(
      () => {
        throw new ExpectedError('typed');
      },
      (error) => (error instanceof ExpectedError ? { type: error.message } : undefined)
    );

    expect(result).toEqual({ success: false, error: { type: 'typed' } });
  });

  it('passes successful results through', async () => {
    await expect(
      mapMutationErrors(
        () => ok('done'),
        () => undefined
      )
    ).resolves.toEqual(ok('done'));
  });

  it('rethrows unexpected errors', async () => {
    const unexpected = new Error('unexpected');

    await expect(
      mapMutationErrors(
        () => {
          throw unexpected;
        },
        () => undefined
      )
    ).rejects.toBe(unexpected);
  });
});

class ExpectedError extends Error {}
