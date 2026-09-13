import {
  Archive,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpToLine,
  ChevronDown,
  ChevronUp,
  Columns2,
  Copy,
  ExternalLink,
  FileDiff,
  Files,
  FolderOpen,
  FolderPlus,
  GitPullRequest,
  Globe,
  MessageSquare,
  MessageSquarePlus,
  MessageSquareShare,
  Palette,
  PanelBottom,
  PanelRight,
  Pin,
  RefreshCw,
  Search,
  Settings,
  SquarePlus,
  SquareTerminal,
  Terminal,
  TextCursorInput,
  type LucideIcon,
} from 'lucide-react';

/**
 * Maps the string iconKey tokens defined in the commands primitive to their
 * LucideIcon components. The shared layer stays free of renderer imports — it
 * stores only the string key, and the renderer resolves it here.
 */
export const COMMAND_ICONS = {
  settings: Settings,
  'folder-plus': FolderPlus,
  'folder-open': FolderOpen,
  'square-plus': SquarePlus,
  'arrow-left': ArrowLeft,
  'arrow-right': ArrowRight,
  'message-square-plus': MessageSquarePlus,
  'columns-2': Columns2,
  'file-diff': FileDiff,
  'message-square': MessageSquare,
  'message-square-share': MessageSquareShare,
  palette: Palette,
  files: Files,
  terminal: Terminal,
  'panel-bottom': PanelBottom,
  'panel-right': PanelRight,
  'square-terminal': SquareTerminal,
  globe: Globe,
  copy: Copy,
  'refresh-cw': RefreshCw,
  search: Search,
  'text-cursor-input': TextCursorInput,
  'external-link': ExternalLink,
  'git-pull-request': GitPullRequest,
  'arrow-down-to-line': ArrowDownToLine,
  'arrow-up-to-line': ArrowUpToLine,
  pin: Pin,
  archive: Archive,
  'chevron-down': ChevronDown,
  'chevron-up': ChevronUp,
} satisfies Record<string, LucideIcon>;

export type CommandIconKey = keyof typeof COMMAND_ICONS;

export function getCommandIcon(iconKey: string | undefined): LucideIcon | undefined {
  if (!iconKey) return undefined;
  return (COMMAND_ICONS as Record<string, LucideIcon>)[iconKey];
}
