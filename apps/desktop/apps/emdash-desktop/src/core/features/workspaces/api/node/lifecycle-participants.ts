import { sshConnectionIdOf, type HostRef } from '@emdash/core/primitives/host/api';
import type { HostAbsolutePath } from '@emdash/core/primitives/path/api';
import { log } from '@emdash/shared/logger';
import type { WorkspaceIdentity } from '@core/features/workspaces/api/node/workspace-identity-service';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';

export type WorkspaceLifecycleContext = Readonly<{
  identity: WorkspaceIdentity;
}>;

export type WorkspaceLifecycleParticipant = Readonly<{
  id: string;
  activate?(context: WorkspaceLifecycleContext): void | Promise<void>;
  deactivate?(context: WorkspaceLifecycleContext): void | Promise<void>;
}>;

export function createWorkspaceLifecycleParticipants(dependencies: {
  registerFileSearchRoot(path: HostAbsolutePath, host: HostRef): Promise<void> | void;
}): readonly WorkspaceLifecycleParticipant[] {
  return [
    {
      id: 'file-search',
      activate: ({ identity }) =>
        dependencies.registerFileSearchRoot(
          hostFileRefFromNativePath(identity.path, sshConnectionIdOf(identity.host)).path,
          identity.host
        ),
    },
  ];
}

export async function activateWorkspaceParticipants(
  participants: readonly WorkspaceLifecycleParticipant[],
  identity: WorkspaceIdentity
): Promise<void> {
  await runParticipants(participants, 'activate', identity);
}

export async function deactivateWorkspaceParticipants(
  participants: readonly WorkspaceLifecycleParticipant[],
  identity: WorkspaceIdentity
): Promise<void> {
  await runParticipants(participants, 'deactivate', identity);
}

async function runParticipants(
  participants: readonly WorkspaceLifecycleParticipant[],
  phase: 'activate' | 'deactivate',
  identity: WorkspaceIdentity
): Promise<void> {
  const results = await Promise.allSettled(
    participants.map((participant) => Promise.resolve(participant[phase]?.({ identity })))
  );
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') return;
    log.warn('Workspace lifecycle participant failed', {
      participant: participants[index]?.id,
      phase,
      workspaceId: identity.workspaceId,
      error: result.reason,
    });
  });
}
