import { describe, expect, it } from 'vitest';
import { settingsPageContributions } from '@core/manifests/browser/settings-page-contributions';
import {
  matchedTabsForQuery,
  searchSettings,
  SETTINGS_SEARCH_INDEX,
  slugifySettingLabel,
  type SettingsSearchEntry,
} from './settings-search';

const FIXTURE_INDEX: SettingsSearchEntry[] = [
  { id: 'color-mode', label: 'Color mode', tab: 'interface', keywords: ['dark mode', 'theme'] },
  { id: 'terminal-font-size', label: 'Terminal font size', tab: 'interface' },
  {
    id: 'enable-tmux',
    label: 'Enable tmux',
    tab: 'general',
    description: 'Run agent sessions and terminals in tmux sessions by default.',
  },
  { id: 'branch-prefix', label: 'Branch prefix', tab: 'repository', keywords: ['git'] },
];

describe('slugifySettingLabel', () => {
  it('kebab-cases labels', () => {
    expect(slugifySettingLabel('Terminal font size')).toBe('terminal-font-size');
  });

  it('strips punctuation and collapses separators', () => {
    expect(slugifySettingLabel('Privacy & Telemetry')).toBe('privacy-telemetry');
    expect(slugifySettingLabel('  Use Option as Meta key ')).toBe('use-option-as-meta-key');
  });
});

describe('searchSettings', () => {
  it('returns nothing for an empty or whitespace query', () => {
    expect(searchSettings('', FIXTURE_INDEX)).toEqual([]);
    expect(searchSettings('   ', FIXTURE_INDEX)).toEqual([]);
  });

  it('matches labels case-insensitively', () => {
    const results = searchSettings('TERMINAL FONT', FIXTURE_INDEX);
    expect(results.map((entry) => entry.id)).toEqual(['terminal-font-size']);
  });

  it('matches partial substrings', () => {
    expect(searchSettings('fon', FIXTURE_INDEX).map((e) => e.id)).toEqual(['terminal-font-size']);
  });

  it('matches descriptions', () => {
    expect(searchSettings('sessions', FIXTURE_INDEX).map((e) => e.id)).toEqual(['enable-tmux']);
  });

  it('matches keywords', () => {
    expect(searchSettings('dark', FIXTURE_INDEX).map((e) => e.id)).toEqual(['color-mode']);
    expect(searchSettings('git', FIXTURE_INDEX).map((e) => e.id)).toEqual(['branch-prefix']);
  });

  it('requires every token to match (AND across tokens)', () => {
    expect(searchSettings('terminal size', FIXTURE_INDEX).map((e) => e.id)).toEqual([
      'terminal-font-size',
    ]);
    expect(searchSettings('terminal banana', FIXTURE_INDEX)).toEqual([]);
  });

  it('allows tokens to match across label, description, and keywords', () => {
    expect(searchSettings('tmux agent', FIXTURE_INDEX).map((e) => e.id)).toEqual(['enable-tmux']);
  });

  it('returns nothing when nothing matches', () => {
    expect(searchSettings('zzz-no-such-setting', FIXTURE_INDEX)).toEqual([]);
  });

  it('ignores extra whitespace between tokens', () => {
    expect(searchSettings('  terminal   font  ', FIXTURE_INDEX).map((e) => e.id)).toEqual([
      'terminal-font-size',
    ]);
  });
});

describe('matchedTabsForQuery', () => {
  it('returns only tabs containing matches, in sidebar order', () => {
    expect(matchedTabsForQuery('terminal', FIXTURE_INDEX)).toEqual(['general', 'interface']);
  });

  it('returns a single tab when only one matches', () => {
    expect(matchedTabsForQuery('branch', FIXTURE_INDEX)).toEqual(['repository']);
  });

  it('returns no tabs for a no-result query', () => {
    expect(matchedTabsForQuery('zzz-no-such-setting', FIXTURE_INDEX)).toEqual([]);
  });

  it('returns no tabs for an empty query', () => {
    expect(matchedTabsForQuery('', FIXTURE_INDEX)).toEqual([]);
  });
});

describe('SETTINGS_SEARCH_INDEX integrity', () => {
  it('has unique ids', () => {
    const ids = SETTINGS_SEARCH_INDEX.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('has kebab-case ids and non-empty labels', () => {
    for (const entry of SETTINGS_SEARCH_INDEX) {
      expect(entry.id).toMatch(/^[a-z0-9]+(-[a-z0-9.]+)*$/);
      expect(entry.label.trim().length).toBeGreaterThan(0);
    }
  });

  it('only references known tabs', () => {
    const tabIds = new Set<string>(settingsPageContributions.map((page) => page.id));
    for (const entry of SETTINGS_SEARCH_INDEX) {
      expect(tabIds.has(entry.tab)).toBe(true);
    }
  });

  it('covers every settings tab with at least one entry', () => {
    const coveredTabs = new Set(SETTINGS_SEARCH_INDEX.map((entry) => entry.tab));
    for (const page of settingsPageContributions) {
      expect(coveredTabs.has(page.id)).toBe(true);
    }
  });

  it('routes well-known queries to the expected tabs', () => {
    expect(matchedTabsForQuery('telemetry')).toEqual(['general']);
    expect(matchedTabsForQuery('jira')).toEqual([]);
    expect(matchedTabsForQuery('ssh')).toContain('connections');
    expect(matchedTabsForQuery('dark mode')).toEqual(['interface']);
    expect(matchedTabsForQuery('font')).toContain('interface');
    expect(matchedTabsForQuery('worktree storage')).toEqual(['workspaces-local']);
    expect(matchedTabsForQuery('cookies')).toEqual(['browser']);
  });

  it('resolves SettingRow auto-derived ids: slugified labels match entry ids for row-backed settings', () => {
    // These entries correspond to SettingRow titles rendered as plain strings,
    // so their id must equal slugifySettingLabel(label) for stable search targets.
    const rowBackedIds = [
      'privacy-telemetry',
      'auto-generate-task-names',
      'enable-tmux',
      'terminal-font-size',
      'notifications',
      'os-notifications',
      'disable-cors-for-localhost',
    ];
    for (const id of rowBackedIds) {
      const entry = SETTINGS_SEARCH_INDEX.find((candidate) => candidate.id === id);
      expect(entry, `missing index entry ${id}`).toBeDefined();
      expect(slugifySettingLabel(entry!.label)).toBe(id);
    }
  });
});
