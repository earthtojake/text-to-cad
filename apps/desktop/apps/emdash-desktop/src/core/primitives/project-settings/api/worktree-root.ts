/**
 * Portable worktree-root path helpers (spec: github-git-settings §6).
 *
 * The worktree-root chain resolves per-project override → per-host default →
 * built-in root. Every consumer — node placement, the renderer settings page,
 * and the create-task destination preview — must normalize configured roots
 * through these helpers so preview and execution cannot diverge. Pure and
 * browser-safe: no node imports.
 */

/**
 * The worktree-root layers below the per-project override, plus the host
 * home directory needed to expand `~` the same way execution does. Produced
 * node-side (host settings + host home) and shipped to the renderer over the
 * Wire so both sides feed identical inputs to the resolver.
 */
export type WorktreeRootContext = {
  /** Per-host default worktree root from the host-settings runtime, if configured. */
  hostWorktreeRoot: string | null;
  /** Built-in worktree root for the host (`<home>/hardcore/worktrees`). */
  builtInWorktreeRoot: string;
  /** The host's home directory, for `~` expansion of configured roots. */
  homeDirectory: string;
};

/** The built-in (last) worktree-root layer: `<home>/hardcore/worktrees`. */
export function builtInWorktreeRootFor(homeDirectory: string): string {
  const separator = pathSeparatorFor(homeDirectory);
  const trimmed = homeDirectory.replace(trailingSeparators(separator), '');
  return `${trimmed}${separator}hardcore${separator}worktrees`;
}

/**
 * Normalizes a configured worktree root the way placement consumes it: trim,
 * expand `~` against the host home, require an absolute path, resolve `.`/`..`
 * segments. Returns null when the value is unusable (relative, `~` with no
 * home, empty) — read-path validation matches execution, which never checks
 * existence (git creates missing directories).
 */
export function normalizeWorktreeRootPath(
  configuredRoot: string,
  homeDirectory: string
): string | null {
  const trimmed = configuredRoot.trim();
  if (!trimmed) return null;

  const homeSeparator = pathSeparatorFor(homeDirectory);
  const home = homeDirectory.trim().replace(trailingSeparators(homeSeparator), '');
  let expanded = trimmed;
  if (trimmed === '~') {
    expanded = home;
  } else if (trimmed.startsWith('~/') || trimmed.startsWith('~\\')) {
    if (!home) return null;
    expanded = `${home}${homeSeparator}${trimmed.slice(2)}`;
  }

  const separator = pathSeparatorFor(expanded);
  if (!isAbsolutePath(expanded, separator)) return null;
  return normalizeAbsolutePath(expanded, separator);
}

function pathSeparatorFor(absolutePath: string): '/' | '\\' {
  return /^[a-zA-Z]:[\\/]/u.test(absolutePath) || absolutePath.startsWith('\\\\') ? '\\' : '/';
}

function trailingSeparators(separator: '/' | '\\'): RegExp {
  return separator === '\\' ? /[\\/]+$/u : /\/+$/u;
}

function isAbsolutePath(candidate: string, separator: '/' | '\\'): boolean {
  if (separator === '\\') {
    return /^[a-zA-Z]:[\\/]/u.test(candidate) || candidate.startsWith('\\\\');
  }
  return candidate.startsWith('/');
}

/**
 * Pure equivalent of node's `path.normalize` for absolute paths: collapses
 * separators and resolves `.`/`..` without escaping the root.
 */
function normalizeAbsolutePath(absolutePath: string, separator: '/' | '\\'): string {
  let root: string;
  let rest: string;
  if (separator === '\\') {
    if (absolutePath.startsWith('\\\\')) {
      // UNC: keep `\\server\share` as the root.
      const segments = absolutePath.slice(2).split(/[\\/]+/u);
      root = `\\\\${segments.slice(0, 2).join('\\')}\\`;
      rest = segments.slice(2).join('\\');
    } else {
      root = `${absolutePath.slice(0, 2)}\\`;
      rest = absolutePath.slice(3);
    }
  } else {
    root = '/';
    rest = absolutePath.slice(1);
  }

  const splitPattern = separator === '\\' ? /[\\/]+/u : /\/+/u;
  const resolved: string[] = [];
  for (const segment of rest.split(splitPattern)) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      resolved.pop();
      continue;
    }
    resolved.push(segment);
  }
  return `${root}${resolved.join(separator)}` || root;
}
