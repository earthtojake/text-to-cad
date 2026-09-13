/**
 * ChatCommands and ScrollToItemOptions — host-injectable callback contracts.
 *
 * Extracted from index.tsx so that internal modules (chat-view, ChatRoot,
 * CommandsContext) can import these types without creating a circular
 * dependency through the package entry point.
 */

import type { ChatImageAttachment } from './model';

export type ChatViewCommandId = 'chat.scrollToTop' | 'chat.scrollToBottom';

export type ChatViewCommand = {
  id: ChatViewCommandId;
  label: string;
  defaultKeybinding?: string;
};

export const CHAT_VIEW_COMMANDS = [
  {
    id: 'chat.scrollToTop',
    label: 'Scroll to top',
    defaultKeybinding: 'Mod+ArrowUp',
  },
  {
    id: 'chat.scrollToBottom',
    label: 'Scroll to bottom',
    defaultKeybinding: 'Mod+ArrowDown',
  },
] as const satisfies readonly ChatViewCommand[];

/**
 * Typed callbacks that host apps inject to respond to user actions inside the
 * chat transcript. Pass via `createChatView({ commands })` or update later
 * via `view.setCommands(commands)`.
 */
export type ChatCommands = {
  /**
   * Called when the user clicks a file path in a diff header, file-op row,
   * resource-link card, or inline prose link.
   */
  onOpenFile?: (arg: {
    path: string;
    itemId: string;
    source: 'diff' | 'file-op' | 'resource-link' | 'prose-link';
  }) => void;

  /**
   * Called when the user clicks an image attachment or generated-image card.
   */
  onViewImage?: (arg: {
    attachment: ChatImageAttachment;
    itemId: string;
    source: 'user-message' | 'assistant-message' | 'generated-image';
  }) => void;

  /**
   * Resolve an attachment id to a displayable data URL. Used for committed
   * messages and tool results whose transcript stores metadata but not bytes.
   */
  resolveAttachment?: (attachment: { id: string; name: string }) => Promise<string | null>;

  /**
   * Called when the user clicks the stop button on the current user message
   * while the agent is generating.
   */
  onStop?: (arg: { itemId: string }) => void;

  /**
   * Synchronously classify an `href` from a rendered markdown link.
   * Returns `{ kind: 'workspace-file'; path: string }` for workspace files,
   * or `{ kind: 'external' }` to keep the default external-link behavior.
   */
  classifyLink?: (href: string) => { kind: 'workspace-file'; path: string } | { kind: 'external' };

  /**
   * Called when the user clicks a Mermaid diagram block preview.
   */
  onViewMermaid?: (arg: { chart: string; blockId: string; source: 'mermaid-block' }) => void;

  /**
   * Called when the user clicks a resolved @-mention chip in the transcript.
   * `id` is the stable identifier (e.g. a file path); `label` is the raw @-token text.
   */
  onClickMention?: (arg: {
    id: string;
    label: string;
    kind: 'file' | 'issue' | 'symbol' | 'custom';
    itemId: string;
    source: 'prose-mention';
  }) => void;
};

export type ScrollToItemOptions = {
  /** Where to align the row within the viewport. Default: 'start'. */
  align?: 'start' | 'center' | 'end';
  /** Additional pixel offset applied after alignment. Default: 0. */
  offset?: number;
  /** Native scroll behavior. Default: 'auto'. */
  behavior?: ScrollBehavior;
};
