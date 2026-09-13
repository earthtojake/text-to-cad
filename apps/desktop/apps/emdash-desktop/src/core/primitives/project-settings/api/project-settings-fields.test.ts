import { describe, expect, it } from 'vitest';
import type { ShareableProjectSettings } from './project-settings';
import {
  hasConfiguredShareableProjectSettings,
  tombstonePatchFor,
} from './project-settings-fields';

// The list emdash used to seed into new projects before the defaults were removed
// (workspace-lifecycle-v2); rows created back then still carry it.
const LEGACY_SEEDED_PRESERVE_PATTERNS = [
  '.env',
  '.env.keys',
  '.env.local',
  '.env.*.local',
  '.envrc',
  'docker-compose.override.yml',
];

describe('hasConfiguredShareableProjectSettings', () => {
  it('does not treat legacy seeded preserve patterns as configured settings', () => {
    expect(
      hasConfiguredShareableProjectSettings({
        preservePatterns: [...LEGACY_SEEDED_PRESERVE_PATTERNS],
      })
    ).toBe(false);
  });

  it('does not treat reordered legacy seeded preserve patterns as configured settings', () => {
    expect(
      hasConfiguredShareableProjectSettings({
        preservePatterns: [...LEGACY_SEEDED_PRESERVE_PATTERNS].reverse(),
      })
    ).toBe(false);
  });

  it('treats non-default preserve patterns as configured settings', () => {
    expect(
      hasConfiguredShareableProjectSettings({
        preservePatterns: ['.env*'],
      })
    ).toBe(true);
  });

  it('treats scripts and shell setup as configured settings', () => {
    const settings: ShareableProjectSettings = {
      preservePatterns: [...LEGACY_SEEDED_PRESERVE_PATTERNS],
      shellSetup: 'nvm use',
      scripts: {
        setup: 'npm install',
      },
    };

    expect(hasConfiguredShareableProjectSettings(settings)).toBe(true);
  });
});

describe('tombstonePatchFor', () => {
  it('combines flat share field identities into one nested personal-config patch', () => {
    expect(tombstonePatchFor(['preservePatterns', 'scripts.prepare', 'scripts.run'])).toEqual({
      preservePatterns: null,
      scripts: { prepare: null, run: null },
    });
  });

  it('returns an empty patch when no fields were written', () => {
    expect(tombstonePatchFor([])).toEqual({});
  });
});
