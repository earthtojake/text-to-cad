/**
 * CommandProvider — synchronous metadata resolver for /-command tokens.
 *
 * When chat-ui parses a message, any `/token` that appears at a word boundary
 * can be resolved through a CommandProvider.  On a successful resolve the token
 * is emitted as an `InlineMention` run with `tone: 'command'`, which Prose.tsx
 * renders as a styled chip.
 *
 * Because the provider lives on the global ChatContext it receives the
 * conversation `uri` (set via `createChatState` options) so it can scope
 * resolution to the correct conversation when multiple conversations share the
 * same provider instance.
 *
 * The provider MUST be synchronous and stable for the lifetime of the ChatRoot
 * mount.  Changing the provider requires a remount (same contract as
 * `mentionProvider`).  When no provider is supplied all `/token` spans are left
 * as plain InlineText (no regression).
 */

/** Resolved metadata for a single slash-command token. */
export interface ChatCommandMeta {
  /** The command name as advertised by the agent (without the leading slash). */
  name: string;
  /** Optional human-readable description shown in the transcript tooltip or chip. */
  description?: string;
}

/**
 * Injectable provider that resolves a raw slash-command token (the text after
 * the leading `/`) to rich metadata for display purposes.
 *
 * Must be synchronous — called during the markdown parse phase which runs
 * inline within virtualizer measurement.
 */
export interface CommandProvider {
  /**
   * Resolve the token string (everything after `/`) to metadata.
   *
   * @param token - The word following `/` in the command span.
   * @param uri   - Conversation URI supplied to `createChatState`.  Use this to
   *                scope resolution when the same provider handles multiple
   *                conversations.  Undefined when no uri was provided.
   *
   * Return null if the token is not a known command (treated as plain text).
   */
  resolve(token: string, uri?: string): ChatCommandMeta | null;
}
