import type * as ChatUi from '@emdash/chat-ui';

type ChatUiRuntime = Pick<
  typeof ChatUi,
  'connectSession' | 'createChatContext' | 'createChatState' | 'createChatView' | 'pinTopMode'
>;

let runtime: ChatUiRuntime | undefined;

export function installChatUiRuntime(nextRuntime: ChatUiRuntime): void {
  runtime = nextRuntime;
}

export function getChatUiRuntime(): ChatUiRuntime {
  if (!runtime) {
    throw new Error('Chat UI runtime was not installed during renderer bootstrap');
  }
  return runtime;
}
