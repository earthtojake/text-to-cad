import { Result } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { githubEvents } from '@core/features/github/node';
import type { GitHubAccountService } from '@core/features/github/node/accounts/github-account-service';
import type { GitHubDeviceFlowService } from '@core/features/github/node/services/github-device-flow-service';
import type { GitHubRepositoryService } from '@core/features/github/node/services/repo-service';
import type {
  GitHubAccountState,
  GitHubAccountSummary,
  GitHubAuthResponse,
  GitHubImportCliAccountsResponse,
  GitHubRemoveAccountResponse,
  GitHubSetDefaultAccountResponse,
} from '@core/primitives/github/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';

export function createGithubOperations(dependencies: {
  accountService: GitHubAccountService;
  deviceFlowService: GitHubDeviceFlowService;
  logger: Logger;
  repositoryService: GitHubRepositoryService;
  telemetry: TelemetryService;
}) {
  const {
    accountService: githubAccountService,
    deviceFlowService: githubDeviceFlowService,
    logger,
    repositoryService: repoService,
    telemetry,
  } = dependencies;
  return {
    getAccountState: async (): Promise<GitHubAccountState> =>
      Result.tryAsync(async () => {
        const accounts = await githubAccountService.listAccounts();
        return {
          connected: accounts.length > 0,
          accounts,
          defaultAccountId: accounts.find((account) => account.isDefault)?.accountId ?? null,
        };
      }).unwrapOrElse((error) => {
        logger.error('Failed to get GitHub account state', { error });
        return { connected: false, accounts: [], defaultAccountId: null };
      }),

    auth: async (): Promise<GitHubAuthResponse> => {
      let result: Awaited<ReturnType<typeof githubDeviceFlowService.start>>;
      try {
        result = await githubDeviceFlowService.start();
      } catch (error) {
        logger.error('GitHub authentication failed', { error });
        githubEvents.emit(undefined, {
          type: 'auth-error',
          error: 'device_flow_error',
          message: 'Authentication failed',
        });
        return { success: false, error: 'Authentication failed' };
      }

      if (!result.success) return result;

      try {
        const accountSummary = (await githubAccountService.listAccounts()).find(
          (candidate) => candidate.accountId === result.account.accountId
        );
        if (!accountSummary) {
          const message = 'Failed to register GitHub account';
          githubEvents.emit(undefined, {
            type: 'auth-error',
            error: 'account_registration_failed',
            message,
          });
          return { success: false, error: message };
        }

        telemetry.capture('integration_connected', { provider: 'github' });
        githubEvents.emit(undefined, { type: 'auth-success', user: result.user });
        return { success: true, account: accountSummary };
      } catch (error) {
        logger.error('Failed to register GitHub account after device flow', { error });
        const message = 'Failed to register GitHub account';
        githubEvents.emit(undefined, {
          type: 'auth-error',
          error: 'account_registration_failed',
          message,
        });
        return { success: false, error: message };
      }
    },

    listAccounts: (): Promise<GitHubAccountSummary[]> =>
      Result.tryAsync(() => githubAccountService.listAccounts()).unwrapOrElse((error) => {
        logger.error('Failed to list GitHub accounts', { error });
        return [];
      }),

    importCliAccounts: (): Promise<GitHubImportCliAccountsResponse> =>
      Result.tryAsync<GitHubImportCliAccountsResponse>(async () => {
        const result = await githubAccountService.importCliAccounts();
        if (result.importedAccountIds.length > 0) {
          telemetry.capture('integration_connected', { provider: 'github', source: 'cli' });
        }
        return result;
      }).unwrapOrElse((error) => {
        logger.error('Failed to import GitHub CLI accounts', { error });
        return { success: false, error: 'Failed to import GitHub CLI accounts' };
      }),

    setDefaultAccount: (accountId: string): Promise<GitHubSetDefaultAccountResponse> =>
      Result.tryAsync<GitHubSetDefaultAccountResponse>(async () => {
        const account = await githubAccountService.setDefaultAccount(accountId);
        if (!account) return { success: false, error: 'GitHub account not found' };
        return { success: true, account };
      }).unwrapOrElse((error) => {
        logger.error('Failed to set default GitHub account', { error });
        return { success: false, error: 'Failed to set default GitHub account' };
      }),

    removeAccount: (accountId: string): Promise<GitHubRemoveAccountResponse> =>
      Result.tryAsync<GitHubRemoveAccountResponse>(async () => {
        const accounts = await githubAccountService.removeAccount(accountId);
        if (!accounts) return { success: false, error: 'GitHub account not found' };
        telemetry.capture('integration_disconnected', { provider: 'github' });
        return { success: true, accounts };
      }).unwrapOrElse((error) => {
        logger.error('Failed to remove GitHub account', { error });
        return { success: false, error: 'Failed to remove GitHub account' };
      }),

    authCancel: (): Promise<{ success: true } | { success: false; error: string }> =>
      Result.tryAsync<{ success: true } | { success: false; error: string }>(async () => {
        githubDeviceFlowService.cancel();
        return { success: true };
      }).unwrapOrElse((error) => {
        logger.error('Failed to cancel GitHub auth', { error });
        return { success: false, error: 'Failed to cancel' };
      }),

    // -- Repositories --------------------------------------------------------

    getRepositories: (accountId?: string) =>
      Result.tryAsync(() => repoService.listRepositories({ accountId })).unwrapOrElse((error) => {
        logger.error('Failed to get repositories', { error });
        return [];
      }),

    getOwners: (
      accountId?: string
    ): Promise<
      | { success: true; owners: Awaited<ReturnType<typeof repoService.getOwners>> }
      | { success: false; error: string }
    > =>
      Result.tryAsync<
        | { success: true; owners: Awaited<ReturnType<typeof repoService.getOwners>> }
        | { success: false; error: string }
      >(async () => {
        const owners = await repoService.getOwners({ accountId });
        return { success: true, owners };
      }).unwrapOrElse((error) => {
        logger.error('Failed to get owners', { error });
        return { success: false, error: error.message ?? 'Failed to get owners' };
      }),

    createRepository: (params: {
      name: string;
      owner: string;
      description?: string;
      isPrivate?: boolean;
      visibility?: 'public' | 'private';
      accountId?: string | null;
    }): Promise<
      | {
          success: true;
          repoUrl: string;
          cloneUrl: string;
          nameWithOwner: string;
          defaultBranch: string;
        }
      | { success: false; error: string }
    > =>
      Result.tryAsync<
        | {
            success: true;
            repoUrl: string;
            cloneUrl: string;
            nameWithOwner: string;
            defaultBranch: string;
          }
        | { success: false; error: string }
      >(async () => {
        const isPrivate = params.isPrivate ?? params.visibility === 'private';
        const repoInfo = await repoService.createRepository({
          name: params.name,
          owner: params.owner,
          description: params.description,
          isPrivate,
          authContext: { accountId: params.accountId ?? undefined },
        });
        return {
          success: true,
          repoUrl: repoInfo.url,
          cloneUrl: repoInfo.cloneUrl,
          nameWithOwner: repoInfo.nameWithOwner,
          defaultBranch: repoInfo.defaultBranch,
        };
      }).unwrapOrElse((error) => {
        logger.error('Failed to create repository', { error });
        return { success: false, error: error.message ?? 'Failed to create repository' };
      }),

    deleteRepository: (params: {
      owner: string;
      name: string;
      accountId?: string | null;
    }): Promise<{ success: true } | { success: false; error: string }> =>
      Result.tryAsync<{ success: true } | { success: false; error: string }>(async () => {
        await repoService.deleteRepository(params.owner, params.name, {
          accountId: params.accountId ?? undefined,
        });
        return { success: true };
      }).unwrapOrElse((error) => {
        logger.error('Failed to delete repository', { error });
        return { success: false, error: error.message ?? 'Failed to delete repository' };
      }),
  };
}
