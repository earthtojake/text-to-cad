import type { ChatMentionMeta, MentionProvider } from '@emdash/chat-ui';
import { resolveFileIconClass } from '@emdash/ui/react/primitives';

/**
 * Synchronous MentionProvider that resolves @-tokens to file mention metadata.
 *
 * Uses a path-heuristic: any token containing a '/' or '.' is treated as a
 * relative file path and resolved as a 'file' mention. Agents virtually always
 * @-mention files via paths like `src/auth/jwt.ts`, so false positives are rare.
 *
 * `iconClass` is populated via `resolveFileIconClass` so transcript pills show
 * the same language-specific devicons as the composer mention pills.
 *
 * This is a singleton wired into the shared ChatContext at bootstrap so all ACP
 * conversations benefit from file mention pills without per-conversation setup.
 */
class WorkspaceFileMentionProvider implements MentionProvider {
  resolve(token: string): ChatMentionMeta | null {
    if (!token.includes('/') && !token.includes('.')) return null;
    const name = token.split('/').pop() ?? token;
    const iconClass = resolveFileIconClass(name) ?? undefined;
    return { id: token, label: token, name, kind: 'file', iconClass };
  }
}

export const workspaceFileMentionProvider = new WorkspaceFileMentionProvider();
