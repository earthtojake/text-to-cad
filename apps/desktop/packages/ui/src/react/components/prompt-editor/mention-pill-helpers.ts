/**
 * Pure helpers for mention pill display — icon resolution and display-name
 * extraction. Kept in a standalone module so they can be unit-tested without
 * a DOM environment.
 */

import { resolveFileIconClass } from '../../lib/file-icons';
import type { MentionKind } from './types';

// ── Basename ──────────────────────────────────────────────────────────────────

/**
 * Return the last path segment of a POSIX or Windows path.
 *
 * @example
 * basename('src/components/foo.tsx') // 'foo.tsx'
 * basename('foo.tsx')                // 'foo.tsx'
 * basename('')                       // ''
 */
export function basename(path: string): string {
  if (!path) return '';
  // Normalize backslash separators.
  const normalized = path.replace(/\\/g, '/');
  const last = normalized.split('/').at(-1) ?? '';
  return last;
}

// ── File-icon class ───────────────────────────────────────────────────────────

/**
 * Return a devicon CSS class for a file label, or null when no icon is
 * registered. Delegates to `resolveFileIconClass` which checks full-filename
 * overrides and then the file extension.
 */
export function fileIconClass(label: string): string | null {
  return resolveFileIconClass(basename(label));
}

// ── Lucide icon name by kind ──────────────────────────────────────────────────

/** Map a MentionKind to a lucide icon name for use in the pill. */
export const KIND_ICON: Record<MentionKind, string> = {
  file: 'File',
  issue: 'CircleDot',
  symbol: 'Braces',
  custom: 'AtSign',
};
