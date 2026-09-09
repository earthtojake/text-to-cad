import type { AcpStartInputWire } from '@emdash/core/runtimes/acp/api/client';
import {
  runtimeResolveErrorAsError,
  type HostRuntimesClient,
  type RuntimeBroker,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';

export type ConversationsAcpStartInput = AcpStartInputWire;
export type ConversationsHostRuntimesClient = HostRuntimesClient;
export type ConversationsRuntimeBroker = Pick<RuntimeBroker, 'client'>;
export type ConversationsRuntimeResolveError = RuntimeResolveError;

export function throwConversationsRuntimeResolveError(error: RuntimeResolveError): never {
  throw runtimeResolveErrorAsError(error);
}
