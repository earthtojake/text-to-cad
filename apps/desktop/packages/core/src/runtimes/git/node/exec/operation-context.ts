import { gitCredentialOperationEnv } from '#primitives/git-credentials/api';
import type { GitOperationCredentials, GitTransferProgress } from '#runtimes/git/api';

export type GitOperationContext<P = GitTransferProgress> = Readonly<{
  signal?: AbortSignal;
  onProgress?: (progress: P) => void;
  /**
   * Per-invocation env overlay for this one git command (e.g. an
   * operation-scoped emdash credential helper). Never carries token material.
   */
  env?: NodeJS.ProcessEnv;
}>;

/**
 * Maps a job input's optional credential context to the env overlay for the
 * underlying git invocation (spec: github-git-settings §4).
 */
export function credentialOperationEnv(
  credentials: GitOperationCredentials | undefined
): NodeJS.ProcessEnv | undefined {
  if (!credentials) return undefined;
  return gitCredentialOperationEnv(
    { port: credentials.port, nonce: credentials.nonce },
    credentials.host
  );
}
