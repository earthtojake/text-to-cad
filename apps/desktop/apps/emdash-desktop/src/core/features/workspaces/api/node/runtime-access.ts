import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import type { WorkspaceIdentity } from '@core/features/workspaces/api/node/workspace-identity-service';
import {
  throwWorkspacesRuntimeResolveError,
  type WorkspacesHostRuntimesClient,
  type WorkspacesRuntimeResolveError as RuntimeResolveError,
} from '@core/features/workspaces/api/runtime-adapter';
import { filesClientScope, type FilesClientScope } from '@core/services/runtime-broker/node/files';

export type WorkspaceRuntimeAccess = Readonly<{
  identity: WorkspaceIdentity;
  client: WorkspacesHostRuntimesClient;
  files: FilesClientScope;
}>;

export type WorkspaceRuntimeIdentityResolver = {
  resolve(workspaceId: string): Promise<WorkspaceIdentity | null>;
};

export async function acquireWorkspaceRuntime(
  runtimes: RuntimeBroker,
  workspaceIdentity: WorkspaceRuntimeIdentityResolver,
  workspaceId: string
): Promise<WorkspaceRuntimeAccess | null> {
  const result = await tryAcquireWorkspaceRuntime(runtimes, workspaceIdentity, workspaceId);
  if (!result.success) throwWorkspacesRuntimeResolveError(result.error);
  return result.data;
}

export async function tryAcquireWorkspaceRuntime(
  runtimes: RuntimeBroker,
  workspaceIdentity: WorkspaceRuntimeIdentityResolver,
  workspaceId: string
): Promise<Result<WorkspaceRuntimeAccess | null, RuntimeResolveError>> {
  const identity = await workspaceIdentity.resolve(workspaceId);
  if (!identity) return ok(null);

  const runtime = await runtimes.client(identity.host);
  if (!runtime.success) return err(runtime.error);
  return ok({
    identity,
    client: runtime.data,
    files: filesClientScope(runtime.data.files, identity.path),
  });
}

export async function withWorkspaceRuntime<T>(
  runtimes: RuntimeBroker,
  workspaceIdentity: WorkspaceRuntimeIdentityResolver,
  workspaceId: string,
  work: (access: WorkspaceRuntimeAccess) => Promise<T>
): Promise<T | null> {
  const access = await acquireWorkspaceRuntime(runtimes, workspaceIdentity, workspaceId);
  if (!access) return null;
  return await work(access);
}
