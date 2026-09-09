import type { HostRef } from '@emdash/core/primitives/host/api';
import {
  terminalsContract as terminalsRuntimeContract,
  type TerminalError,
  type TerminalKey,
} from '@emdash/core/runtimes/terminals/api';
import {
  isRuntimeResolveError,
  runtimeResolveErrorAsError,
  type HostRuntimesClient,
  type RuntimeBroker,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';

export { terminalsRuntimeContract };

export type TerminalsHostRuntimesClient = HostRuntimesClient;
export type TerminalsRuntimeBroker = Pick<RuntimeBroker, 'client'>;
export type TerminalsRuntimeKey = TerminalKey;
export type TerminalsRuntimeError = TerminalError;
export type TerminalsRuntimeResolveError = RuntimeResolveError;

export function isTerminalsRuntimeResolveError(
  value: unknown
): value is TerminalsRuntimeResolveError {
  return isRuntimeResolveError(value);
}

export function throwTerminalsRuntimeResolveError(error: RuntimeResolveError): never {
  throw runtimeResolveErrorAsError(error);
}

export type TerminalsWorkspaceIdentity = Readonly<{
  workspaceId: string;
  host: HostRef;
  path: string;
  projectId: string;
}>;

export type TerminalsWorkspaceIdentityResolver = Readonly<{
  resolve(workspaceId: string): Promise<TerminalsWorkspaceIdentity | null>;
}>;
