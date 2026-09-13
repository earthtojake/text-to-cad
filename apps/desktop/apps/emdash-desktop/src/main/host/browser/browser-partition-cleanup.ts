import { readdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { app } from 'electron';
import { BROWSER_PARTITION_PREFIX } from '@core/primitives/browser/api';
import { log } from '@main/lib/logger';

const PERSIST_PREFIX = 'persist:';
const LEGACY_DIR_PREFIX = `${BROWSER_PARTITION_PREFIX.slice(PERSIST_PREFIX.length)}-`;
const PROFILE_DIR_PREFIX = `${BROWSER_PARTITION_PREFIX.slice(PERSIST_PREFIX.length)}-profile`;
const ISOLATED_DIR_PREFIX = `${BROWSER_PARTITION_PREFIX.slice(PERSIST_PREFIX.length)}-isolated-`;

/**
 * Browsers used to get one persistent partition per browser tab. Keep named
 * profile and isolated-task partitions, but remove old unused tab partitions so
 * stale cookies and caches do not accumulate in userData/Partitions.
 */
export async function cleanupLegacyBrowserPartitions(): Promise<void> {
  const partitionsDir = join(app.getPath('userData'), 'Partitions');
  let entries;
  try {
    entries = await readdir(partitionsDir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (!entry.name.startsWith(LEGACY_DIR_PREFIX)) continue;
    if (entry.name.startsWith(PROFILE_DIR_PREFIX) || entry.name.startsWith(ISOLATED_DIR_PREFIX)) {
      continue;
    }
    try {
      await rm(join(partitionsDir, entry.name), { recursive: true, force: true });
    } catch (error) {
      log.warn('Failed to remove legacy browser partition', { partition: entry.name, error });
    }
  }
}
