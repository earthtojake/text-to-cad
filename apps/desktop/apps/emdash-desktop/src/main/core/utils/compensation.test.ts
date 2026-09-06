import { describe, expect, it, vi } from 'vitest';
import { withCompensation } from './compensation';

describe('withCompensation', () => {
  it('returns the action result when the action succeeds', async () => {
    const compensate = vi.fn();

    await expect(
      withCompensation({
        action: async () => 'ok',
        compensate,
      })
    ).resolves.toBe('ok');

    expect(compensate).not.toHaveBeenCalled();
  });

  it('runs compensation and rethrows when the action fails', async () => {
    const error = new Error('action failed');
    const compensate = vi.fn(async () => {});

    await expect(
      withCompensation({
        action: async () => {
          throw error;
        },
        compensate,
      })
    ).rejects.toBe(error);

    expect(compensate).toHaveBeenCalledTimes(1);
  });

  it('reports compensation failures without hiding the action error', async () => {
    const actionError = new Error('action failed');
    const compensationError = new Error('compensation failed');
    const onCompensationError = vi.fn();

    await expect(
      withCompensation({
        action: async () => {
          throw actionError;
        },
        compensate: async () => {
          throw compensationError;
        },
        onCompensationError,
      })
    ).rejects.toBe(actionError);

    expect(onCompensationError).toHaveBeenCalledWith(compensationError);
  });
});
