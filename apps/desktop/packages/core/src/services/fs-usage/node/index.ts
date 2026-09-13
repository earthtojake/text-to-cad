import type { Stats } from 'node:fs';
import { lstat, readdir } from 'node:fs/promises';
import path from 'node:path';

export type PathUsageError = {
  path: string;
  message: string;
};

export type PathUsage = {
  path: string;
  type: 'file' | 'directory';
  apparentBytes: number;
  diskBytes: number;
  exclusiveDiskBytes: number;
  artifactBytes: number;
  errors: PathUsageError[];
};

type EntryUsage = {
  apparentBytes: number;
  diskBytes: number;
  inodeKey: string | null;
  linkCount: number;
  isDirectory: boolean;
  isArtifact: boolean;
};

type ScanState = {
  root: string;
  displayPath: string;
  artifactRoots: string[];
  entries: EntryUsage[];
  errors: PathUsageError[];
};

export async function measureAbsolutePathUsage(
  absolutePath: string,
  displayPath: string,
  options: { artifactRoots?: string[] } = {}
): Promise<PathUsage> {
  const root = path.resolve(absolutePath);
  const rootStats = await lstat(root);

  if (!rootStats.isDirectory()) {
    const bytes = diskBytes(rootStats);
    return {
      path: displayPath,
      type: 'file',
      apparentBytes: rootStats.size,
      diskBytes: bytes,
      exclusiveDiskBytes: rootStats.nlink > 1 ? 0 : bytes,
      artifactBytes: 0,
      errors: [],
    };
  }

  const state: ScanState = {
    root,
    displayPath,
    artifactRoots: normalizeArtifactRoots(options.artifactRoots ?? []),
    entries: [],
    errors: [],
  };
  await scanPath(state, root);
  return {
    path: displayPath,
    type: 'directory',
    ...aggregateEntries(state.entries),
    errors: state.errors,
  };
}

async function scanPath(state: ScanState, currentPath: string): Promise<void> {
  const relative = displayRelativePath(state, currentPath);
  let stats: Stats;
  try {
    stats = await lstat(currentPath);
  } catch (error) {
    state.errors.push({ path: relative, message: errorMessage(error) });
    return;
  }

  const isDirectory = stats.isDirectory();
  state.entries.push({
    apparentBytes: stats.size,
    diskBytes: diskBytes(stats),
    inodeKey: inodeKey(stats),
    linkCount: stats.nlink,
    isDirectory,
    isArtifact: isArtifactPath(state, relative),
  });
  if (!isDirectory) return;

  let children;
  try {
    children = await readdir(currentPath, { withFileTypes: true });
  } catch (error) {
    state.errors.push({ path: relative, message: errorMessage(error) });
    return;
  }
  for (const child of children) {
    await scanPath(state, path.join(currentPath, child.name));
  }
}

function aggregateEntries(entries: EntryUsage[]) {
  let apparentBytes = 0;
  let diskBytesTotal = 0;
  let exclusiveDiskBytes = 0;
  let artifactBytes = 0;
  const linked = new Map<string, { count: number; linkCount: number; diskBytes: number }>();
  const linkedArtifacts = new Map<
    string,
    { count: number; linkCount: number; diskBytes: number }
  >();

  for (const entry of entries) {
    apparentBytes += entry.apparentBytes;
    if (entry.isDirectory || !entry.inodeKey || entry.linkCount <= 1) {
      diskBytesTotal += entry.diskBytes;
      exclusiveDiskBytes += entry.diskBytes;
      if (entry.isArtifact) artifactBytes += entry.diskBytes;
      continue;
    }
    const existing = linked.get(entry.inodeKey);
    if (existing) existing.count += 1;
    else {
      linked.set(entry.inodeKey, {
        count: 1,
        linkCount: entry.linkCount,
        diskBytes: entry.diskBytes,
      });
    }
    if (entry.isArtifact) {
      const existingArtifact = linkedArtifacts.get(entry.inodeKey);
      if (existingArtifact) existingArtifact.count += 1;
      else {
        linkedArtifacts.set(entry.inodeKey, {
          count: 1,
          linkCount: entry.linkCount,
          diskBytes: entry.diskBytes,
        });
      }
    }
  }

  for (const group of linked.values()) {
    diskBytesTotal += group.diskBytes;
    if (group.linkCount <= group.count) exclusiveDiskBytes += group.diskBytes;
  }
  for (const group of linkedArtifacts.values()) {
    if (group.linkCount <= group.count) artifactBytes += group.diskBytes;
  }
  return { apparentBytes, diskBytes: diskBytesTotal, exclusiveDiskBytes, artifactBytes };
}

function displayRelativePath(state: ScanState, currentPath: string): string {
  const relative = path.relative(state.root, currentPath);
  if (!relative) return state.displayPath;
  const suffix = relative.split(path.sep).join('/');
  return state.displayPath ? `${state.displayPath}/${suffix}` : suffix;
}

function diskBytes(stats: Stats): number {
  return stats.blocks > 0 ? stats.blocks * 512 : stats.size;
}

function normalizeArtifactRoots(roots: string[]): string[] {
  return Array.from(
    new Set(
      roots
        .map((root) => root.trim().replace(/\\/gu, '/').replace(/\/+$/u, ''))
        .filter((root) => root && root !== '.' && root !== '..')
    )
  );
}

function isArtifactPath(state: ScanState, relativePath: string): boolean {
  if (!relativePath) return false;
  const normalized = relativePath.replace(/\\/gu, '/');
  return state.artifactRoots.some(
    (root) => normalized === root || normalized.startsWith(`${root}/`)
  );
}

function inodeKey(stats: Stats): string | null {
  return stats.ino === 0 ? null : `${stats.dev}:${stats.ino}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
