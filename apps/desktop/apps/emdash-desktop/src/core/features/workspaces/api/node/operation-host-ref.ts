import {
  hostRef,
  hostRefFromParts,
  LOCAL_HOST_REF,
  type HostRef,
} from '@emdash/core/primitives/host/api';

type WorkspaceHostColumns = {
  location?: 'local' | 'remote' | null;
  sshConnectionId?: string | null;
};

/**
 * Resolves operation routing from the most authoritative available owner:
 * the task workspace first, then the project's repository workspace.
 */
export function operationHostRef(input: {
  workspace?: WorkspaceHostColumns;
  repository?: WorkspaceHostColumns;
}): HostRef {
  for (const owner of [input.workspace, input.repository]) {
    if (owner?.location) return hostRefFromParts(owner.location, owner.sshConnectionId ?? null);
    if (owner?.sshConnectionId) return hostRef('remote', owner.sshConnectionId);
  }
  return LOCAL_HOST_REF;
}
