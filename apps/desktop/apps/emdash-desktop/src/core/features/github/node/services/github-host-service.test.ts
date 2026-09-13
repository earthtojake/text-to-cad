import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GitHubHostService } from './github-host-service';

const mockMetaGet = vi.hoisted(() => vi.fn());
const mockOctokit = vi.hoisted(() => vi.fn());

vi.mock('@octokit/rest', () => ({
  Octokit: mockOctokit,
}));

describe('GitHubHostService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOctokit.mockImplementation(function (options) {
      return {
        options,
        rest: { meta: { get: mockMetaGet } },
      };
    });
  });

  it('accepts github.com without probing', async () => {
    const service = new GitHubHostService();

    await expect(service.probe('github.com')).resolves.toEqual({
      success: true,
      data: { host: 'github.com' },
    });
    expect(mockOctokit).not.toHaveBeenCalled();
  });

  it('probes GHES meta endpoint with the enterprise API base URL', async () => {
    mockMetaGet.mockResolvedValue({ data: { verifiable_password_authentication: true } });
    const service = new GitHubHostService();

    await expect(service.probe('ghe.example.com')).resolves.toEqual({
      success: true,
      data: { host: 'ghe.example.com' },
    });
    expect(mockOctokit).toHaveBeenCalledWith({ baseUrl: 'https://ghe.example.com/api/v3' });
  });

  it('treats authenticated-only GHES meta responses as compatible', async () => {
    mockMetaGet.mockRejectedValue({ status: 403 });
    const service = new GitHubHostService();

    await expect(service.probe('ghe.example.com')).resolves.toEqual({
      success: true,
      data: { host: 'ghe.example.com' },
    });
  });

  it('returns not_github for a 404 meta response', async () => {
    mockMetaGet.mockRejectedValue({ status: 404 });
    const service = new GitHubHostService();

    await expect(service.probe('gitlab.example.com')).resolves.toEqual({
      success: false,
      error: {
        type: 'not_github',
        host: 'gitlab.example.com',
        reason: 'meta endpoint returned 404',
      },
    });
  });
});
