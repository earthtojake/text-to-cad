import { Minimatch } from 'minimatch';
import type { PortableRelativePath } from '#primitives/path/api';

// Structural declaration keeps this browser-reachable api file free of node
// ambient types; the typeof guard below already handles environments without it.
declare const process: { platform?: string } | undefined;

export const DEFAULT_SEARCH_EXCLUDE = [
  '.git',
  '.svn',
  '.hg',
  'dist',
  'build',
  '.next',
  '.nuxt',
  'out',
  '.turbo',
  'coverage',
  '.nyc_output',
  '.cache',
  '.parcel-cache',
  'tmp',
  'temp',
  '.DS_Store',
  'Thumbs.db',
  '.vscode-test',
  '.idea',
  '__pycache__',
  '.pytest_cache',
  'venv',
  '.venv',
  'target',
  '.terraform',
  '.serverless',
  '.checkouts',
  'checkouts',
  '.conductor',
  '.cursor',
  '.claude',
  '.devin',
  '.amp',
  '.codex',
  '.aider',
  '.continue',
  '.cody',
  '.windsurf',
  'worktrees',
  '.worktrees',
  '.emdash',
  'node_modules',
] as const;

export const DEFAULT_TREE_EXCLUDE = ['.git', '.DS_Store', 'Thumbs.db'] as const;

export const DEFAULT_WATCHER_EXCLUDE = [
  '**/.git/objects/**',
  '**/.git/subtree-cache/**',
  '**/node_modules/**',
  '**/.hg/store/**',
] as const;

export interface ExclusionMatcher {
  excludes(path: PortableRelativePath): boolean;
  ripgrepGlobs(): readonly string[];
  watchIgnoreGlobs(): readonly string[];
}

export type ExclusionPolicyOptions = Readonly<{
  caseSensitive?: boolean;
}>;

type GlobPattern = Readonly<{
  pattern: string;
  matcher: Minimatch;
}>;

const GLOB_MAGIC_PATTERN = /[*?[\]{}()!+@]/u;

export class ExclusionPolicy implements ExclusionMatcher {
  private readonly segments: readonly string[];
  private readonly excludedSegments: ReadonlySet<string>;
  private readonly globPatterns: readonly GlobPattern[];
  private readonly normalize: (value: string) => string;

  constructor(patterns: readonly string[], options: ExclusionPolicyOptions = {}) {
    // Default to case-sensitive on all platforms except Windows; guard for renderer environments
    // where `process` may not be available.
    const caseSensitive =
      options.caseSensitive ??
      (typeof process === 'undefined' ? true : process.platform !== 'win32');
    this.normalize = caseSensitive ? (value) => value : (value) => value.toLocaleLowerCase('en-US');

    const segments: string[] = [];
    const globPatterns: GlobPattern[] = [];
    for (const pattern of normalizeExclusionPatterns(patterns)) {
      if (isBareSegmentPattern(pattern)) {
        segments.push(pattern);
      } else {
        globPatterns.push({
          pattern,
          matcher: new Minimatch(pattern, {
            dot: true,
            nocase: !caseSensitive,
            nobrace: false,
            noext: false,
            nonegate: true,
          }),
        });
      }
    }

    this.segments = segments;
    this.excludedSegments = new Set(segments.map(this.normalize));
    this.globPatterns = globPatterns;
  }

  excludes(path: PortableRelativePath): boolean {
    if (path === '') return false;
    const parts = path.split('/');
    if (parts.some((segment) => this.excludedSegments.has(this.normalize(segment)))) return true;

    for (const candidate of pathAndAncestors(path)) {
      if (this.globPatterns.some(({ matcher }) => matcher.match(candidate))) return true;
    }
    return false;
  }

  ripgrepGlobs(): readonly string[] {
    return [
      ...this.segments.flatMap((segment) => [`!**/${segment}`, `!**/${segment}/**`]),
      ...this.globPatterns.flatMap(({ pattern }) => negativeGlobPair(pattern)),
    ];
  }

  watchIgnoreGlobs(): readonly string[] {
    return [
      ...this.segments.flatMap((segment) => [
        segment,
        `${segment}/**`,
        `**/${segment}`,
        `**/${segment}/**`,
      ]),
      ...this.globPatterns.flatMap(({ pattern }) => positiveGlobPair(pattern)),
    ];
  }
}

/**
 * Normalize a list of exclusion patterns: trim, deduplicate, preserve user order.
 * Use this for display / storage where the user's ordering should be kept.
 */
export function normalizeExclusionPatterns(patterns: readonly string[]): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const raw of patterns) {
    const pattern = normalizeExclusionPattern(raw);
    if (!pattern || seen.has(pattern)) continue;
    seen.add(pattern);
    normalized.push(pattern);
  }
  return normalized;
}

/**
 * Canonical form of a pattern list: normalize, deduplicate, then sort.
 * Order-insensitive — use for identity keys and fingerprints where `['a','b']`
 * and `['b','a']` must map to the same identity.
 */
export function canonicalExclusionPatterns(patterns: readonly string[]): string[] {
  return normalizeExclusionPatterns(patterns).sort();
}

function normalizeExclusionPattern(pattern: string): string {
  // Replace backslashes with forward slashes for Windows-path tolerance.
  // This discards minimatch escape sequences (e.g. `\*`) but exclusion
  // patterns in user settings are almost never escaped globs.
  let normalized = pattern.trim().replaceAll('\\', '/').replace(/\/+/g, '/');
  if (normalized.startsWith('./')) normalized = normalized.slice(2);
  while (normalized.length > 1 && normalized.endsWith('/')) {
    normalized = normalized.slice(0, -1);
  }
  return normalized;
}

function isBareSegmentPattern(pattern: string): boolean {
  return !pattern.includes('/') && !GLOB_MAGIC_PATTERN.test(pattern);
}

function pathAndAncestors(path: PortableRelativePath): string[] {
  const candidates: string[] = [];
  let current = path as string;
  while (current) {
    candidates.push(current);
    const separator = current.lastIndexOf('/');
    if (separator === -1) break;
    current = current.slice(0, separator);
  }
  return candidates;
}

function negativeGlobPair(pattern: string): string[] {
  const positive = positiveGlobPair(pattern);
  return positive.map((glob) => `!${glob}`);
}

function positiveGlobPair(pattern: string): string[] {
  if (pattern.endsWith('/**')) return [pattern];
  return [pattern, `${pattern}/**`];
}
