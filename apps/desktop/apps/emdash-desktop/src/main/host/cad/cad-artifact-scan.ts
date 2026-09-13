import { readdir, stat } from 'node:fs/promises';
import { join, relative, resolve, sep } from 'node:path';
import type { CadArtifactScanResult } from '@core/features/browser/api';

/** Model artifacts the CAD Viewer can show. Recipe sources are edited, not revealed. */
const REVEALABLE_SUFFIXES = ['.step', '.stp', '.stl', '.3mf', '.glb', '.dxf'] as const;

/** Directories that only ever hold runtime, cache, dependency, or build files. */
const SKIPPED_DIRECTORIES = new Set([
  '.git',
  '.hg',
  '.svn',
  'node_modules',
  '.venv',
  'venv',
  '.cad-runtime',
  '__pycache__',
  '__cadgen__',
  '.nx',
  '.cache',
  'dist',
  'build',
  'release',
  'out',
]);
const MAX_DEPTH = 8;
const MAX_ENTRIES = 50_000;

export function isRevealableCadArtifact(path: string): boolean {
  const lower = path.toLowerCase();
  return REVEALABLE_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

/**
 * Model artifacts under a workspace written at or after `sinceMs`, newest
 * last. The desktop polls this while an agent works so a model produced by
 * the agent, or by any subagent writing into the same workspace, can be
 * opened without the file tree having that folder expanded.
 */
export async function listCadArtifacts(input: {
  workspacePath: string;
  sinceMs: number;
}): Promise<CadArtifactScanResult> {
  const root = resolve(input.workspacePath);
  try {
    if (!(await stat(root)).isDirectory()) {
      return { success: false, error: `Workspace is not a directory: ${root}` };
    }
  } catch {
    return { success: false, error: `Workspace does not exist: ${root}` };
  }

  const artifacts: Array<{ path: string; mtimeMs: number }> = [];
  let visited = 0;
  let truncated = false;

  const walk = async (directory: string, depth: number): Promise<void> => {
    if (depth > MAX_DEPTH || truncated) return;
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (++visited > MAX_ENTRIES) {
        truncated = true;
        return;
      }
      const full = join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!SKIPPED_DIRECTORIES.has(entry.name)) await walk(full, depth + 1);
        continue;
      }
      if (!entry.isFile() || !isRevealableCadArtifact(entry.name)) continue;
      let mtimeMs: number;
      try {
        const info = await stat(full);
        if (info.size === 0) continue;
        mtimeMs = info.mtimeMs;
      } catch {
        continue;
      }
      if (mtimeMs < input.sinceMs) continue;
      artifacts.push({ path: relative(root, full).split(sep).join('/'), mtimeMs });
    }
  };
  await walk(root, 0);

  artifacts.sort(
    (left, right) => left.mtimeMs - right.mtimeMs || left.path.localeCompare(right.path)
  );
  return { success: true, artifacts, truncated };
}
