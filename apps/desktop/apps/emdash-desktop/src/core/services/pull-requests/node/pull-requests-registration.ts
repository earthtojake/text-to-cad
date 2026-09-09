import { err, ok, type Result } from '@emdash/shared';
import type { Disposable } from '@emdash/shared/concurrency';
import { log } from '@emdash/shared/logger';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import type { GitHubAuthError, PullRequestsRuntimeClient } from '@core/services/pull-requests/api';
import type { PullRequestSyncIdentity } from './sync-identity';

type PullRequestsRegistrationClient = Pick<
  PullRequestsRuntimeClient,
  | 'registerRepository'
  | 'unregisterRepository'
  | 'cancelSync'
  | 'getPullRequestsForBranch'
  | 'syncSingle'
>;

/**
 * The blessed per-project account resolution (spec: github-git-settings §2).
 * Success carries the effective account row id; failures are discriminated so
 * sync-identity requests can fail closed with an honest status. The `type`
 * field is consumed structurally to stay decoupled from the GitHub feature's
 * error taxonomy.
 */
type ProjectAccountResolution = Result<
  { accountId?: string },
  {
    type?: 'project_not_found' | 'unconfigured' | 'disabled' | 'account_selection_failed';
    message: string;
  }
>;

type PullRequestsRegistrationOptions = {
  getClient: () => Promise<PullRequestsRegistrationClient>;
  onProjectOpened(handler: (projectId: string) => void): () => void;
  onProjectClosed(handler: (projectId: string) => void): () => void;
  onTaskProvisioned(
    handler: (event: { projectId: string; branchName: string | undefined }) => void
  ): () => void;
  subscribeToProjectRemotes(projectId: string, handler: () => void): (() => void) | undefined;
  resolveProjectRepositoryUrls(projectId: string): Promise<string[]>;
  resolveProjectAuthContext(projectId: string): Promise<ProjectAccountResolution>;
};

/**
 * Tells the pull-request worker *what* to sync (repository URLs per open
 * project) and answers its per-sync "as whom" requests through the blessed
 * resolver (spec: github-git-settings §8). No account is pushed into the
 * worker — identity is resolved fresh on every sync, so account changes apply
 * on the next sync without any event plumbing.
 */
export class PullRequestsRegistration implements Disposable {
  private readonly projectRepositoryUrls = new Map<string, string[]>();
  private readonly repositoryUnsubscribes = new Map<string, () => void>();
  private unsubscribes: Array<() => void> = [];

  constructor(private readonly options: PullRequestsRegistrationOptions) {}

  initialize(): void {
    if (this.unsubscribes.length > 0) return;
    this.unsubscribes = [
      this.options.onProjectOpened((projectId) => {
        void this.onProjectOpened(projectId);
      }),
      this.options.onProjectClosed((projectId) => {
        void this.onProjectClosed(projectId);
      }),
      this.options.onTaskProvisioned(({ projectId, branchName }) => {
        void this.onTaskProvisioned(projectId, branchName).catch((error) => {
          log.warn('PullRequestsRegistration: failed to refresh a provisioned task', {
            projectId,
            error: String(error),
          });
        });
      }),
    ];
  }

  dispose(): void {
    for (const unsubscribe of this.unsubscribes) unsubscribe();
    this.unsubscribes = [];
    for (const unsubscribe of this.repositoryUnsubscribes.values()) unsubscribe();
    this.repositoryUnsubscribes.clear();
    this.projectRepositoryUrls.clear();
  }

  async onProjectOpened(projectId: string): Promise<void> {
    await this.refreshProject(projectId);
    this.subscribeToRepository(projectId);
  }

  async onProjectClosed(projectId: string): Promise<void> {
    this.repositoryUnsubscribes.get(projectId)?.();
    this.repositoryUnsubscribes.delete(projectId);
    const removedUrls = this.projectRepositoryUrls.get(projectId) ?? [];
    this.projectRepositoryUrls.delete(projectId);
    await this.cancelUnreferenced(removedUrls);
  }

  async refreshProject(projectId: string): Promise<void> {
    const previousUrls = this.projectRepositoryUrls.get(projectId) ?? [];
    const repositoryUrls = await this.resolveRepositoryUrls(projectId);
    this.projectRepositoryUrls.set(projectId, repositoryUrls);

    const client = await this.options.getClient();
    for (const repositoryUrl of repositoryUrls) {
      const result = await client.registerRepository({ repositoryUrl });
      if (!result.success) {
        log.warn('PullRequestsRegistration: failed to register repository', {
          projectId,
          repositoryUrl,
          error: result.error,
        });
      }
    }

    const current = new Set(repositoryUrls);
    await this.cancelUnreferenced(previousUrls.filter((url) => !current.has(url)));
  }

