import type { Result } from '@emdash/shared';

export type RepositoryProvider = 'github';

export type ProviderRepositoryCapabilities = {
  pullRequests: boolean;
  issues: boolean;
};

export type ProviderRepository = {
  provider: RepositoryProvider;
  host: string;
  repositoryUrl: string;
  nameWithOwner: string;
  capabilities: ProviderRepositoryCapabilities;
};

export type ProviderRepositoryError =
  | { type: 'no_remote' }
  | { type: 'invalid_remote' }
  | { type: 'unsupported_provider'; host?: string; reason?: string }
  | { type: 'host_unreachable'; host: string; reason: string }
  | { type: 'host_error'; host: string; reason: string };

export type ProviderRepositoryResult = Result<ProviderRepository, ProviderRepositoryError>;
