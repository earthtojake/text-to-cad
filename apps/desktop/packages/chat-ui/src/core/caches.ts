/**
 * ChatCaches — per-ChatRoot instance data caches.
 *
 * Each mounted ChatRoot creates its own bundle via `createChatCaches()`.
 * The bundle owns four Map-backed caches (blocks, rich-inline text, syntax
 * highlight tokens, and diff rows) so different instances never share mutable
 * state and teardown is a single `caches.clear()` call.
 *
 * Distribution of global vs instance-scoped state
 * ─────────────────────────────────────────────────
 * Stays global (intentional):
 *   _highlighter (Shiki engine)  — stateless, expensive one-time init.
 *   nodeMemo / blockMemo         — WeakMap keyed by object identity, GC'd.
 *   pretext internal caches      — third-party global; flushed via clearTextMeasure().
 *   SUPPORTED_LANGS etc.         — immutable constants.
 *
 * Moved to per-instance (this file):
 *   blockCache       — string-keyed by messageId; unbounded; conflict vector.
 *   richInlineCache  — content-keyed; was unbounded.
 *   highlightCache   — content-keyed; bounded LRU 200, but leaked across instances.
 *   diffCache        — content-keyed; bounded LRU 100, but leaked across instances.
 *
 * ── Reaching the bundle ──────────────────────────────────────────────────────
 * Two execution contexts need caches:
 *   Measure path  — has MeasureCtx → add ctx.caches.
 *   Render leaves — Solid components deep in Project → add CachesContext + useCaches().
 */

import { clearCache as clearPretextInternalCaches } from '@chenglou/pretext';
import {
  type PreparedRichInline,
  type RichInlineItem,
  prepareRichInline as rawPrepareRichInline,
} from '@chenglou/pretext/rich-inline';
import { computeDiffRows } from '@components/rows/tools/diff/diff-lines';
import type { DiffRow } from '@components/rows/tools/diff/diff-lines';
import { renderMermaidSVG } from 'beautiful-mermaid';
import {
  createDefaultHighlighter,
  type ChatHighlighter,
  type HighlightResult,
} from './highlight/highlighter';
import type { CommandProvider } from './markdown/command-provider';
import type { Block } from './markdown/document';
import type { MentionProvider } from './markdown/mention-provider';
import { parseMarkdownToBlocks } from './markdown/parse';

// ── Streaming parse helpers ───────────────────────────────────────────────────
//
// Incremental (append-aware) streaming parser state. During streaming each new
// chunk re-parses only the "growing" tail (text after the last safe boundary).
// Safe boundaries are:
//   • A closing code fence line (3+ backticks/tildes at line start) — the code
//     block is structurally complete at this point and can be committed without
//     waiting for a trailing blank line.
//   • A blank line that is not inside an open code fence.
//
// The settled prefix keeps its Block object identities across chunks so
// blockMemo (WeakMap-keyed by Block ref) hits for them — turning the O(n²)
// re-parse/re-measure/re-render into O(tail) per chunk.

type StreamingRecord = {
  /** Portion of the message text whose blocks are stable (object-identity-stable). */
  stableText: string;
  /** Parsed Block objects for stableText. Never mutated after creation. */
  stableBlocks: Block[];
  /** Next block counter value = stableBlocks.length. */
  counter: number;
};

/**
 * Returns true if `text` ends inside an open code fence (a line starting with
 * 3+ backticks or tildes). Used to avoid treating blank lines inside code blocks
 * as safe streaming-parse boundaries.
 */
