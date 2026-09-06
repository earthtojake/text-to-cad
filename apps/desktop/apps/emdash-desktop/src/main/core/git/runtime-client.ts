import type {
  CheckoutSelector,
  GitFilePath,
  RepositorySelector,
} from '@emdash/core/runtimes/git/api';
import { ok, type Result } from '@emdash/shared';
import type {
  JobError,
  JobInput,
  JobProgress,
  JobResult,
  LiveJobClientHandle,
  LiveJobEndpointDef,
} from '@emdash/wire/rpc';
import { hostPathFromNative, portablePath } from '@core/primitives/desktop-runtime/api';
import { runRuntimeLiveJob } from '@main/core/runtime/live-job';

export function repositorySelector(nativePath: string): RepositorySelector {
  return { repository: hostPathFromNative(nativePath) };
}

export function checkoutSelector(nativePath: string): CheckoutSelector {
  return { checkout: hostPathFromNative(nativePath) };
}

export function gitFilePath(relativePath: string): GitFilePath {
  return portablePath(relativePath.replaceAll('\\', '/')) as GitFilePath;
}

export async function mutationResult<Data, Error>(
  pending: Promise<Result<{ data: Data }, Error>>
): Promise<Result<Data, Error>> {
  const result = await pending;
  return result.success ? ok(result.data.data) : result;
}

export function runGitJob<Def extends LiveJobEndpointDef>(
  definition: Def,
  handle: LiveJobClientHandle<Def>,
  input: JobInput<Def>,
  onProgress?: (progress: JobProgress<Def>) => void
): Promise<Result<JobResult<Def>, JobError<Def>>> {
  return runRuntimeLiveJob(definition, handle, input, onProgress);
}

export function gitErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message) return message;
    const type = (error as { type?: unknown }).type;
    if (typeof type === 'string') return type.replaceAll('_', ' ');
  }
  return String(error);
}
