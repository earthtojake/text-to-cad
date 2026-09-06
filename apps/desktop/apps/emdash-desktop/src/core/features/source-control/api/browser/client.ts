import type { PortableRelativePath } from '@emdash/core/primitives/path/api';
import type { CheckoutHeadState } from '@emdash/core/runtimes/git/api';
import { createScope } from '@emdash/shared/concurrency';
import type { ContractClient } from '@emdash/wire/rpc';
import { observe, pin, remote } from '@emdash/wire/state';
import { getProjectsWireClient } from '@core/features/projects/api/browser/client';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import type {
  InitializeRepositoryResult,
  InspectProjectPathParams,
  ProjectPathInspection,
} from '@core/primitives/projects/api';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { sourceControlContract, sourceControlDomain } from '../contract';

export type SourceControlClient = ContractClient<typeof sourceControlContract>;

export function getSourceControlClient(): Promise<SourceControlClient> {
  return domainClient<SourceControlClient>(sourceControlDomain, sourceControlContract);
}

export async function inspectProjectPath(
  input: InspectProjectPathParams
): Promise<ProjectPathInspection> {
  return (await getProjectsWireClient()).inspectProjectPath(input);
}

export async function initializeProjectRepository(
  projectId: string
): Promise<InitializeRepositoryResult> {
  return (await getProjectsWireClient()).initializeRepository({ projectId });
}

export function repositorySelector(projectId: string): { projectId: string } {
  return { projectId };
}

export function checkoutSelector(workspaceId: string): { workspaceId: string } {
  return { workspaceId };
}

export function gitFilePath(relativePath: string): PortableRelativePath {
  return portablePath(relativePath.replaceAll('\\', '/'));
}

export async function readCheckoutHead(workspaceId: string): Promise<CheckoutHeadState> {
  const client = await getSourceControlClient();
  const scope = createScope({ label: `read-checkout-head:${workspaceId}` });
  const checkoutRemote = remote(sourceControlContract.checkout.model, client.checkout.model, {
    scope,
    lingerMs: 0,
  });
  try {
    const model = checkoutRemote(checkoutSelector(workspaceId));
    pin(scope, [model.states.head]);
    return await new Promise((resolve, reject) => {
      observe(
        model.states.head,
        (current) => {
          if (current.status === 'error') {
            reject(current.error);
            return;
          }
          if (current.value) resolve(current.value);
        },
        { scope }
      );
    });
  } finally {
    await checkoutRemote.dispose();
    await scope.dispose();
  }
}
