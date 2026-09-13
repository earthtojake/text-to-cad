/**
 * document — Parsed markdown document model.
 *
 * This is the output contract of the markdown parser (core/markdown/parse.ts).
 * A ChatMessage's markdown is split into Block[] so that:
 *   1. The measurement engine can measure each block independently.
 *   2. Renderers can specialise per block kind (prose / code / table).
 *   3. Collapse state is stored per-block by stable ID.
 *
 * This module is PURE: no geometry, no pretext/fonts, no DOM imports.
 */

/** Fine-grained variant within the prose block kind. */
export type ProseVariant = 'body' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'list-item' | 'quote';

// ── Inline run types ──────────────────────────────────────────────────────────

/** A segment of styled text within a prose block. */
export type InlineText = {
  kind: 'text';
  text: string;
  bold?: boolean;
  italic?: boolean;
  strike?: boolean;
  href?: string;
};

/** Inline code span — rendered with extra chrome (padding). */
export type InlineCode = {
  kind: 'code';
  text: string;
};

/** Mention chip — rendered with badge-style chrome (padding + bg). */
export type InlineMention = {
  kind: 'mention';
  label: string;
  /** Optional semantic tone for the chip colour (e.g. 'math' for inline-math). */
  tone?: string;
  /**
   * Fields populated when a MentionProvider resolves the @-token to rich metadata.
   * Absent for plain-text heuristic mentions (e.g. the inline-math fallback).
   */
  id?: string;
  /** Short display name shown in the rendered pill. Defaults to label. */
  name?: string;
  /** Semantic category for the pill icon and colour. */
  mentionKind?: 'file' | 'issue' | 'symbol' | 'custom';
  /** Optional host icon CSS class (e.g. a devicon class) rendered as `<i>`. */
  iconClass?: string;
  /** Optional host icon image URL rendered as `<img>`. */
  iconUrl?: string;
};

/**
 * Explicit line break — produced from a hard break node (two trailing spaces /
 * backslash line ending) or a literal `\n` inside a text node. `layoutProse`
 * uses these as segment boundaries; `runsToRichItems` never sees them.
 */
export type InlineBreak = { kind: 'break' };

export type InlineRun = InlineText | InlineCode | InlineMention | InlineBreak;

/**
 * The text shown inside a rendered mention pill.
 *
 * Slash-command chips (`tone: 'command'`) keep their `/`-prefixed `label` so they
 * read as commands and stay visually distinct from file/issue/symbol mentions
 * (whose `name` is a bare basename). All other mentions prefer the short `name`,
 * falling back to `label`.
 */
export function mentionDisplayText(mention: InlineMention): string {
  if (mention.tone === 'command') return mention.label;
  return mention.name ?? mention.label;
}

// ── Block types ───────────────────────────────────────────────────────────────

/** Stable ID format: `${messageId}#${blockIndex}` */
export type BlockId = string;

/**
 * A prose block (paragraph, heading, list item, or blockquote paragraph).
 * The `runs` array is what pretext/rich-inline receives for height measurement.
 */
export type ProseBlock = {
  kind: 'prose';
  id: BlockId;
  variant: ProseVariant;
  runs: InlineRun[];
  /** Nesting depth (for list items and blockquotes). */
  depth?: number;
};

/**
 * A fenced or indented code block.
 * Height is computed via: `lines.length * CODE_LINE_HEIGHT + 2 * CODE_BLOCK_PAD_Y`.
 */
export type CodeBlock = {
  kind: 'code';
  id: BlockId;
  /** Raw source code. */
  code: string;
  /** Optional language hint (e.g. "typescript"). */
  lang?: string;
};

/**
 * A markdown table — formula-measured (static row height), no DOM write-back.
 * Height = (1 + rows.length) * TABLE_ROW_H + TABLE_BORDER.
 */
export type TableBlock = {
  kind: 'table';
  id: BlockId;
  /** Column header labels. */
  header: string[];
  /** Data rows — each row is an array of cell strings, same length as header. */
  rows: string[][];
};

/**
 * A horizontal rule (`---`) separating sections.
 * Height is a fixed 1px line; margins are owned by the block def.
 */
export type RuleBlock = {
  kind: 'rule';
  id: BlockId;
};

/**
 * A fenced Mermaid diagram (` ```mermaid `).
 * Rendered as a clickable 21:9 SVG preview via beautiful-mermaid.
 */
export type MermaidBlock = {
  kind: 'mermaid';
  id: BlockId;
  /** Raw Mermaid source text. */
  source: string;
};

export type Block = ProseBlock | CodeBlock | TableBlock | RuleBlock | MermaidBlock;
