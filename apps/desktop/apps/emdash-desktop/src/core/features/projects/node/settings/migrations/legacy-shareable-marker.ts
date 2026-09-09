import type { ShareableProjectSettings } from '@core/primitives/project-settings/api';
import { compactUndefined, parseJsonObject } from '../project-settings-json';

const LEGACY_SHAREABLE_CONFIG_MIGRATED_AT = '__legacyShareableConfigMigratedAt';

function readLegacyShareableConfigMigratedAt(raw: string): string | undefined {
  try {
    const parsed = parseJsonObject(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return undefined;
    const value = (parsed as Record<string, unknown>)[LEGACY_SHAREABLE_CONFIG_MIGRATED_AT];
    return typeof value === 'string' && value.trim() ? value : undefined;
  } catch {
    return undefined;
  }
}

export function hasLegacyShareableConfigMigrated(raw: string): boolean {
  return readLegacyShareableConfigMigratedAt(raw) !== undefined;
}

export function serializeShareableProjectSettings(
  settings: ShareableProjectSettings,
  options: {
    previousRaw?: string;
    markLegacyShareableConfigMigrated?: boolean;
  } = {}
): string {
  const next = compactUndefined(settings) as Record<string, unknown>;
  const migratedAt = options.markLegacyShareableConfigMigrated
    ? new Date().toISOString()
    : options.previousRaw
      ? readLegacyShareableConfigMigratedAt(options.previousRaw)
      : undefined;

  if (migratedAt) {
    next[LEGACY_SHAREABLE_CONFIG_MIGRATED_AT] = migratedAt;
  }

  return JSON.stringify(next);
}
