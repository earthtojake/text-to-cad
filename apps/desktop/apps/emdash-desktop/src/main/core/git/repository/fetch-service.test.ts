import { describe, expect, it, vi } from 'vitest';
import { GitRepositoryFetchService } from './fetch-service';

const runtime = vi.hoisted(() => ({ runGitJob: vi.fn() }));

vi.mock('@main/core/git/runtime-client', async (importOriginal) => ({
  ...(await importOriginal()),
  runGitJob: runtime.runGitJob,
}));

describe('GitRepositoryFetchService', () => {
  it('attempts background fetches for SSH remotes using system git credentials', async () => {
    const fetch = {};
    const snapshot = vi.fn().mockResolvedValue({
      data: { remotes: [{ name: 'origin', url: 'git@github.com:owner/repo.git' }] },
    });
    const getRemote = vi.fn().mockResolvedValue('origin');
    runtime.runGitJob.mockResolvedValue({ success: true, data: undefined });
    const git = {
      repository: {
        fetch,
        model: { state: vi.fn(() => ({ snapshot })) },
      },
    };
    const repository = { repository: { root: { kind: 'posix' }, segments: ['repo'] } };

    const service = new GitRepositoryFetchService(git as never, repository as never, getRemote);

    service.start();

    await vi.waitFor(() =>
      expect(runtime.runGitJob).toHaveBeenCalledWith(
        expect.anything(),
        fetch,
        expect.objectContaining({ remote: 'origin' })
      )
    );
    service.stop();
  });
});
