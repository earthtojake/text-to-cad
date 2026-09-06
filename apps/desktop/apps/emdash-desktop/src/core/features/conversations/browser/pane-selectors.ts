/**
 * Pane selectors for the conversations domain.
 *
 * These helpers let conversation UI read conversation-tab state from a generic
 * PaneStore without the engine having to know about ConversationTabResource.
 */
import type { PaneStore } from '@core/primitives/workbench-shell/browser/tabs/pane-store';
import type { ConversationTabResource } from './conversation-tab-resource';

export function activeConversationId(pane: PaneStore): string | undefined {
  const resource = pane.activeResourceOfKind<ConversationTabResource>('conversation');
  return resource?.store?.data?.id;
}

export function activeConversationResource(pane: PaneStore): ConversationTabResource | undefined {
  return pane.activeResourceOfKind<ConversationTabResource>('conversation');
}

/** @deprecated Use activeConversationResource */
export const activeConversation = (pane: PaneStore, _conversations?: unknown) =>
  activeConversationResource(pane)?.store;