  /**
   * Answers the worker's per-sync "as whom" request: the effective account of
   * an open project referencing the repository, resolved through the blessed
   * resolver at call time. Fails closed — an unresolvable account (or a
   * repository no open project references) yields an error, never a fallback
   * identity.
   */
  async resolveSyncIdentity(
    repositoryUrl: string
  ): Promise<Result<PullRequestSyncIdentity, GitHubAuthError>> {
    const host = parseRepositoryRef(repositoryUrl)?.host ?? 'unknown';
    const projectIds = [...this.projectRepositoryUrls.entries()]
      .filter(([, urls]) => urls.includes(repositoryUrl))
      .map(([projectId]) => projectId);
    if (projectIds.length === 0) {
      return err({
        type: 'account_unresolvable',
        host,
        message: 'No open project references this repository.',
      });
    }
    let failure: { type?: string; message: string } | undefined;
    for (const projectId of projectIds) {
      const resolved = await this.options.resolveProjectAuthContext(projectId);
      if (resolved.success) {
        // The blessed resolver returns an account on success; treat a missing
        // id defensively as "keep looking" rather than an implicit default.
        if (resolved.data.accountId) return ok({ accountId: resolved.data.accountId });
        continue;
      }
      failure ??= resolved.error;
    }
    return err(mapProjectAccountError(host, failure));
  }

  async onTaskProvisioned(projectId: string, branchName: string | undefined): Promise<void> {
    if (!branchName) return;
    const repositoryUrls =
      this.projectRepositoryUrls.get(projectId) ?? (await this.resolveRepositoryUrls(projectId));
    const client = await this.options.getClient();
    for (const repositoryUrl of repositoryUrls) {
      const result = await client.getPullRequestsForBranch({ repositoryUrl, branch: branchName });
      if (!result.success) continue;
      for (const pullRequest of result.data.prs) {
        const number = pullRequest.identifier
          ? Number.parseInt(pullRequest.identifier.replace('#', ''), 10)
          : Number.NaN;
        if (Number.isNaN(number)) continue;
        await client.syncSingle({ repositoryUrl, number });
      }
    }
  }

  async deleteProjectData(projectId: string): Promise<void> {
    const repositoryUrls =
      this.projectRepositoryUrls.get(projectId) ?? (await this.resolveRepositoryUrls(projectId));
    this.projectRepositoryUrls.delete(projectId);
    const client = await this.options.getClient();
    for (const repositoryUrl of repositoryUrls) {
      if (this.isReferenced(repositoryUrl)) continue;
      const result = await client.unregisterRepository({ repositoryUrl });
      if (!result.success) {
        log.warn('PullRequestsRegistration: failed to unregister deleted project repository', {
          projectId,
          repositoryUrl,
          error: result.error,
        });
      }
    }
  }

  private subscribeToRepository(projectId: string): void {
    if (this.repositoryUnsubscribes.has(projectId)) return;
    const unsubscribe = this.options.subscribeToProjectRemotes(projectId, () => {
      void this.refreshProject(projectId).catch((error) => {
        log.warn('PullRequestsRegistration: failed to refresh changed remotes', {
          projectId,
          error: String(error),
        });
      });
    });
    if (unsubscribe) this.repositoryUnsubscribes.set(projectId, unsubscribe);
  }

  private async resolveRepositoryUrls(projectId: string): Promise<string[]> {
    try {
      return await this.options.resolveProjectRepositoryUrls(projectId);
    } catch (error) {
      log.warn('PullRequestsRegistration: failed to resolve project remotes', {
        projectId,
        error: String(error),
      });
      return [];
    }
  }

  private async cancelUnreferenced(repositoryUrls: string[]): Promise<void> {
    if (repositoryUrls.length === 0) return;
    const client = await this.options.getClient();
    for (const repositoryUrl of repositoryUrls) {
      if (this.isReferenced(repositoryUrl)) continue;
      await client.cancelSync({ repositoryUrl });
    }
  }

  private isReferenced(repositoryUrl: string): boolean {
    return [...this.projectRepositoryUrls.values()].some((urls) => urls.includes(repositoryUrl));
  }
}

function mapProjectAccountError(
  host: string,
  failure: { type?: string; message: string } | undefined
): GitHubAuthError {
  switch (failure?.type) {
    case 'unconfigured':
      return {
        type: 'auth_required',
        host,
        message: failure.message,
        hint: 'Connect a GitHub account from settings.',
      };
    case 'disabled':
      return { type: 'github_disabled', host, message: failure.message };
    default:
      return {
        type: 'account_unresolvable',
        host,
        message: failure?.message ?? 'No GitHub account resolved for this repository.',
      };
  }
}
