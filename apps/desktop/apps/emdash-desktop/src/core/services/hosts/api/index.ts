import type { WorkspaceServerTarget } from './targets';

export {
  hostAvailabilityStateSchema,
  hostReadySchema,
  type ExplicitRecoveryCause,
  type HostAvailability,
  type HostAvailabilityState,
  type HostPreparingPhase,
  type HostReady,
  type RecoveryCause,
} from './availability';
export type {
  LocalWorkspaceServerTarget,
  SshWorkspaceServerTarget,
  WorkspaceServerTarget,
} from './targets';

export {
  hostsContract,
  hostsDomain,
  hostServerStateSchema,
  hostServerStatusSchema,
  isServerUsable,
  type HostServerRuntime,
  type HostServerState,
  type HostServerStatus,
} from './contract';

export type HostInvalidation = {
  connectionId: string;
  reason: 'reconnect-failed' | 'machine-mutation' | 'connection-lost';
  target?: WorkspaceServerTarget;
  error?: unknown;
};

export type MachineMutationEvents = {
  on(name: 'machine:mutated', handler: (event: { connectionId: string }) => void): () => void;
};
