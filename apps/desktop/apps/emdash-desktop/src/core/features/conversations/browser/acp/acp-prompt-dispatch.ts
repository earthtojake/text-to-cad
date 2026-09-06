import type { PromptInput } from '@emdash/core/runtimes/acp/api/client';

export type AcpPromptDispatchResult =
  | { success: true }
  | { success: false; error: string; errorType?: string };

/** Runtime error types that mean the agent session is gone and a reconnect is the remedy. */
export const SESSION_GONE_ERROR_TYPES = new Set(['conversation_not_found', 'invalid_state']);

/**
 * True when a failed send means the agent session is unusable: the runtime no
 * longer knows the conversation, or the adapter still holds a session whose
 * process died underneath it and answers every prompt with an internal error.
 */
export function isSessionGoneError(errorType: string | undefined, message: string): boolean {
  if (errorType && SESSION_GONE_ERROR_TYPES.has(errorType)) return true;
  if (errorType !== 'prompt_failed') return false;
  return /internal error|session (?:has )?(?:ended|closed)|not found|process (?:exited|closed)/i.test(
    message
  );
}

/**
 * Turns a runtime or transport error into a sentence a person can act on.
 * Runtime errors are tagged objects whose `message` is sometimes an identifier
 * (a conversation id for `conversation_not_found`), so the type decides the
 * wording and the message is used only when it reads as prose.
 */
export function describeAcpError(error: unknown): { message: string; type?: string } {
  if (error instanceof Error) return { message: nonEmpty(error.message) ?? GENERIC_MESSAGE };
  if (typeof error === 'string') return { message: nonEmpty(error) ?? GENERIC_MESSAGE };
  if (!error || typeof error !== 'object') return { message: GENERIC_MESSAGE };
  const tagged = error as { type?: unknown; message?: unknown; cause?: { message?: unknown } };
  const type = typeof tagged.type === 'string' ? tagged.type : undefined;
  const message = nonEmpty(tagged.message);
  const cause = nonEmpty(tagged.cause?.message);
  switch (type) {
    case 'conversation_not_found':
      return { type, message: 'The agent session for this chat has ended.' };
    case 'invalid_state':
      return { type, message: message ?? 'The agent session is not ready for this request.' };
    case 'auth_required':
      return { type, message: cause ?? message ?? 'Sign in to the agent to continue.' };
    case 'provider_unsupported':
      return { type, message: 'This agent is not available on this machine.' };
    case 'prompt_failed': {
      const reason = cause ?? message;
      if (!reason || /^internal error$/i.test(reason)) {
        return {
          type,
          message:
            'The agent hit an internal error; the session will be reconnected on the next send.',
        };
      }
      return { type, message: reason };
    }
    default:
      return { ...(type ? { type } : {}), message: cause ?? message ?? GENERIC_MESSAGE };
  }
}

const GENERIC_MESSAGE = 'The agent rejected the request.';

function nonEmpty(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

export interface AcpPromptSender {
  sendPrompt(
    prompt: PromptInput
  ): Promise<{ success: true; data: { queued: boolean } } | { success: false; error: unknown }>;
}

/**
 * A prompt is dispatched only after the ACP runtime explicitly accepts it.
 * Keeping this boundary independent from the composer lets artifact-specific
 * transactions roll back without coupling ordinary chats to CAD state.
 */
export async function dispatchAcpPrompt(
  session: AcpPromptSender | null,
  prompt: PromptInput
): Promise<AcpPromptDispatchResult> {
  if (!session) return { success: false, error: 'The agent session is not connected.' };
  try {
    const result = await session.sendPrompt(prompt);
    if (result.success) return { success: true };
    const described = describeAcpError(result.error);
    return {
      success: false,
      error: described.message,
      ...(described.type ? { errorType: described.type } : {}),
    };
  } catch (error) {
    return { success: false, error: describeAcpError(error).message };
  }
}
