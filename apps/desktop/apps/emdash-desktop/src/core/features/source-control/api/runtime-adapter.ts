import type { HostRef } from '@emdash/core/primitives/host/api';
import { gitContract } from '@emdash/core/runtimes/git/api';
import {
  runtimeResolveErrorAsError,
  type HostRuntimesClient,
  type RuntimeBroker,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';

export const sourceControlGitRuntimeContract = gitContract;

export type SourceControlHostRuntimesClient = HostRuntimesClient;
export type SourceControlRuntimeBroker = Pick<RuntimeBroker, 'client'>;
export type SourceControlRuntimeResolveError = RuntimeResolveError;

export function throwSourceControlRuntimeResolveError(error: RuntimeResolveError): never {
  throw runtimeResolveErrorAsError(error);
}

export type SourceControlWorkspaceIdentity = Readonly<{
  workspaceId: string;
  host: HostRef;
  path: string;
  projectId: string;
}>;

export type SourceControlWorkspaceIdentityResolver = Readonly<{
  resolve(workspaceId: string): Promise<SourceControlWorkspaceIdentity | null>;
  resolveProject(projectId: string): Promise<SourceControlWorkspaceIdentity | null>;
}>;
