/**
 * Canonical mention grammar shared between the chat composer (write path) and
 * the transcript parser (read path) so neither side can drift from the other.
 *
 * Pure TypeScript — no remark/unified dependencies.
 */

/** Discriminator for the three inline-chip syntax forms. */
export type MentionSyntax = 'at-bare' | 'at-bracket' | 'slash';

/** Semantic category for a mention, mirrors the composer's MentionKind. */
export type MentionKind = 'file' | 'issue' | 'symbol' | 'custom';

/**
 * Pattern source for bare @-mention tokens.
 *
 * Matches word chars, slashes, hyphens, colons, parens, and internal dots.
 * A trailing dot is NOT consumed (sentence-final dot avoidance).
 *
 * Examples matched: @src/auth/jwt.ts  @issue-42  @handleSubmit()  @.gitignore
 *
 * Use as: `new RegExp(AT_BARE_PATTERN, 'g')`
 */
export const AT_BARE_PATTERN = String.raw`@((?:[\w/\-:()]|\.(?=[\w/\-:()]))+)`;

/**
 * Pattern source for /-command tokens.
 *
 * Matches only at line start or after whitespace to avoid matching path
 * separators and URLs (e.g. path/to/file, https://example.com/path).
 *
 * Examples matched: /web  /search-files  /explain
 *
 * Use as: `new RegExp(SLASH_PATTERN, 'g')`
 */
export const SLASH_PATTERN = String.raw`(?:^|(?<=\s))\/([\w-]+)`;

/**
 * Characters that require an angle-bracket URL destination in CommonMark.
 * Bare link destinations forbid spaces and unbalanced parentheses.
 */
const NEEDS_ANGLE = /[\s()]/;

/**
 * Produce the canonical text form of a mention for use as the serialized
 * submit/clipboard text.
 *
 * - File and issue mentions with a target: `@[label](target)`. When the target
 *   contains spaces or parentheses (forbidden in bare CommonMark destinations),
 *   it is wrapped in angle brackets: `@[label](<path with spaces>)`. remark
 *   parses both forms to the same link node, recovering the target verbatim.
 * - Everything else: `@${target ?? label}` (bare form).
 */
export function stringifyMention(m: {
  label: string;
  target?: string;
  kind: MentionKind | null;
}): string {
  if ((m.kind === 'file' || m.kind === 'issue') && m.target) {
    const dest = NEEDS_ANGLE.test(m.target) ? `<${m.target}>` : m.target;
    return `@[${m.label}](${dest})`;
  }
  return `@${m.target ?? m.label}`;
}
