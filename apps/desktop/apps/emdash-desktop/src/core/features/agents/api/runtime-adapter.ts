import type { DependencyId } from '@emdash/core/primitives/host-dependencies/api';
import { agentConfigContract } from '@emdash/core/runtimes/agent-config/api';
import {
  runtimeResolveErrorAsError,
  type HostRuntimesClient,
  type RuntimeBroker,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';

export { agentConfigContract as agentsConfigRuntimeContract };
export type AgentsDependencyId = DependencyId;
export type AgentsHostRuntimesClient = HostRuntimesClient;
export type AgentsRuntimeBroker = Pick<RuntimeBroker, 'client'>;
export type AgentsRuntimeResolveError = RuntimeResolveError;

export function throwAgentsRuntimeResolveError(error: RuntimeResolveError): never {
  throw runtimeResolveErrorAsError(error);
}
