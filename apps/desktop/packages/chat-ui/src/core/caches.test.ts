/**
 * caches.test.ts — unit tests for createChatCaches().
 *
 * Runs in jsdom because core/caches.ts → parse-blocks.ts →
 * decode-named-character-reference accesses document at module load time.
 *
 * @vitest-environment jsdom
 */

import { describe, expect, it } from 'vitest';
import { createChatCaches } from './caches';

// ── computeDiff memoization ───────────────────────────────────────────────────

describe('createChatCaches().computeDiff', () => {
  it('memoizes identical calls — same reference returned', () => {
    const caches = createChatCaches();
    const a = caches.computeDiff('foo\nbar', 'foo\nbaz');
    const b = caches.computeDiff('foo\nbar', 'foo\nbaz');
    expect(a).toBe(b);
  });

  it('different inputs → different results', () => {
    const caches = createChatCaches();
    const a = caches.computeDiff('x', 'y');
    const b = caches.computeDiff('x', 'z');
    expect(a).not.toBe(b);
  });

  it('instances are isolated — diff cache is not shared across createChatCaches() calls', () => {
    // Each createChatCaches() creates an isolated diff cache; a fresh instance
    // always produces a new array reference for the same input.
    const c1 = createChatCaches();
    const a = c1.computeDiff('a\nb', 'a\nc');
    const c2 = createChatCaches();
    const b = c2.computeDiff('a\nb', 'a\nc');
    // Different instances, same content, different references.
    expect(a).not.toBe(b);
    expect(a).toEqual(b);
  });

  it('instances are isolated — different bundles do not share cache', () => {
    const c1 = createChatCaches();
    const c2 = createChatCaches();
    const a = c1.computeDiff('foo\nbar', 'foo\nbaz');
    const b = c2.computeDiff('foo\nbar', 'foo\nbaz');
    // Same value, but different object references.
    expect(a).toEqual(b);
    expect(a).not.toBe(b);
  });
});

// ── parseBlocksStreaming ───────────────────────────────────────────────────────