function endsInsideFence(text: string): boolean {
  let inside = false;
  let i = 0;
  while (i < text.length) {
    const nlIdx = text.indexOf('\n', i);
    const lineEnd = nlIdx === -1 ? text.length : nlIdx;
    const line = text.slice(i, lineEnd);
    if (/^\s*(`{3,}|~{3,})/.test(line)) inside = !inside;
    if (nlIdx === -1) break;
    i = nlIdx + 1;
  }
  return inside;
}

/**
 * Returns the position in `tail` immediately after the last safe streaming
 * parse boundary. Two events constitute a safe boundary:
 *
 *   1. A closing code fence line (3+ backticks/tildes at line start that
 *      transitions `inside` from true to false). The code block is
 *      structurally complete at this point — remark parses it identically
 *      in isolation — so we commit immediately without waiting for a trailing
 *      blank line.
 *   2. A blank line (`\n\n`) that is not inside an open code fence.
 *
 * Returns 0 when no safe boundary exists (the entire tail is still growing).
 *
 * `stableText` is used to determine whether the start of `tail` is already
 * inside a code fence opened in the stable prefix.
 */
function findSafeStreamBoundary(stableText: string, tail: string): number {
  let inside = endsInsideFence(stableText);
  let lastSafe = 0;
  let i = 0;

  while (i < tail.length) {
    const nlIdx = tail.indexOf('\n', i);
    if (nlIdx === -1) break;
    const line = tail.slice(i, nlIdx);
    const isFence = /^\s*(`{3,}|~{3,})/.test(line);
    if (isFence) {
      inside = !inside;
      // A line that just closed a fence is a safe commit point: the fenced
      // code block is structurally complete even without a trailing blank line.
      if (!inside) lastSafe = nlIdx + 1;
    }
    // A blank line outside a fence is also a safe boundary.
    if (!inside && tail[nlIdx + 1] === '\n') {
      lastSafe = nlIdx + 2;
    }
    i = nlIdx + 1;
  }

  return lastSafe;
}

// ── Cache key helpers ─────────────────────────────────────────────────────────

/**
 * Content-addressable key for a RichInlineItem[].
 * Uses control-character separators to avoid collision and stay fast.
 */
function richInlineKey(items: RichInlineItem[]): string {
  let key = '';
  for (const item of items) {
    key += item.font;
    key += '\x00';
    key += item.text;
    key += '\x00';
    if (item.break) key += item.break;
    key += '\x00';
    if (item.extraWidth !== undefined) key += item.extraWidth;
    key += '\x01';
  }
  return key;
}

// ── LRU helpers ───────────────────────────────────────────────────────────────

function lruGet<V>(cache: Map<string, V>, key: string): V | undefined {
  const val = cache.get(key);
  if (val !== undefined) {
    cache.delete(key);
    cache.set(key, val);
  }
  return val;
}

function lruSet<V>(cache: Map<string, V>, key: string, val: V, maxSize: number): void {
  if (cache.size >= maxSize) {
    cache.delete(cache.keys().next().value!);
  }
  cache.set(key, val);
}

// ── SharedCaches ─────────────────────────────────────────────────────────────
//
// Content-addressed caches that are safe to share across all conversations.
// Owned by ChatContext; survives view mounts/unmounts.

export type SharedCaches = {
  /** Return a cached PreparedRichInline for items; computes and caches on miss. */
  prepareRichInline(items: RichInlineItem[]): PreparedRichInline;
  /**
   * Syntax-highlight code; returns null for unsupported languages.
   * Caches result in a bounded LRU (200 entries).
   */
  highlight(code: string, lang: string | undefined): HighlightResult | null;
  /**
   * Cache-only highlight lookup; never triggers parsing.
   * Use for the synchronous fast-path on scroll-back re-mounts.
   */
  peekHighlight(code: string, lang: string | undefined): HighlightResult | null;
  /** Compute a line-level diff with bounded LRU caching (100 entries). */
  computeDiff(oldText: string | null, newText: string): DiffRow[];
  /**
   * Render a Mermaid diagram source to an SVG string.
   * Returns null on invalid/unsupported input.
   * Caches result in a bounded LRU (100 entries).
   * Uses CSS-variable theming so a single cached SVG adapts to light/dark.
   */
  renderMermaid(source: string): string | null;
  /**
   * Cache-only Mermaid SVG lookup; never triggers rendering.
   * Use for the synchronous fast-path on scroll-back re-mounts.
   */
  peekMermaid(source: string): string | null;
  /**
   * Flush pretext's internal global caches.
   * Call after fonts load (glyph metrics change with the loaded font).
   * Width changes do NOT require this flush — the block fingerprint
   * (measureEpoch|width|collapsed) already handles width invalidation.
   */
  clearTextMeasure(): void;
};

// ── ParseCaches ───────────────────────────────────────────────────────────────
//
// messageId-keyed parse caches. Owned by ChatState (per conversation); ties
// Block object identities to a specific message so WeakMap measurement caches
// hit across streaming updates.

export type ParseCaches = {
  /** Parse markdown into a Block[] with identity-stable caching per messageId. */
  parseBlocks(id: string, markdown: string): Block[];
  /**
   * Incremental streaming parse — O(tail) per chunk instead of O(n²).
   *
   * Maintains a per-id streaming record that tracks the stable prefix (text
   * whose Block objects are reused across chunks so blockMemo hits for them).
   * Only the growing tail after the last safe boundary is re-parsed on each
   * chunk. Safe boundaries are:
   *   • A closing code fence line (commits the code block immediately).
   *   • A blank line outside any open code fence.
   *
   * Call this while `item.streaming === true`; switch to the normal
   * `parseBlocks` after the turn is frozen — that final call clears the record.
   *
   * Limitations (acceptable for chat use):
   *   - Non-append mutations (edit/replay) fall back to a full reparse.
   *   - Link-reference definitions and exotic loose-list continuations near
   *     a blank-line boundary may not parse identically in isolation vs. in
   *     context.
   */
  parseBlocksStreaming(id: string, markdown: string): Block[];
  /**
   * Returns the number of blocks currently in the stable settled prefix for a
   * streaming message. Blocks with index `< settledBlockCount(id)` have crossed
   * a safe parse boundary and will not be re-parsed. Returns 0 when no record
   * exists (not streaming / not yet parsed).
   */
  settledBlockCount(id: string): number;
  /** Drop the cached blocks for one message (call after text is frozen). */
  evictBlocks(id: string): void;
  /** Drop all parse caches. Call when the ChatState disposes. */
  clearAll(): void;
};

// ── ChatCaches ────────────────────────────────────────────────────────────────
//
// Full bundle provided to CachesContext and MeasureCtx. Assembled by ChatView
// from SharedCaches (context) + ParseCaches (state). Leaf components call
// useCaches() to obtain this.

export type ChatCaches = SharedCaches & ParseCaches;

const HIGHLIGHT_CACHE_MAX = 200;
const DIFF_CACHE_MAX = 100;
const MERMAID_CACHE_MAX = 100;

// ── createSharedCaches ────────────────────────────────────────────────────────
//
// Creates the content-addressed caches owned by ChatContext. Safe to share
// across all conversations; survives view mounts/unmounts.

export function createSharedCaches(highlighter?: ChatHighlighter): SharedCaches {
  const hl = highlighter ?? createDefaultHighlighter();

  // Rich-inline text measurement cache — keyed by content.
  // Width-independent: prepareRichInline measures intrinsic glyph widths, not
  // line-broken layout, so the same prepared items are valid at any column width.
  const richInlineCache = new Map<string, PreparedRichInline>();

  // Syntax highlight LRU — keyed by `${resolvedLang}\x00${code}`.
  const highlightCache = new Map<string, HighlightResult>();

  // Diff LRU — keyed by `${oldText ?? '\x00null'}\x00${newText}`.
  const diffCache = new Map<string, DiffRow[]>();

  // Mermaid SVG LRU — keyed by source text.
  const mermaidCache = new Map<string, string>();

  function diffKey(oldText: string | null, newText: string): string {
    return `${oldText ?? '\x00null'}\x00${newText}`;
  }

  return {
    prepareRichInline(items) {
      const key = richInlineKey(items);
      const cached = richInlineCache.get(key);
      if (cached) return cached;
      const prepared = rawPrepareRichInline(items);
      richInlineCache.set(key, prepared);
      return prepared;
    },

    highlight(code, lang) {
      const key = `${lang ?? ''}\x00${code}`;
      const cached = lruGet(highlightCache, key);
      if (cached) return cached;
      try {
        const result = hl.highlight(code, lang);
        if (!result) return null;
        lruSet(highlightCache, key, result, HIGHLIGHT_CACHE_MAX);
        return result;
      } catch {
        return null;
      }
    },

    peekHighlight(code, lang) {
      return lruGet(highlightCache, `${lang ?? ''}\x00${code}`) ?? null;
    },

    computeDiff(oldText, newText) {
      const key = diffKey(oldText, newText);
      const cached = lruGet(diffCache, key);
      if (cached) return cached;
      const result = computeDiffRows(oldText, newText);
      lruSet(diffCache, key, result, DIFF_CACHE_MAX);
      return result;
    },

    renderMermaid(source) {
      const hit = lruGet(mermaidCache, source);
      if (hit !== undefined) return hit;
      try {
        // CSS variables as color values so a single cached SVG adapts to
        // light/dark mode without re-rendering.
        const svg = renderMermaidSVG(source, {
          transparent: true,
          bg: 'var(--chat-bg)',
          fg: 'var(--chat-fg)',
          line: 'var(--chat-fg-muted)',
          muted: 'var(--chat-fg-passive)',
          surface: 'var(--chat-bg-1)',
          border: 'var(--chat-border)',
        });
        lruSet(mermaidCache, source, svg, MERMAID_CACHE_MAX);
        return svg;
      } catch {
        return null;
      }
    },

    peekMermaid(source) {
      return mermaidCache.get(source) ?? null;
    },

    clearTextMeasure() {
      // Flush richInlineCache: PreparedRichInline objects embed glyph metrics
      // from pretext, so they must be invalidated when fonts change.
      // Width changes do NOT require this flush — block fingerprints
      // (measureEpoch|width|collapsed) handle width invalidation.
      richInlineCache.clear();
      // Flush pretext's internal glyph cache (metrics change when fonts load).
      clearPretextInternalCaches();
    },
  };
}

// ── createParseCaches ─────────────────────────────────────────────────────────
//
// Creates the messageId-keyed parse caches owned by ChatState (per conversation).
// Keeping Block object identities stable across streaming updates is what lets
// WeakMap measurement caches hit without full re-measurement.

export function createParseCaches(
  mentionProvider?: MentionProvider,
  commandProvider?: CommandProvider,
  uri?: string
): ParseCaches {
  // Block parse cache — keyed by messageId.
  const blockCache = new Map<string, { text: string; blocks: Block[] }>();

  // Streaming parse records — keyed by messageId. Cleared when the non-streaming
  // parseBlocks path is taken (i.e. on turn freeze).
  const streamCache = new Map<string, StreamingRecord>();

  return {
    parseBlocks(id, markdown) {
      // Clear any streaming record — this path is taken after turn freeze.
      streamCache.delete(id);
      const hit = blockCache.get(id);
      if (hit && hit.text === markdown) return hit.blocks;
      const blocks = parseMarkdownToBlocks(id, markdown, mentionProvider, commandProvider, 0, uri);
      blockCache.set(id, { text: markdown, blocks });
      return blocks;
    },

    parseBlocksStreaming(id, markdown) {
      if (!markdown.trim()) return [];

      let rec = streamCache.get(id);

      // If the text is not an append (edit/replay), reset and treat all content
      // as a fresh growing tail with no stable prefix.
      if (!rec || !markdown.startsWith(rec.stableText)) {
        rec = { stableText: '', stableBlocks: [], counter: 0 };
        streamCache.set(id, rec);
      }

      const tail = markdown.slice(rec.stableText.length);

      // Find the last blank-line boundary in the tail that is outside any open
      // code fence. Everything before it can be parsed as stable settled blocks.
      const boundary = findSafeStreamBoundary(rec.stableText, tail);

      if (boundary > 0) {
        // Parse the newly settled chunk and append to the stable prefix. These
        // blocks get object-stable identities on subsequent chunks (blockMemo hits).
        const settledChunk = tail.slice(0, boundary);
        const newBlocks = parseMarkdownToBlocks(
          id,
          settledChunk,
          mentionProvider,
          commandProvider,
          rec.counter,
          uri
        );
        rec.stableBlocks = [...rec.stableBlocks, ...newBlocks];
        rec.stableText += settledChunk;
        rec.counter += newBlocks.length;
      }

      // Re-parse the still-growing tail (small; only content after boundary).
      const growingChunk = tail.slice(boundary);
      const growingBlocks = growingChunk.trim()
        ? parseMarkdownToBlocks(
            id,
            growingChunk,
            mentionProvider,
            commandProvider,
            rec.counter,
            uri
          )
        : [];

      return growingBlocks.length > 0 ? [...rec.stableBlocks, ...growingBlocks] : rec.stableBlocks;
    },

    settledBlockCount(id) {
      return streamCache.get(id)?.counter ?? 0;
    },

    evictBlocks(id) {
      blockCache.delete(id);
      streamCache.delete(id);
    },

    clearAll() {
      blockCache.clear();
      streamCache.clear();
    },
  };
}

// ── createChatCaches ──────────────────────────────────────────────────────────
//
// Legacy combined factory — used by the fallback CachesContext and direct
// story/test mounts that do not set up a full ChatContext + ChatState.
// Assembles SharedCaches + ParseCaches into a single ChatCaches bundle.

export function createChatCaches(
  highlighter?: ChatHighlighter,
  mentionProvider?: MentionProvider,
  commandProvider?: CommandProvider
): ChatCaches {
  const shared = createSharedCaches(highlighter);
  const parse = createParseCaches(mentionProvider, commandProvider);
  return { ...shared, ...parse };
}

// ── Module-level fallback ─────────────────────────────────────────────────────

/**
 * Lazily-created fallback bundle for call sites that are not under a
 * CachesContext.Provider (direct test/story mounts of leaf components).
 *
 * Not used in production ChatView mounts; those supply context+state caches.
 */
let _fallbackCaches: ChatCaches | null = null;

export function getFallbackCaches(): ChatCaches {
  if (!_fallbackCaches) _fallbackCaches = createChatCaches();
  return _fallbackCaches;
}
