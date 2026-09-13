import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import { settingsPageContributions } from '@core/manifests/browser/settings-page-contributions';

export type SettingsSearchEntry = {
  /** Stable kebab-case id; for SettingRow-backed settings it equals slugifySettingLabel(label). */
  id: string;
  /** The visible label of the setting in the UI. */
  label: string;
  tab: Exclude<SettingsPageTab, 'docs'>;
  description?: string;
  /** Extra terms (synonyms, provider names) that should also match this entry. */
  keywords?: string[];
};

/** Derives a stable search-entry id from a visible label. */
export function slugifySettingLabel(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export const SETTINGS_SEARCH_INDEX: SettingsSearchEntry[] = [
  // General
  {
    id: 'version',
    label: 'Version',
    tab: 'general',
    description: 'App version and updates.',
    keywords: ['update', 'upgrade', 'restart', 'release'],
  },
  {
    id: 'privacy-telemetry',
    label: 'Privacy & Telemetry',
    tab: 'general',
    description: 'Help improve Hardcore by sending anonymous usage data.',
    keywords: ['analytics', 'posthog', 'usage data', 'tracking'],
  },
  {
    id: 'auto-generate-task-names',
    label: 'Auto-generate task names',
    tab: 'general',
    description: 'Automatically suggests a task name when creating a new task.',
  },
  {
    id: 'auto-approve-by-default',
    label: 'Auto-approve by default',
    tab: 'general',
    description: 'Skip permission prompts for supported agents when creating new tasks.',
    keywords: ['permissions', 'yolo'],
  },
  {
    id: 'auto-trust-worktree-directories',
    label: 'Auto-trust worktree directories',
    tab: 'general',
    description: 'Skip the folder trust prompt in supported CLIs for new tasks.',
    keywords: ['trust', 'claude code', 'copilot'],
  },
  {
    id: 'create-branch-and-worktree-by-default',
    label: 'Create branch and worktree by default',
    tab: 'general',
    description: 'Start new From Branch tasks in a dedicated task branch and worktree.',
    keywords: ['git'],
  },
  {
    id: 'preserve-task-name-capitalization',
    label: 'Preserve task name capitalization',
    tab: 'general',
    description: 'Keep uppercase letters in generated and manually entered task names.',
    keywords: ['lowercase', 'uppercase'],
  },
  {
    id: 'include-issue-context-by-default',
    label: 'Include issue context by default',
    tab: 'general',
    description: 'Add the selected issue to the initial agent prompt.',
  },
  {
    id: 'enable-tmux',
    label: 'Enable tmux',
    tab: 'general',
    description: 'Run agent sessions and terminals in tmux sessions by default.',
    keywords: ['multiplexer'],
  },
  {
    id: 'notifications',
    label: 'Notifications',
    tab: 'general',
    description: 'Get notified when agents need your attention.',
    keywords: ['alerts'],
  },
  {
    id: 'sound',
    label: 'Sound',
    tab: 'general',
    description: 'Play audio cues for agent events.',
    keywords: ['audio', 'notifications'],
  },
  {
    id: 'custom-sound',
    label: 'Custom sound',
    tab: 'general',
    description: 'Use an audio file instead of the built-in cue.',
    keywords: ['audio', 'notifications'],
  },
  {
    id: 'sound-timing',
    label: 'Sound timing',
    tab: 'general',
    description: 'When to play sounds.',
    keywords: ['audio', 'notifications', 'unfocused'],
  },
  {
    id: 'os-notifications',
    label: 'OS notifications',
    tab: 'general',
    description: 'Show system banners when agents need attention or finish.',
    keywords: ['banner', 'system'],
  },
  // Agents
  {
    id: 'agents',
    label: 'Agents',
    tab: 'clis-models',
    description: 'Manage installed CLI agents and their configuration.',
    keywords: ['claude', 'codex', 'copilot', 'cursor', 'gemini', 'cli'],
  },
  {
    id: 'mcp',
    label: 'MCP',
    tab: 'mcp',
    description: 'Manage local MCP servers available to agents.',
    keywords: ['model context protocol', 'servers', 'tools'],
  },
  {
    id: 'skills',
    label: 'Skills',
    tab: 'skills',
    description: 'Manage reusable local agent skills.',
    keywords: ['skill modules', 'agents'],
  },

  // Connections
  {
    id: 'ssh-connections',
    label: 'Machines',
    tab: 'connections',
    description: 'Reusable remote hosts for SSH projects.',
    keywords: ['remote', 'host'],
  },

  // Repository
  {
    id: 'branch-prefix',
    label: 'Branch prefix',
    tab: 'repository',
    description: 'Leave empty to create branches without a prefix.',
    keywords: ['git'],
  },
  {
    id: 'random-branch-suffix',
    label: 'Random branch suffix',
    tab: 'repository',
    description: 'Add a random suffix to branch names.',
    keywords: ['git'],
  },
  {
    id: 'auto-push-on-create',
    label: 'Auto-push on create',
    tab: 'repository',
    description: 'Push the new branch to the selected project remote and set upstream.',
    keywords: ['git', 'remote', 'upstream'],
  },
  // Local workspaces
  {
    id: 'task-worktree-storage',
    label: 'Workspaces',
    tab: 'workspaces-local',
    description: 'Review task worktree usage and remove stale task worktrees.',
    keywords: ['disk', 'cleanup', 'storage', 'worktrees'],
  },

  // Conversations
  {
    id: 'conversations',
    label: 'Conversations',
    tab: 'conversations',
    description: 'Every conversation record on this machine, including unlinked ones.',
    keywords: ['chats', 'sessions', 'orphaned', 'history', 'agents'],
  },

  // Prompts
  {
    id: 'prompts',
    label: 'Prompts',
    tab: 'prompts',
    description: 'Manage reusable prompts for tasks and conversations.',
    keywords: ['prompt library', 'snippets'],
  },

  // System
  {
    id: 'system',
    label: 'System',
    tab: 'system',
    description: 'Review local resource utilization and system dependencies.',
    keywords: ['cpu', 'memory', 'disk', 'dependencies', 'git', 'tmux'],
  },

  // Interface
  {
    id: 'color-mode',
    label: 'Color mode',
    tab: 'interface',
    description: 'Choose how Hardcore looks.',
    keywords: ['theme', 'dark mode', 'light mode', 'appearance', 'system'],
  },
  {
    id: 'default-terminal-shell',
    label: 'Default terminal shell',
    tab: 'interface',
    description: 'Used for new local terminals.',
    keywords: ['bash', 'zsh', 'fish'],
  },
  {
    id: 'terminal-font',
    label: 'Terminal font',
    tab: 'interface',
    description: 'Choose the font family for the terminal.',
    keywords: ['font family', 'menlo'],
  },
  {
    id: 'terminal-font-size',
    label: 'Terminal font size',
    tab: 'interface',
    description: 'Adjust the font size used by terminal sessions and CLI agents.',
    keywords: ['text size', 'zoom'],
  },
  {
    id: 'auto-copy-selected-text',
    label: 'Auto-copy selected text',
    tab: 'interface',
    description: 'Automatically copy text to clipboard when you select it in the terminal.',
    keywords: ['clipboard', 'terminal'],
  },
  {
    id: 'use-option-as-meta-key',
    label: 'Use Option as Meta key',
    tab: 'interface',
    description: 'Treat the Option key as the Meta key in the terminal.',
    keywords: ['macos', 'alt', 'terminal'],
  },
  {
    id: 'left-sidebar-line-changes',
    label: 'Left sidebar line changes',
    tab: 'interface',
    description: 'Show added and removed line counts for tasks in the left sidebar.',
    keywords: ['diff'],
  },
  {
    id: 'left-sidebar-pr-status',
    label: 'Left sidebar PR status',
    tab: 'interface',
    description: 'Show GitHub PR merge and status icons for tasks in the left sidebar.',
    keywords: ['pull request'],
  },
  {
    id: 'left-sidebar-timestamps',
    label: 'Left sidebar timestamps',
    tab: 'interface',
    description: 'Show the relative task timestamp in the left sidebar.',
    keywords: ['time'],
  },
  {
    id: 'resource-monitor',
    label: 'Resource monitor',
    tab: 'interface',
    description: 'Track CPU and memory usage for running agents.',
    keywords: ['cpu', 'memory', 'performance'],
  },
  {
    id: 'context-bar',
    label: 'Context bar',
    tab: 'interface',
    description: 'Hide the on-screen context trigger.',
  },
  {
    id: 'keyboard-shortcuts',
    label: 'Keyboard shortcuts',
    tab: 'interface',
    description: 'Rebind, reset, or remove app keyboard shortcuts.',
    keywords: ['hotkeys', 'keybindings', 'rebind'],
  },
  {
    id: 'open-in-tools',
    label: 'Tools',
    tab: 'interface',
    description: 'Show or hide detected "Open in" apps in menus.',
    keywords: ['open in', 'editor', 'hidden tools'],
  },
  // Browser
  {
    id: 'default-browser-profile',
    label: 'Default browser profile',
    tab: 'browser',
    description: 'New browser tabs open with this profile.',
    keywords: ['isolated'],
  },
  {
    id: 'disable-cors-for-localhost',
    label: 'Disable CORS for localhost',
    tab: 'browser',
    description:
      'Allow localhost pages in Hardcore browser tabs to call APIs without CORS headers.',
    keywords: ['cross-origin'],
  },
  {
    id: 'browser-profiles',
    label: 'Browser profiles',
    tab: 'browser',
    description: 'Each profile keeps its own cookies and logins, shared across tasks.',
    keywords: ['cookies', 'logins'],
  },
  {
    id: 'browsing-data',
    label: 'Browsing data',
    tab: 'browser',
    description: 'Clear cookies, cached files, and site data from the in-app browser.',
    keywords: ['cookies', 'cache', 'clear', 'site data'],
  },
];

function normalizeQuery(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function entryMatchesTokens(entry: SettingsSearchEntry, tokens: string[]): boolean {
  const haystack = [entry.label, entry.description ?? '', ...(entry.keywords ?? [])]
    .join(' ')
    .toLowerCase();
  return tokens.every((token) => haystack.includes(token));
}

/** All index entries matching the query. An empty/whitespace query matches nothing. */
export function searchSettings(
  query: string,
  index: SettingsSearchEntry[] = SETTINGS_SEARCH_INDEX
): SettingsSearchEntry[] {
  const tokens = normalizeQuery(query);
  if (tokens.length === 0) return [];
  return index.filter((entry) => entryMatchesTokens(entry, tokens));
}

/** Tabs containing at least one match, in sidebar order. */
export function matchedTabsForQuery(
  query: string,
  index: SettingsSearchEntry[] = SETTINGS_SEARCH_INDEX
): SettingsPageTab[] {
  const matchedTabs = new Set(searchSettings(query, index).map((entry) => entry.tab));
  return settingsPageContributions
    .filter((page) => matchedTabs.has(page.id))
    .map((page) => page.id);
}
