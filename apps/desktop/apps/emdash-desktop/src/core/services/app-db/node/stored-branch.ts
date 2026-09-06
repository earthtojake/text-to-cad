import type { GitBranchRef } from '@core/primitives/git/api';

/**
 * The persisted form of a Branch stored in SQLite. The column is plain text so
 * app code, not Drizzle, owns compatibility with historical storage formats.
 */
export type StoredBranch = string & { readonly __storedBranch: unique symbol };

export function toStoredBranch(branch: GitBranchRef | null | undefined): StoredBranch | null {
  return branch ? (JSON.stringify(branch) as StoredBranch) : null;
}

export function fromStoredBranch(
  raw: string | GitBranchRef | null | undefined
): GitBranchRef | undefined {
  if (!raw) return undefined;
  if (typeof raw !== 'string') return decodeStoredBranchValue(raw);

  try {
    const parsed = JSON.parse(raw) as unknown;
    const decoded = decodeStoredBranchValue(parsed);
    if (decoded) return decoded;

    if (parsed === null) return undefined;

    // A historical plain branch name can itself be valid JSON, e.g. "123" or "true".
    return isStructuredJson(raw) ? undefined : { type: 'local', branch: raw };
  } catch {
    return { type: 'local', branch: raw };
  }
}

function decodeStoredBranchValue(value: unknown): GitBranchRef | undefined {
  if (typeof value === 'string') {
    return value ? { type: 'local', branch: value } : undefined;
  }

  if (!isRecord(value) || typeof value.branch !== 'string' || value.branch.length === 0) {
    return undefined;
  }

  if (value.type === 'local') {
    const remote = decodeRemote(value.remote);
    return remote
      ? { type: 'local', branch: value.branch, remote }
      : { type: 'local', branch: value.branch };
  }

  if (value.type === 'remote') {
    const remote = decodeRemote(value.remote);
    return remote ? { type: 'remote', branch: value.branch, remote } : undefined;
  }

  return undefined;
}

function decodeRemote(value: unknown): GitBranchRef['remote'] | undefined {
  if (!isRecord(value)) return undefined;
  if (typeof value.name !== 'string' || typeof value.url !== 'string') return undefined;
  return { name: value.name, url: value.url };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isStructuredJson(raw: string): boolean {
  const first = raw.trimStart()[0];
  return first === '{' || first === '[';
}
