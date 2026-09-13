import type { Result } from '@emdash/shared';
import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type { ProjectAttachmentError } from '@core/features/projects/api';
import type { ProviderRepository, ProviderRepositoryError } from '@core/primitives/repository/api';

export type ProviderRepositoryResult = Result<
  ProviderRepository,
  ProviderRepositoryError | ProjectAttachmentError
>;

export const repositoryDomain = 'repository' as const;

export const repositoryContract = defineContract({
  resolveProvider: procedure({
    input: z.object({ projectId: z.string() }),
    output: z.custom<ProviderRepositoryResult>(),
  }),
});
