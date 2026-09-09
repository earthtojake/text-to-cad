import type { CatalogIndex, CatalogSkill } from '@emdash/core/primitives/skills/api';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { SkillsList } from '@core/features/skills/browser/components/SkillsList';
import type { UseSkillsResult } from '@core/features/skills/browser/components/useSkills';
import { modalStore } from '@core/primitives/modals/react/modal-store';
import { ThemeProvider } from '@core/primitives/theme/browser/theme-provider';

const skill: CatalogSkill = {
  id: 'test-skill',
  displayName: 'Test Skill',
  description: 'A skill used to exercise the details modal.',
  source: 'local',
  frontmatter: {
    name: 'test-skill',
    description: 'A skill used to exercise the details modal.',
  },
  installed: true,
  localPath: '/tmp/test-skill',
};

const catalog: CatalogIndex = {
  version: 1,
  lastUpdated: new Date(0).toISOString(),
  skills: [skill],
};

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('SkillsList details modal', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    modalStore.dismissAll();
    for (const entry of [...modalStore.stack]) modalStore.removeEntry(entry.key);
    await act(async () => root.unmount());
    host.remove();
  });

  it('opens skill details through the catalog modal stack', async () => {
    const skills = {
      catalog,
      isLoading: false,
      isRefreshing: false,
      searchQuery: '',
      filteredSkills: [skill],
      installedSkills: [skill],
      recommendedSkills: [],
      skillShSearchSkills: [],
      isSearchingSkillSh: false,
      refresh: vi.fn(),
      install: vi.fn(async () => true),
      uninstall: vi.fn(async () => true),
    } as unknown as UseSkillsResult;

    await act(async () => {
      root.render(
        <ThemeProvider theme="emlight" onThemeChange={vi.fn()}>
          <SkillsList skills={skills} />
        </ThemeProvider>
      );
    });

    const card = host.querySelector<HTMLElement>('[role="button"]');
    expect(card).not.toBeNull();

    await act(async () => card!.click());

    expect(modalStore.activeModalId).toBe('skillDetailModal');
    expect(modalStore.activeModalArgs?.skill).toEqual(skill);
  });
});