describe('createChatCaches().parseBlocksStreaming', () => {
  it('returns empty array for empty text', () => {
    const caches = createChatCaches();
    expect(caches.parseBlocksStreaming('m1', '')).toEqual([]);
    expect(caches.parseBlocksStreaming('m1', '   ')).toEqual([]);
  });

  it('parses a simple growing paragraph without a boundary', () => {
    const caches = createChatCaches();
    const blocks = caches.parseBlocksStreaming('m1', 'Hello world');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe('prose');
  });

  it('stable prefix blocks keep object identity across appends', () => {
    const caches = createChatCaches();

    // First chunk: one complete paragraph + start of a second (no blank line yet).
    const text1 = 'Para one.\n\nPara two is grow';
    const blocks1 = caches.parseBlocksStreaming('m1', text1);
    expect(blocks1).toHaveLength(2);

    // Second chunk: para two keeps growing (no new boundary).
    const text2 = 'Para one.\n\nPara two is growing more';
    const blocks2 = caches.parseBlocksStreaming('m1', text2);
    expect(blocks2).toHaveLength(2);

    // The first block (settled prefix) must be the same object reference.
    expect(blocks2[0]).toBe(blocks1[0]);
    // The second block (growing tail) is re-parsed each time — different object.
    expect(blocks2[1]).not.toBe(blocks1[1]);
  });

  it('advances the stable prefix when a new blank line appears', () => {
    const caches = createChatCaches();

    const text1 = 'Para one.\n\nPara two is grow';
    const blocks1 = caches.parseBlocksStreaming('m1', text1);
    const firstBlock = blocks1[0];

    // New blank line after para two finalises it into the stable prefix.
    const text2 = 'Para one.\n\nPara two is complete.\n\nPara three start';
    const blocks2 = caches.parseBlocksStreaming('m1', text2);
    expect(blocks2).toHaveLength(3);

    // The first block is still the same object.
    expect(blocks2[0]).toBe(firstBlock);
    // The second block is now a stable object (it was finalised this chunk).
    expect(blocks2[1].kind).toBe('prose');
  });

  it('assigns sequential IDs across settled chunks', () => {
    const caches = createChatCaches();

    const finalText = 'Para one.\n\nPara two.\n\nPara three.';
    const blocks = caches.parseBlocksStreaming('m1', finalText);
    expect(blocks.map((b) => b.id)).toEqual(['m1#0', 'm1#1', 'm1#2']);
  });

  it('does not treat blank lines inside a code fence as a boundary', () => {
    const caches = createChatCaches();

    // Code fence is open — blank line inside should not become a boundary.
    const text = 'Intro.\n\n```js\nconst x = 1;\n\nconst y = 2;\n```\n\nOutro.';
    const blocks = caches.parseBlocksStreaming('m1', text);

    // Should have: intro prose, code block, outro prose.
    expect(blocks.some((b) => b.kind === 'code')).toBe(true);
  });

  it('falls back to full reparse on non-append text (edit/replay)', () => {
    const caches = createChatCaches();

    const text1 = 'Para one.\n\nPara two.\n\n';
    const blocks1 = caches.parseBlocksStreaming('m1', text1);
    const firstBlock = blocks1[0];

    // Simulate an edit — the new text does NOT start with the stable prefix.
    const textEdited = 'Completely different content.\n\n';
    const blocks2 = caches.parseBlocksStreaming('m1', textEdited);

    // IDs restart from 0.
    expect(blocks2[0].id).toBe('m1#0');
    // Object identity is reset — different from the original first block.
    expect(blocks2[0]).not.toBe(firstBlock);
  });

  it('parseBlocks (non-streaming) clears the streaming record', () => {
    const caches = createChatCaches();

    const text = 'Para one.\n\nPara two grow';
    const streaming = caches.parseBlocksStreaming('m1', text);
    const streamBlock = streaming[0];

    // Freeze — call the normal parseBlocks path.
    const frozen = caches.parseBlocks('m1', 'Para one.\n\nPara two complete.');
    expect(frozen).toHaveLength(2);

    // Next streaming call starts fresh (record was cleared by parseBlocks).
    const restarted = caches.parseBlocksStreaming('m1', 'New stream start');
    expect(restarted[0].id).toBe('m1#0');
    // Not the same object as before the freeze.
    expect(restarted[0]).not.toBe(streamBlock);
  });

  it('evictBlocks clears the streaming record as well', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\n');
    caches.evictBlocks('m1');
    // After evict, streaming restarts with counter 0.
    const blocks = caches.parseBlocksStreaming('m1', 'Fresh start');
    expect(blocks[0].id).toBe('m1#0');
  });

  it('clearAll() removes streaming records', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two grow');
    caches.clearAll();
    const blocks = caches.parseBlocksStreaming('m1', 'After clear');
    expect(blocks[0].id).toBe('m1#0');
  });

  // ── Fence-close boundary ──────────────────────────────────────────────────

  it('closes a code block as a boundary even without a trailing blank line', () => {
    const caches = createChatCaches();
    // Fence closes on its own line with no blank line after it.
    const text = 'Intro.\n\n```js\nconst x = 1;\n```\n';
    const blocks = caches.parseBlocksStreaming('m1', text);
    // Should have intro prose + code block in settled prefix; no growing tail.
    expect(blocks.some((b) => b.kind === 'code')).toBe(true);
    expect(blocks[0].kind).toBe('prose');
    expect(blocks[1].kind).toBe('code');
    // Both are settled — ids are sequential from 0.
    expect(blocks[0].id).toBe('m1#0');
    expect(blocks[1].id).toBe('m1#1');
  });

  it('code block keeps object identity after the fence closes when more text arrives', () => {
    const caches = createChatCaches();
    // First chunk: complete fenced code block with no trailing blank line.
    const text1 = 'Intro.\n\n```js\nconst x = 1;\n```\n';
    const blocks1 = caches.parseBlocksStreaming('m1', text1);
    const codeBlock1 = blocks1[1];
    expect(codeBlock1.kind).toBe('code');

    // Second chunk: more prose arrives but the code block is now settled.
    const text2 = text1 + 'Now call it.';
    const blocks2 = caches.parseBlocksStreaming('m1', text2);
    // Code block is still the exact same object reference (stable prefix).
    expect(blocks2[1]).toBe(codeBlock1);
    // Growing tail produces a new prose block.
    expect(blocks2).toHaveLength(3);
    expect(blocks2[2].kind).toBe('prose');
  });

  it('open fence does not trigger a fence-close boundary', () => {
    const caches = createChatCaches();
    // Fence is still open — no closing line yet.
    const text = 'Intro.\n\n```js\nconst x = 1;\n';
    const blocks = caches.parseBlocksStreaming('m1', text);
    // The code block is in the growing tail; intro prose has blank-line settled.
    expect(blocks.some((b) => b.kind === 'code')).toBe(true);
  });

  it('blank lines inside an open fence are still not boundaries', () => {
    const caches = createChatCaches();
    // Blank line inside the open fence must not commit the fence-open prefix.
    const text = 'Intro.\n\n```js\nconst x = 1;\n\nconst y = 2;\n';
    const blocks = caches.parseBlocksStreaming('m1', text);
    // Still a code block in the growing tail.
    expect(blocks.some((b) => b.kind === 'code')).toBe(true);
  });
});

