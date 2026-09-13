import type { AppDb } from '@core/services/app-db/node/db';
import { projectSettings as projectSettingsTable } from '@core/services/app-db/node/schema';
import { parseJsonObject } from './project-settings-json';

function readPinnedGithubAccountId(raw: string): string | undefined {
  try {
    const parsed = parseJsonObject(raw) as Record<string, unknown>;
    // New stored model: { githubAccount: { kind: 'account', accountId } }.
    const account = parsed.githubAccount;
    if (account && typeof account === 'object') {
      const { kind, accountId } = account as Record<string, unknown>;
      if (kind === 'account' && typeof accountId === 'string') {
        return normalizeAccountId(accountId);
      }
      return undefined;
    }
    // Legacy rows not yet lazily migrated: { githubAccountId: string }.
    const value = parsed.githubAccountId;
    if (typeof value !== 'string') return undefined;
    return normalizeAccountId(value);
  } catch {
    return undefined;
  }
}

function normalizeAccountId(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

export async function countProjectsUsingGithubAccount(
  db: AppDb,
  accountId: string
): Promise<number> {
  const targetAccountId = accountId.trim();
  if (!targetAccountId) return 0;

  const rows = db
    .select({ baseProjectSettingsJson: projectSettingsTable.baseProjectSettingsJson })
    .from(projectSettingsTable)
    .all();

  let count = 0;
  for (const row of rows) {
    if (readPinnedGithubAccountId(row.baseProjectSettingsJson) === targetAccountId) {
      count += 1;
    }
  }
  return count;
}
