/**
 * Node micro-benchmarks for layout hot paths.
 *
 * All benchmarks run in the `node` Vitest project (pure JS, no DOM).
 * Use `pnpm --filter @emdash/chat-ui run test:bench` to execute.
 *
 * Scenarios:
 *   - caches.parseBlocks: markdown parse + caching on representative bodies
 *   - layoutBlockStack:   full block layout over cached blocks
 *   - unitDef.measure (message blocks): block-level measure over a 2 000-item transcript
 */

import { messageUnitDef } from '@components/rows/message/message.def';
import { createChatCaches } from '@core/caches';
import { DEFAULT_THEME } from '@core/theme';
import { bench, describe } from 'vitest';
import { generateMockTranscript } from '@/mock-transcript';
import type { ChatItem, ChatMessage } from '@/model';
import { layoutBlockStack, measureBlockCached } from './block-stack';

// ── Fixtures ─────────────────────────────────────────────────────────────────

const TRANSCRIPT = generateMockTranscript(2000, 42);
const MESSAGE_ITEMS = (TRANSCRIPT.flatMap((turn) => turn.items) as ChatItem[]).filter(
  (x): x is ChatMessage => x.kind === 'message'
);

const REPRESENTATIVE_BODIES = [
  // Short prose
  'Hello world! This is a simple message.',
  // Medium prose with heading
  '## Overview\n\nLorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore.',
  // Prose + code block
  'Here is some code:\n\n```typescript\nfunction add(a: number, b: number): number {\n  return a + b;\n}\n```',
  // Multi-paragraph
  'Paragraph one.\n\nParagraph two with more text.\n\nParagraph three with even more text to measure.',
  // Table
  '| Column A | Column B |\n|----------|----------|\n| row 1a   | row 1b   |\n| row 2a   | row 2b   |',
];

const CACHES = createChatCaches();
const MEASURE_CTX = {
  theme: DEFAULT_THEME,
  width: 640,
  isCollapsed: (_id: string) => false,
  expanded: (_id: string) => false,
  caches: CACHES,
};

// ── Benchmarks ────────────────────────────────────────────────────────────────

describe('caches.parseBlocks', () => {
  bench('parse 5 representative bodies (cold cache)', () => {
    // Use a fresh cache instance + key each time to exercise the parser path.
    const cold = createChatCaches();
    const id = Math.random().toString(36).slice(2);
    for (const body of REPRESENTATIVE_BODIES) {
      cold.parseBlocks(`${id}-${body.length}`, body);
    }
  });

  bench('parse 5 representative bodies (warm cache)', () => {
    // Stable IDs against the shared CACHES instance — every call is a hit.
    for (let i = 0; i < REPRESENTATIVE_BODIES.length; i++) {
      CACHES.parseBlocks(`bench-warm-${i}`, REPRESENTATIVE_BODIES[i]);
    }
  });
});

describe('layoutBlockStack', () => {
  // Pre-parse once so we only measure layout, not parsing.
  const parsedBodies = REPRESENTATIVE_BODIES.map((body, i) =>
    CACHES.parseBlocks(`bench-layout-${i}`, body)
  );

  bench('layout 5 representative block stacks', () => {
    for (const blocks of parsedBodies) {
      layoutBlockStack(blocks, MEASURE_CTX);
    }
  });
});

describe('messageUnitDef.measure', () => {
  bench('measure 100 message rows (cold cache)', () => {
    const cold = createChatCaches();
    const coldCtx = { ...MEASURE_CTX, caches: cold };
    for (const item of MESSAGE_ITEMS.slice(0, 100)) {
      messageUnitDef.measure(item, coldCtx, messageUnitDef.vars!);
    }
  });

  bench('measure all message rows (warm blockMemo)', () => {
    for (const item of MESSAGE_ITEMS) {
      messageUnitDef.measure(item, MEASURE_CTX, messageUnitDef.vars!);
    }
  });
});

describe('measureBlockCached (individual blocks)', () => {
  // Pre-parse blocks so we isolate the layout cost from parse cost.
  const parsedBodies = REPRESENTATIVE_BODIES.map((body, i) =>
    CACHES.parseBlocks(`bench-block-${i}`, body)
  );

  bench('measure all blocks in 5 representative bodies', () => {
    for (const blocks of parsedBodies) {
      for (const block of blocks) {
        measureBlockCached(block, MEASURE_CTX);
      }
    }
  });
});
