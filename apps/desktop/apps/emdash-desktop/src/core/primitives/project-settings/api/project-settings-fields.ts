import {
  SHAREABLE_PROJECT_SETTINGS_WRITE_FIELDS,
  type ShareableProjectSettings,
  type ShareableProjectSettingsWriteField,
} from './project-settings';

export type ShareablePersonalConfigTombstonePatch = {
  preservePatterns?: null;
  scripts?: {
    prepare?: null;
    setup?: null;
    run?: null;
    teardown?: null;
  };
};

type ShareableFieldAccessor = {
  path: string[];
  get(settings: ShareableProjectSettings): unknown;
  set(settings: ShareableProjectSettings, value: unknown): void;
  clear(settings: ShareableProjectSettings): void;
  displayValue(settings: ShareableProjectSettings): string | null;
};

function ensureScripts(
  settings: ShareableProjectSettings
): NonNullable<ShareableProjectSettings['scripts']> {
  settings.scripts ??= {};
  return settings.scripts;
}

function displayText(value: string | undefined): string | null {
  return value?.trim() ? value : null;
}

function compactScripts(settings: ShareableProjectSettings): void {
  if (settings.scripts && Object.values(settings.scripts).every((value) => value === undefined)) {
    delete settings.scripts;
  }
}

function normalizePatterns(patterns: string[] | undefined): string[] {
  return patterns?.map((pattern) => pattern.trim()).filter(Boolean) ?? [];
}

/**
 * The preserve defaults emdash used to seed into new projects (removed in
 * workspace-lifecycle-v2). Rows seeded before the removal still carry them, and a
 * project whose only shareable setting is that stale seed should not read as
 * deliberately configured.
 */
const LEGACY_SEEDED_PRESERVE_PATTERNS = [
  '.env',
  '.env.keys',
  '.env.local',
  '.env.*.local',
  '.envrc',
  'docker-compose.override.yml',
] as const;

export function hasDefaultPreservePatterns(settings: ShareableProjectSettings): boolean {
  const patterns = normalizePatterns(settings.preservePatterns);
  if (patterns.length !== LEGACY_SEEDED_PRESERVE_PATTERNS.length) return false;
  const patternSet = new Set(patterns);
  return LEGACY_SEEDED_PRESERVE_PATTERNS.every((pattern) => patternSet.has(pattern));
}

export function hasConfiguredShareableProjectSettings(settings: ShareableProjectSettings): boolean {
  return SHAREABLE_PROJECT_SETTINGS_WRITE_FIELDS.some((field) => {
    if (field === 'preservePatterns') {
      const patterns = normalizePatterns(settings.preservePatterns);
      return patterns.length > 0 && !hasDefaultPreservePatterns(settings);
    }
    return SHAREABLE_FIELD_ACCESSORS[field].displayValue(settings) !== null;
  });
}

export const SHAREABLE_FIELD_ACCESSORS = {
  preservePatterns: {
    path: ['preservePatterns'],
    get: (settings) => settings.preservePatterns,
    set: (settings, value) => {
      settings.preservePatterns = value as string[] | undefined;
    },
    clear: (settings) => {
      delete settings.preservePatterns;
    },
    displayValue: (settings) => {
      const value = normalizePatterns(settings.preservePatterns);
      return value?.length ? value.join('\n') : null;
    },
  },
  'scripts.prepare': {
    path: ['scripts', 'prepare'],
    get: (settings) => settings.scripts?.prepare,
    set: (settings, value) => {
      ensureScripts(settings).prepare = value as string | undefined;
    },
    clear: (settings) => {
      if (settings.scripts) delete settings.scripts.prepare;
      compactScripts(settings);
    },
    displayValue: (settings) => displayText(settings.scripts?.prepare),
  },
  'scripts.setup': {
    path: ['scripts', 'setup'],
    get: (settings) => settings.scripts?.setup,
    set: (settings, value) => {
      ensureScripts(settings).setup = value as string | undefined;
    },
    clear: (settings) => {
      if (settings.scripts) delete settings.scripts.setup;
      compactScripts(settings);
    },
    displayValue: (settings) => displayText(settings.scripts?.setup),
  },
  'scripts.run': {
    path: ['scripts', 'run'],
    get: (settings) => settings.scripts?.run,
    set: (settings, value) => {
      ensureScripts(settings).run = value as string | undefined;
    },
    clear: (settings) => {
      if (settings.scripts) delete settings.scripts.run;
      compactScripts(settings);
    },
    displayValue: (settings) => displayText(settings.scripts?.run),
  },
  'scripts.teardown': {
    path: ['scripts', 'teardown'],
    get: (settings) => settings.scripts?.teardown,
    set: (settings, value) => {
      ensureScripts(settings).teardown = value as string | undefined;
    },
    clear: (settings) => {
      if (settings.scripts) delete settings.scripts.teardown;
      compactScripts(settings);
    },
    displayValue: (settings) => displayText(settings.scripts?.teardown),
  },
} satisfies Record<ShareableProjectSettingsWriteField, ShareableFieldAccessor>;

export const SHAREABLE_FIELD_TOMBSTONES = {
  preservePatterns: { preservePatterns: null },
  'scripts.prepare': { scripts: { prepare: null } },
  'scripts.setup': { scripts: { setup: null } },
  'scripts.run': { scripts: { run: null } },
  'scripts.teardown': { scripts: { teardown: null } },
} satisfies Record<ShareableProjectSettingsWriteField, ShareablePersonalConfigTombstonePatch>;

export function tombstonePatchFor(
  fields: ShareableProjectSettingsWriteField[]
): ShareablePersonalConfigTombstonePatch {
  const patch: ShareablePersonalConfigTombstonePatch = {};
  for (const field of fields) {
    const tombstone = SHAREABLE_FIELD_TOMBSTONES[field];
    if ('preservePatterns' in tombstone) patch.preservePatterns = null;
    if ('scripts' in tombstone) patch.scripts = { ...patch.scripts, ...tombstone.scripts };
  }
  return patch;
}

export function clearShareableProjectSettingsFields<T extends ShareableProjectSettings>(
  settings: T,
  fields: ShareableProjectSettingsWriteField[]
): T {
  const next: ShareableProjectSettings = {
    ...settings,
    preservePatterns: settings.preservePatterns ? [...settings.preservePatterns] : undefined,
    scripts: settings.scripts ? { ...settings.scripts } : undefined,
  };

  for (const field of fields) {
    SHAREABLE_FIELD_ACCESSORS[field].clear(next);
  }

  return next as T;
}

export function mergeShareableProjectSettings(
  ...sources: ShareableProjectSettings[]
): ShareableProjectSettings {
  const next: ShareableProjectSettings = {};

  for (const source of sources) {
    for (const field of SHAREABLE_PROJECT_SETTINGS_WRITE_FIELDS) {
      const value = SHAREABLE_FIELD_ACCESSORS[field].get(source);
      if (value !== undefined) {
        SHAREABLE_FIELD_ACCESSORS[field].set(next, value);
      }
    }
  }

  return next;
}
