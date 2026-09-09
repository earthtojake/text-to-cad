const CHAT_TAB_KINDS = new Set(['acp-chat', 'conversation']);

/**
 * The task itself owns its one chat, so that pane never needs a second visible
 * label. Everything else keeps real tab chrome: filenames, status, switching,
 * rename, and close are meaningful for artifacts and legacy multi-tab layouts.
 */
export function shouldShowTaskPaneTabBar(kinds: readonly string[]): boolean {
  if (kinds.length === 0) return false;
  if (kinds.length === 1 && CHAT_TAB_KINDS.has(kinds[0]!)) return false;
  return true;
}
