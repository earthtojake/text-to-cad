import { agentConfigContract } from '@emdash/core/runtimes/agent-config/api';
import {
  runtimeResolveErrorAsError,
  type HostRuntimesClient,
  type RuntimeBroker,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';

export { agentConfigContract as skillsConfigRuntimeContract };
export type SkillsHostRuntimesClient = HostRuntimesClient;
export type SkillsRuntimeBroker = Pick<RuntimeBroker, 'client'>;
export type SkillsRuntimeResolveError = RuntimeResolveError;

export function throwSkillsRuntimeResolveError(error: RuntimeResolveError): never {
  throw runtimeResolveErrorAsError(error);
}
