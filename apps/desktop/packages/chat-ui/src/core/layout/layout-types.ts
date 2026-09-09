/**
 * Geometry types produced by the projected layout engine.
 *
 * These are plain data structures (no React, no MobX).
 * Leaf block layout types (ProseLaidOut, CodeLaidOut, TableLaidOut) are
 * consumed by Prose/Code/Table renderers and by BlockFrame for positioning.
 * They are also extended with a `raw` back-reference in BlockLeafLayout
 * (Project.tsx) so renderBlockLeaf can access source block data without a
 * separate lookup.
 *
 * Row-level layout aggregates (formerly MessageLayout) are now expressed as
 * compose trees (core/compose.ts) returned by each ComponentDef.measure().
 */

/** A single fragment on a line: the text to render and its x offset. */
export type FragmentLayout = {
  text: string;
  /** X offset in px from the block's left edge. */
  x: number;
  /** Index into the original `InlineRun[]` array — used to determine styling. */
  runIndex: number;
};

/** A single wrapped line inside a prose block. */
export type LineLayout = {
  /** Y offset in px from the block's top edge. */
  top: number;
  /** Left indent in px (for list items, blockquotes). */
  left: number;
  fragments: FragmentLayout[];
};

/** Optional absolute bullet marker (list items). */
export type BulletLayout = {
  x: number;
  top: number;
  char: string;
};

/** Prose block with pre-computed line/fragment geometry. */
export type ProseLaidOut = {
  kind: 'prose';
  id: string;
  top: number;
  height: number;
  /**
   * Widest line right-edge in px (textLeft + occupiedWidth of all fragments).
   * Used by MessageLayout to compute the user bubble hug-width.
   */
  contentWidth: number;
  /**
   * Per-line band height in px (variant line-height). The renderer sets this as
   * the line element's height so `.pf { top: 50% }` centers text within the band.
   */
  lineHeight: number;
  lines: LineLayout[];
  bullet?: BulletLayout;
  /** True if a left-side quote rail should be drawn. */
  quoteRail?: boolean;
};

/** Code block with pre-positioned source lines. */
export type CodeLaidOut = {
  kind: 'code';
  id: string;
  top: number;
  height: number;
  /** Full effective width — code blocks always fill their allocated area. */
  contentWidth: number;
  lines: { top: number; text: string }[];
  lang?: string;
};

/** Table block: formula-measured, single-line truncated cells. */
export type TableLaidOut = {
  kind: 'table';
  id: string;
  top: number;
  height: number;
  contentWidth: number;
  /** Width of each column in px (equal distribution, floored at TABLE_MIN_COL_W). */
  colWidths: number[];
  /** Total table width = colWidths.length * colW; may exceed contentWidth (triggers scroll). */
  tableWidth: number;
  header: string[];
  rows: string[][];
};

export type BlockLaidOut = ProseLaidOut | CodeLaidOut | TableLaidOut;

// ── Block leaf layout (produced by block-stack.ts) ────────────────────────────
//
// Extended leaf layout types that carry a back-reference to the source Block.
// Produced by `measureBlockCached` in `core/layout/block-stack.ts`.
// Used by `renderBlockLeaf` and `BlockStackView` to render without a lookup.

import type {
  Block,
  CodeBlock,
  MermaidBlock,
  ProseBlock,
  RuleBlock,
} from '@core/markdown/document';

export type ProseLeafLayout = ProseLaidOut & { raw: ProseBlock };
export type CodeLeafLayout = CodeLaidOut & { raw: CodeBlock };
export type TableLeafLayout = TableLaidOut & { raw: Block };

/** Layout for a horizontal rule block — a thin fixed-height separator. */
export type RuleLeafLayout = {
  kind: 'rule';
  id: string;
  top: number;
  height: number;
  raw: RuleBlock;
};

/** Layout for a Mermaid diagram block — fixed 21:9 aspect-ratio preview. */
export type MermaidLaidOut = {
  kind: 'mermaid';
  id: string;
  top: number;
  height: number;
  contentWidth: number;
  source: string;
};

export type MermaidLeafLayout = MermaidLaidOut & { raw: MermaidBlock };

export type BlockLeafLayout =
  | ProseLeafLayout
  | CodeLeafLayout
  | TableLeafLayout
  | RuleLeafLayout
  | MermaidLeafLayout;
