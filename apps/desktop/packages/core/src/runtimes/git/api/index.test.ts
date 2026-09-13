import { describe, expect, it } from 'vitest';
import * as git from './index';

describe('@emdash/core/runtimes/git/api public exports', () => {
  it('exposes wire contracts and shared pure helpers', () => {
    const exported = git as Record<string, unknown>;

    expect(exported.gitContract).toBeTypeOf('object');
    expect(exported.gitRepositoryContract).toBeTypeOf('object');
    expect(exported.gitCheckoutContract).toBeTypeOf('object');
    expect(exported.computeBaseRef).toBeTypeOf('function');
    expect(exported.StatusParser).toBeTypeOf('function');
    expect(exported.TooManyFilesChangedError).toBeTypeOf('function');
    expect(exported.MAX_STATUS_FILES).toBeTypeOf('number');
  });

  it('does not export runtime implementations or the removed oRPC surface', () => {
    const exported = git as Record<string, unknown>;

    expect(exported.GitRuntime).toBeUndefined();
    expect(exported.createGitContractImpl).toBeUndefined();
    expect(exported.createGitController).toBeUndefined();
    expect(exported.GitSessionManager).toBeUndefined();
    expect(exported.createRepositoryLiveHost).toBeUndefined();
    expect(exported.RepositoryResource).toBeUndefined();
    expect(exported.createCheckoutLiveHost).toBeUndefined();
    expect(exported.CheckoutResource).toBeUndefined();
    expect(exported.GitRepository).toBeUndefined();
    expect(exported.GitCheckout).toBeUndefined();
    expect(exported.gitRouter).toBeUndefined();
    expect(exported.serveGitPort).toBeUndefined();
    expect(exported.createGitSessionJobs).toBeUndefined();
  });
});
