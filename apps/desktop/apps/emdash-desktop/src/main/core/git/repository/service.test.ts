import type * as WireState from '@emdash/wire/state';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GitRepositoryService } from './service';

const mocks = vi.hoisted(() => ({
  dispose: vi.fn(),
  remote: vi.fn(),
}));

vi.mock('@emdash/wire/state', async (importOriginal) => ({
  ...(await importOriginal<typeof WireState>()),
  remote: mocks.remote,
}));

describe('GitRepositoryService', () => {
  beforeEach(() => {
    mocks.dispose.mockReset();
    mocks.remote.mockReset();
    mocks.remote.mockReturnValue(() => ({
      states: {
        remotes: {
          __stateNode: {
            observe(listener: (snapshot: unknown) => void) {
              listener({
                status: 'ready',
                value: { remotes: [{ name: 'origin', url: 'git@example' }] },
              });
              return mocks.dispose;
            },
          },
        },
      },
    }));
  });

  it('subscribes to remote state and disposes the observation scope', async () => {
    const service = new GitRepositoryService(
      { repository: { model: { state: vi.fn() } } } as never,
      { repository: { root: { kind: 'posix' }, segments: ['plain-folder'] } } as never,
      vi.fn()
    );
    const cb = vi.fn();

    const unsubscribe = service.subscribeRemotes(cb);

    expect(cb).toHaveBeenCalledWith({ remotes: [{ name: 'origin', url: 'git@example' }] });

    unsubscribe();

    await vi.waitFor(() => expect(mocks.dispose).toHaveBeenCalled());
  });
});