// ── settledBlockCount ─────────────────────────────────────────────────────────

describe('createChatCaches().settledBlockCount', () => {
  it('returns 0 before any streaming parse', () => {
    const caches = createChatCaches();
    expect(caches.settledBlockCount('m1')).toBe(0);
  });

  it('returns 0 while the tail is still growing (no safe boundary yet)', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Growing paragraph, no blank line yet');
    expect(caches.settledBlockCount('m1')).toBe(0);
  });

  it('advances to 1 after the first blank-line boundary', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two grows');
    expect(caches.settledBlockCount('m1')).toBe(1);
  });

  it('advances by the number of newly settled blocks per chunk', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two.\n\nPara three grows');
    expect(caches.settledBlockCount('m1')).toBe(2);
  });

  it('advances to 2 when a code fence closes (no trailing blank line required)', () => {
    const caches = createChatCaches();
    // Intro para + code block settle once the fence closes.
    caches.parseBlocksStreaming('m1', 'Intro.\n\n```js\nconst x = 1;\n```\n');
    expect(caches.settledBlockCount('m1')).toBe(2);
  });

  it('does not advance past an open fence (blank lines inside are not boundaries)', () => {
    const caches = createChatCaches();
    // Intro prose settles at the blank line before the opening fence (count = 1).
    // The blank line inside the open fence does NOT advance the count further.
    caches.parseBlocksStreaming('m1', 'Intro.\n\n```js\nconst x = 1;\n\nconst y = 2;\n');
    // Intro prose has settled (1 block), but the code block is still open.
    expect(caches.settledBlockCount('m1')).toBe(1);
  });

  it('returns 0 after evictBlocks', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two grows');
    caches.evictBlocks('m1');
    expect(caches.settledBlockCount('m1')).toBe(0);
  });

  it('returns 0 after clearAll', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two grows');
    caches.clearAll();
    expect(caches.settledBlockCount('m1')).toBe(0);
  });

  it('resets to 0 after parseBlocks clears the streaming record', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two grows');
    caches.parseBlocks('m1', 'Para one.\n\nPara two complete.');
    expect(caches.settledBlockCount('m1')).toBe(0);
  });

  it('is independent per message id', () => {
    const caches = createChatCaches();
    caches.parseBlocksStreaming('m1', 'Para one.\n\nPara two grows');
    caches.parseBlocksStreaming('m2', 'Other message, no boundary yet');
    expect(caches.settledBlockCount('m1')).toBe(1);
    expect(caches.settledBlockCount('m2')).toBe(0);
  });
});
