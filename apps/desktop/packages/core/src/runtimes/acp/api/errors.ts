/**
 * Tagged error union for AcpRuntime public API failures, plus the wire error schemas the
 * contract declares per verb (convention 2: closed `type`-discriminated unions built from
 * shared variant objects).
 */

import type { BaseError, SerializedError } from '@emdash/shared';
import { fail } from '@emdash/shared';
import { z } from 'zod';

/** Provider does not support the ACP transport. */
export type ProviderUnsupportedError = BaseError<'provider_unsupported'>;

/** No conversation with the given id is tracked in the runtime. */
export type ConversationNotFoundError = BaseError<'conversation_not_found'>;

/**
 * A command was issued but the current lifecycle state does not allow it,
 * e.g. Prompt while already working.
 */
export type InvalidStateError = BaseError<'invalid_state'>;

/** Spawning the agent process failed. */
export type SpawnFailedError = BaseError<'spawn_failed', SerializedError>;

/** The ACP initialize handshake failed. */
export type InitializeFailedError = BaseError<'initialize_failed', SerializedError>;

/** The agent's newSession call failed. */
export type NewSessionFailedError = BaseError<'new_session_failed', SerializedError>;

/** The agent requires authentication before a session can be started. */
export type AuthRequiredError = BaseError<'auth_required', SerializedError>;

/** A prompt() call to the agent failed. */
export type PromptFailedError = BaseError<'prompt_failed', SerializedError>;

/** A cancel() call to the agent failed. */
export type CancelFailedError = BaseError<'cancel_failed', SerializedError>;

/** A setSessionConfigOption() call to the agent failed. */
export type SetConfigFailedError = BaseError<'set_config_failed', SerializedError>;

/** A setSessionMode() call to the agent failed. */
export type SetModeFailedError = BaseError<'set_mode_failed', SerializedError>;

export type AcpRuntimeError =
  | ProviderUnsupportedError
  | ConversationNotFoundError
  | InvalidStateError
  | SpawnFailedError
  | InitializeFailedError
  | NewSessionFailedError
  | AuthRequiredError
  | PromptFailedError
  | CancelFailedError
  | SetConfigFailedError
  | SetModeFailedError;

export type AcpStartError =
  | ProviderUnsupportedError
  | AuthRequiredError
  | SpawnFailedError
  | InitializeFailedError
  | NewSessionFailedError
  | InvalidStateError;
export type AcpResumeError = AcpStartError;
export type AcpKillError = never;
export type AcpSendPromptError = ConversationNotFoundError | InvalidStateError | PromptFailedError;
export type AcpQueueMutationError = ConversationNotFoundError | InvalidStateError;
export type AcpEditQueuedPromptError = AcpQueueMutationError;
export type AcpDeleteQueuedPromptError = AcpQueueMutationError;
export type AcpChangeQueuePromptOrderError = AcpQueueMutationError;
export type AcpResolvePermissionError = AcpQueueMutationError;
export type AcpSetPromptDraftError = ConversationNotFoundError;
export type AcpCancelTurnError = InvalidStateError | CancelFailedError;
export type AcpSetModelOptionError =
  | ConversationNotFoundError
  | InvalidStateError
  | SetConfigFailedError;
export type AcpSetModeOptionError =
  | ConversationNotFoundError
  | InvalidStateError
  | SetModeFailedError;
export type AcpExportTranscriptError = ConversationNotFoundError;
export type AcpExportRawLogError = ConversationNotFoundError;
export type AcpAttachmentError = InvalidStateError;
export type AcpGetHistoryError = never;

export const acpErr = {
  providerUnsupported: (providerId: string) =>
    fail('provider_unsupported', { message: `Provider '${providerId}' does not support ACP` }),

  conversationNotFound: (conversationId: string) =>
    fail('conversation_not_found', { message: conversationId }),

  invalidState: (message: string) => fail('invalid_state', { message }),

  spawnFailed: (cause: SerializedError) => fail('spawn_failed', { cause }),

  initializeFailed: (cause: SerializedError) => fail('initialize_failed', { cause }),

  newSessionFailed: (cause: SerializedError) => fail('new_session_failed', { cause }),

  authRequired: (cause: SerializedError) => fail('auth_required', { cause }),

  promptFailed: (cause: SerializedError) => fail('prompt_failed', { cause }),

  cancelFailed: (cause: SerializedError) => fail('cancel_failed', { cause }),

  setConfigFailed: (cause: SerializedError) => fail('set_config_failed', { cause }),

  setModeFailed: (cause: SerializedError) => fail('set_mode_failed', { cause }),
} as const;

