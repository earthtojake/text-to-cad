import {
  DEFAULT_SEARCH_EXCLUDE,
  DEFAULT_TREE_EXCLUDE,
  DEFAULT_WATCHER_EXCLUDE,
} from '@emdash/core/primitives/exclusion-policy/api';
import { z } from 'zod';
import type { FilesSettings } from '@core/primitives/app-settings/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';

const exclusionListSchema = z.array(z.string().trim().min(1)).default([]);
export const HARDCORE_TREE_EXCLUDE = ['__cadgen__', '__pycache__', '.hardcore', '.venv'] as const;
export function withHardcoreTreeExclusions(patterns: readonly string[] | undefined): string[] {
  return [...new Set([...(patterns ?? []), ...HARDCORE_TREE_EXCLUDE])];
}

const treeExclusionListSchema = exclusionListSchema.transform(withHardcoreTreeExclusions);

const filesSettingsSchema = z.object({
  treeExclude: treeExclusionListSchema,
  searchExclude: exclusionListSchema,
  watcherExclude: exclusionListSchema,
});

export const filesSettingsContribution = defineSettingsContribution<'files', FilesSettings>({
  key: 'files',
  schema: filesSettingsSchema,
  defaults: {
    treeExclude: [...DEFAULT_TREE_EXCLUDE, ...HARDCORE_TREE_EXCLUDE],
    searchExclude: [...DEFAULT_SEARCH_EXCLUDE],
    watcherExclude: [...DEFAULT_WATCHER_EXCLUDE],
  },
});
