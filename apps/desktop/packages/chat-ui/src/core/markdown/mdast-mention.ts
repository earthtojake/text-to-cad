import type { MentionKind, MentionSyntax } from '@emdash/shared/markdown';
/**
 * MdastMention — custom mdast node produced by the `remarkInlineMentions`
 * transform plugin.
 *
 * The plugin folds `@[label](target)` link nodes and splits `@bare` / `/command`
 * text spans into these nodes so the compiler (`blockToBlocks`) can map them
 * to `InlineMention` runs without needing to re-run regex scanning.
 */
import type { Node } from 'unist';

export interface MdastMention extends Node {
  type: 'mention';
  /** Which grammar form produced this node. */
  syntax: MentionSyntax;
  /** Display text shown in the pill (basename for file mentions). */
  label: string;
  /** Stable path/id for click-to-open (the link URL for bracket form). */
  target?: string;
  /** Short name override — same as label in most cases. */
  name?: string;
  /** Semantic category for pill icon and color. */
  mentionKind?: MentionKind;
  /** Optional devicon CSS class for the pill icon. */
  iconClass?: string;
  /** Optional host icon image URL for the pill icon. */
  iconUrl?: string;
  /** Tone override — 'command' for slash chips, 'math' for inline math. */
  tone?: string;
}
