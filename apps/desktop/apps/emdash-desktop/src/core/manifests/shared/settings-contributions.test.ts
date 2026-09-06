import { describe, expect, it } from 'vitest';
import { appSettingsSchemaContributions } from './settings-contributions';

describe('settings contribution manifest', () => {
  it('registers every contribution under its declared key', () => {
    for (const [key, contribution] of Object.entries(appSettingsSchemaContributions)) {
      expect(contribution.key).toBe(key);
    }
  });
});
