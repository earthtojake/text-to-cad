import type { ChatMentionMeta, MentionProvider } from '@emdash/chat-ui';
import { parseIssueMentionToken } from '@core/primitives/issues/api';
import { workspaceFileMentionProvider } from './workspace-file-mention-provider';

class ChatMentionProvider implements MentionProvider {
  resolve(token: string, _uri?: string): ChatMentionMeta | null {
    const issue = parseIssueMentionToken(token);
    if (issue) {
      return {
        id: issue.token,
        label: issue.token,
        name: issue.identifier,
        kind: 'issue',
      };
    }

    return workspaceFileMentionProvider.resolve(token);
  }
}

export const chatMentionProvider = new ChatMentionProvider();