export const serializedErrorSchema = z.object({
  name: z.string(),
  message: z.string(),
  stack: z.string().optional(),
});

const plainTagErrorSchema = <T extends string>(type: T) =>
  z.object({ type: z.literal(type), message: z.string().optional() });

const failedErrorSchema = <T extends string>(type: T) =>
  z.object({
    type: z.literal(type),
    message: z.string().optional(),
    cause: serializedErrorSchema.optional(),
  });

export const providerUnsupportedErrorSchema = plainTagErrorSchema('provider_unsupported');
export const conversationNotFoundErrorSchema = plainTagErrorSchema('conversation_not_found');
export const invalidStateErrorSchema = plainTagErrorSchema('invalid_state');
export const spawnFailedErrorSchema = failedErrorSchema('spawn_failed');
export const initializeFailedErrorSchema = failedErrorSchema('initialize_failed');
export const newSessionFailedErrorSchema = failedErrorSchema('new_session_failed');
export const authRequiredErrorSchema = failedErrorSchema('auth_required');
export const promptFailedErrorSchema = failedErrorSchema('prompt_failed');
export const cancelFailedErrorSchema = failedErrorSchema('cancel_failed');
export const setConfigFailedErrorSchema = failedErrorSchema('set_config_failed');
export const setModeFailedErrorSchema = failedErrorSchema('set_mode_failed');

export const acpStartErrorSchema = z.discriminatedUnion('type', [
  providerUnsupportedErrorSchema,
  authRequiredErrorSchema,
  spawnFailedErrorSchema,
  initializeFailedErrorSchema,
  newSessionFailedErrorSchema,
  invalidStateErrorSchema,
]);
export const acpResumeErrorSchema = acpStartErrorSchema;
export const acpKillErrorSchema = z.never();
export const acpSendPromptErrorSchema = z.discriminatedUnion('type', [
  conversationNotFoundErrorSchema,
  invalidStateErrorSchema,
  promptFailedErrorSchema,
]);
export const acpQueueMutationErrorSchema = z.discriminatedUnion('type', [
  conversationNotFoundErrorSchema,
  invalidStateErrorSchema,
]);
export const acpEditQueuedPromptErrorSchema = acpQueueMutationErrorSchema;
export const acpDeleteQueuedPromptErrorSchema = acpQueueMutationErrorSchema;
export const acpChangeQueuePromptOrderErrorSchema = acpQueueMutationErrorSchema;
export const acpResolvePermissionErrorSchema = acpQueueMutationErrorSchema;
export const acpSetPromptDraftErrorSchema = conversationNotFoundErrorSchema;
export const acpCancelTurnErrorSchema = z.discriminatedUnion('type', [
  invalidStateErrorSchema,
  cancelFailedErrorSchema,
]);
export const acpSetModelOptionErrorSchema = z.discriminatedUnion('type', [
  conversationNotFoundErrorSchema,
  invalidStateErrorSchema,
  setConfigFailedErrorSchema,
]);
export const acpSetModeOptionErrorSchema = z.discriminatedUnion('type', [
  conversationNotFoundErrorSchema,
  invalidStateErrorSchema,
  setModeFailedErrorSchema,
]);
export const acpExportTranscriptErrorSchema = conversationNotFoundErrorSchema;
export const acpExportRawLogErrorSchema = conversationNotFoundErrorSchema;
export const acpAttachmentErrorSchema = invalidStateErrorSchema;
export const acpGetHistoryErrorSchema = z.never();

export const acpRuntimeErrorSchema = z.discriminatedUnion('type', [
  providerUnsupportedErrorSchema,
  conversationNotFoundErrorSchema,
  invalidStateErrorSchema,
  spawnFailedErrorSchema,
  initializeFailedErrorSchema,
  newSessionFailedErrorSchema,
  authRequiredErrorSchema,
  promptFailedErrorSchema,
  cancelFailedErrorSchema,
  setConfigFailedErrorSchema,
  setModeFailedErrorSchema,
]);
