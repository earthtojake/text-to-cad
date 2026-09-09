import { createController, type Controller } from '@emdash/wire/rpc';
import { pullRequestsContract } from '../api';
import type { PullRequestService } from './pull-request-service';

export function createPullRequestsWireController(service: PullRequestService): Controller {
  return createController(pullRequestsContract, {
    listPullRequests: (input) => service.listPullRequests(input),
    getFilterOptions: (input) => service.getFilterOptions(input.repositoryUrls),
    getPullRequestsForBranch: (input) =>
      service.getPullRequestsForBranch(input.repositoryUrl, input.branch),
    getPullRequestByUrl: (input) => service.getPullRequestByUrl(input.repositoryUrl, input.url),
    registerRepository: (input) => service.registerRepository(input.repositoryUrl),
    unregisterRepository: (input, meta) =>
      service.runOperation('unregister-repository', meta.signal, () =>
        service.unregisterRepository(input.repositoryUrl)
      ),
    // These are not runOperation-wrapped because startSync already scope-tracks and deduplicates them.
    sync: (input) => service.sync(input.repositoryUrl),
    forceFullSync: (input) => service.forceFullSync(input.repositoryUrl),
    syncSingle: (input, meta) =>
      service.runOperation('sync-single', meta.signal, (signal) =>
        service.syncSingle(input.repositoryUrl, input.number, signal)
      ),
    syncChecks: (input, meta) =>
      service.runOperation('sync-checks', meta.signal, (signal) =>
        service.syncChecks(input.repositoryUrl, input.pullRequestUrl, input.headRefOid, signal)
      ),
    cancelSync: (input, meta) =>
      service.runOperation('cancel-sync', meta.signal, () =>
        service.cancelSync(input.repositoryUrl)
      ),
    createPullRequest: (input, meta) =>
      service.runOperation('create-pull-request', meta.signal, (signal) =>
        service.createPullRequest(input, signal)
      ),
    mergePullRequest: (input, meta) =>
      service.runOperation('merge-pull-request', meta.signal, (signal) =>
        service.mergePullRequest(input.repositoryUrl, input.number, input.options, signal)
      ),
    markReadyForReview: (input, meta) =>
      service.runOperation('mark-ready-for-review', meta.signal, (signal) =>
        service.markReadyForReview(input.repositoryUrl, input.number, signal)
      ),
    getPullRequestFiles: (input, meta) =>
      service.runOperation('get-pull-request-files', meta.signal, (signal) =>
        service.getPullRequestFiles(input.repositoryUrl, input.number, signal)
      ),
    getPullRequestComments: (input, meta) =>
      service.runOperation('get-pull-request-comments', meta.signal, (signal) =>
        service.getPullRequestComments(input.repositoryUrl, input.number, signal)
      ),
    syncState: service.syncStateHost(),
  });
}
