import type { ChatMentionMeta, MentionProvider } from './core/markdown/mention-provider';
import type {
  ChatItem,
  ChatPlanEntry,
  ChatResourceLink,
  ChatRole,
  FileOpKind,
  ResourceTarget,
  ToolStatus,
  TranscriptTurn,
} from './model';

/** Tiny deterministic PRNG (mulberry32) so stories render identically each time. */
function makeRng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const WORDS = (
  'lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor ' +
  'incididunt ut labore et dolore magna aliqua enim ad minim veniam quis nostrud ' +
  'exercitation ullamco laboris nisi aliquip ex ea commodo consequat duis aute'
).split(' ');

function words(rng: () => number, min: number, max: number): string {
  const n = min + Math.floor(rng() * (max - min + 1));
  const out: string[] = [];
  for (let i = 0; i < n; i++) out.push(WORDS[Math.floor(rng() * WORDS.length)]);
  const s = out.join(' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── Code samples ──────────────────────────────────────────────────────────────

const CODE_SAMPLE = [
  '```typescript',
  'function add(a: number, b: number): number {',
  '  return a + b;',
  '}',
  'console.log(add(2, 3));',
  '```',
].join('\n');

const LARGE_CODE_SAMPLE = [
  '```typescript',
  'import { createSignal, createMemo, For, Show } from "solid-js";',
  '',
  'type Item = { id: string; label: string; done: boolean };',
  '',
  'export function TodoList() {',
  '  const [items, setItems] = createSignal<Item[]>([]);',
  '  const [input, setInput] = createSignal("");',
  '',
  '  const remaining = createMemo(() => items().filter((x) => !x.done).length);',
  '',
  '  const addItem = () => {',
  '    const text = input().trim();',
  '    if (!text) return;',
  '    setItems((prev) => [...prev, { id: crypto.randomUUID(), label: text, done: false }]);',
  '    setInput("");',
  '  };',
  '',
  '  const toggle = (id: string) => {',
  '    setItems((prev) => prev.map((x) => (x.id === id ? { ...x, done: !x.done } : x)));',
  '  };',
  '',
  '  const remove = (id: string) => {',
  '    setItems((prev) => prev.filter((x) => x.id !== id));',
  '  };',
  '',
  '  return (',
  '    <div class="todo-root">',
  '      <h1>Todos ({remaining()} remaining)</h1>',
  '      <div class="add-row">',
  '        <input value={input()} onInput={(e) => setInput(e.currentTarget.value)} />',
  '        <button onClick={addItem}>Add</button>',
  '      </div>',
  '      <For each={items()}>',
  '        {(item) => (',
  '          <div class="item" classList={{ done: item.done }}>',
  '            <input type="checkbox" checked={item.done} onChange={() => toggle(item.id)} />',
  '            <span>{item.label}</span>',
  '            <button onClick={() => remove(item.id)}>x</button>',
  '          </div>',
  '        )}',
  '      </For>',
  '    </div>',
  '  );',
  '}',
  '```',
].join('\n');

// ── Table samples ─────────────────────────────────────────────────────────────

const TABLE_SAMPLE = [
  '| Block | Strategy |',
  '|-------|----------|',
  '| prose | pretext  |',
  '| code  | line-count |',
  '| island | DOM measure |',
].join('\n');

const LARGE_TABLE_SAMPLE = [
  '| Metric | Before | After | Delta |',
  '|--------|--------|-------|-------|',
  '| Initial paint (200 rows) | 1240ms | 890ms | -28% |',
  '| p50 frame time (10k sweep) | 12ms | 8ms | -33% |',
  '| p95 frame time (10k sweep) | 60ms | 17ms | -72% |',
  '| max frame time (10k sweep) | 84ms | 22ms | -74% |',
  '| DOM nodes created / frame | 320 | 320 | 0% |',
  '| Row creations during sweep | 1820 | 1820 | 0% |',
  '| Heap after dispose (MB) | 18.4 | 17.9 | -3% |',
  '| setCount seed (10k rows) | 4.2ms | 3.1ms | -26% |',
  '| setCount seed (100k rows) | 41ms | 30ms | -27% |',
  '| parse cache hit rate | 32% | 78% | +46pp |',
  '| nodeMemo hit rate | 45% | 91% | +46pp |',
].join('\n');

// ── Diff sample pairs ─────────────────────────────────────────────────────────

type DiffSample = { oldText: string | null; newText: string };

const DIFF_SAMPLES: DiffSample[] = [
  // Small modify — two lines changed
  {
    oldText: 'const a = 1;\nconst b = 2;\n\nexport { a, b };',
    newText: 'const a = 1;\nconst b = 3;\nconst c = a + b;\n\nexport { a, b, c };',
  },
  // Multi-line modify — function body rewrite
  {
    oldText: ['export function estimate(item: ChatItem): number {', '  return 60;', '}'].join('\n'),
    newText: [
      'export function estimate(item: ChatItem, ctx: MeasureCtx): number {',
      '  const text = "text" in item ? item.text : "";',
      '  const lines = Math.max(1, Math.ceil((text?.length ?? 0) / 60));',
      '  return lines * ctx.theme.fonts.body.lineHeight;',
      '}',
    ].join('\n'),
  },
  // New file (oldText null)
  {
    oldText: null,
    newText: [
      '/**',
      ' * generic-estimate — engine-level fallback height heuristic.',
      ' */',
      "import type { MeasureCtx } from '../define';",
      "import type { ChatItem } from '../../model';",
      '',
      'export function genericEstimate(item: ChatItem, ctx: MeasureCtx): number {',
      '  const text = "text" in item && typeof item.text === "string" ? item.text : "";',
      '  const lines = Math.max(1, Math.ceil(text.length / 60));',
      '  return lines * ctx.theme.fonts.body.lineHeight;',
      '}',
    ].join('\n'),
  },
  // Larger modify — config object diff
  {
    oldText: [
      'const config = {',
      '  overscanBefore: 4,',
      '  overscanAfter: 4,',
      '  estimateSize: () => 60,',
      '};',
    ].join('\n'),
    newText: [
      'const OVERSCAN_BASE = 4;',
      'const OVERSCAN_LEADING = 12;',
      'const OVERSCAN_TRAILING = 3;',
      '',
      'const config = {',
      '  overscanBefore: OVERSCAN_TRAILING,',
      '  overscanAfter: OVERSCAN_LEADING,',
      '  estimateSize: (i: number) => estimateRowHeight(getItem(state, i), ctx),',
      '};',
    ].join('\n'),
  },
];

/** Build a markdown body whose shape varies by index to exercise every block tier. */
function bodyFor(rng: () => number, i: number): string {
  const variant = i % 8;
  switch (variant) {
    case 0:
      return words(rng, 8, 40) + '.';
    case 1:
      return `## ${words(rng, 2, 5)}\n\n${words(rng, 20, 60)}.`;
    case 2:
      return [
        words(rng, 5, 15) + ':',
        '',
        `- ${words(rng, 3, 8)}`,
        `- ${words(rng, 3, 8)}`,
        `- ${words(rng, 3, 8)}`,
      ].join('\n');
    case 3:
      return `${words(rng, 6, 18)}.\n\n${CODE_SAMPLE}`;
    case 4:
      return `> ${words(rng, 8, 24)}.`;
    case 5:
      return `${words(rng, 6, 18)}.\n\n${TABLE_SAMPLE}`;
    // Heavy variants for content-magnitude variety
    case 6:
      // Long prose (120-200 words) to stress pretext line-break measurement
      return words(rng, 40, 80) + '.\n\n' + words(rng, 40, 80) + '.\n\n' + words(rng, 20, 40) + '.';
    default:
      // Heavy: multi-paragraph + large code block
      return `${words(rng, 10, 25)}.\n\n${LARGE_CODE_SAMPLE}`;
  }
}

/** Heavy assistant body variant: large table or large code block with prose. */
function heavyBodyFor(rng: () => number, i: number): string {
  const variant = i % 2;
  if (variant === 0) {
    return `${words(rng, 8, 20)}:\n\n${LARGE_TABLE_SAMPLE}`;
  }
  return `${words(rng, 8, 20)}.\n\n${LARGE_CODE_SAMPLE}\n\n${words(rng, 10, 30)}.`;
}

// ── Context mentions + inline code (rich prose) ────────────────────────────────

/**
 * Resolved metadata for the mock @-mention tokens used by `richBodyFor`. The
 * keys are the raw tokens (text after '@'); a `mockMentionProvider` resolves
 * them so the perf/stress stories render real context-mention pills.
 */
const MENTION_META: Record<string, ChatMentionMeta> = {
  'ChatRoot.tsx': {
    id: 'packages/chat-ui/src/ChatRoot.tsx',
    label: 'ChatRoot.tsx',
    name: 'ChatRoot.tsx',
    kind: 'file',
  },
  'transcript.ts': {
    id: 'packages/chat-ui/src/state/transcript.ts',
    label: 'transcript.ts',
    name: 'transcript.ts',
    kind: 'file',
  },
  'caches.ts': {
    id: 'packages/chat-ui/src/core/caches.ts',
    label: 'caches.ts',
    name: 'caches.ts',
    kind: 'file',
  },
  'issue-42': { id: '42', label: 'issue-42', name: '#42', kind: 'issue' },
  'issue-101': { id: '101', label: 'issue-101', name: '#101', kind: 'issue' },
  layoutBlockStack: {
    id: 'sym:layoutBlockStack',
    label: 'layoutBlockStack',
    name: 'layoutBlockStack',
    kind: 'symbol',
  },
  parseBlocksStreaming: {
    id: 'sym:parseBlocksStreaming',
    label: 'parseBlocksStreaming',
    name: 'parseBlocksStreaming',
    kind: 'symbol',
  },
};

const MENTION_TOKENS = Object.keys(MENTION_META);

/**
 * Synchronous mock mention resolver for the perf/stress stories. Pass to
 * `<ChatRoot mentionProvider={mockMentionProvider} />` so the `@token` spans
 * produced by `richBodyFor` render as context-mention pills.
 */
export const mockMentionProvider: MentionProvider = {
  resolve(token: string): ChatMentionMeta | null {
    return MENTION_META[token] ?? null;
  },
};

/** Inline-code snippets sprinkled into rich paragraphs. */
const INLINE_CODE = [
  'blockMemo',
  'parseBlocks()',
  'virt.setSize',
  'measureEpoch',
  'createMemo',
  'unwrap()',
  'content-visibility',
];

/** Inline markdown links sprinkled into rich paragraphs. */
const LINKS = [
  '[the docs](https://emdash.dev/docs)',
  '[issue tracker](https://github.com/emdash/emdash/issues)',
  '[pretext](https://github.com/chenglou/pretext)',
  '[the streaming RFC](https://emdash.dev/rfc/streaming)',
  '[benchmark results](https://emdash.dev/perf)',
];

/**
 * A lorem paragraph with an inline-code span, a context mention, and an inline
 * link spliced in at pseudo-random positions, ending in a period. Exercises the
 * mixed inline-run layout path (text + code chip + mention pill + link) under
 * pretext measurement.
 */
function richParagraph(rng: () => number, min: number, max: number): string {
  const toks = words(rng, min, max).split(' ');
  toks.splice(Math.floor(rng() * (toks.length + 1)), 0, '`' + pick(rng, INLINE_CODE) + '`');
  toks.splice(Math.floor(rng() * (toks.length + 1)), 0, '@' + pick(rng, MENTION_TOKENS));
  toks.splice(Math.floor(rng() * (toks.length + 1)), 0, pick(rng, LINKS));
  return toks.join(' ') + '.';
}

/**
 * Full-spec markdown document used by the large stress stories (500k / 1M):
 * every heading level (h1–h4), paragraphs with inline code + context mentions +
 * links, unordered (with nesting) and ordered lists, a blockquote, a fenced code
 * block, and a GFM table. Small/large code and table variants alternate by index
 * so block heights vary. Bodies are interned into a fixed pool by
 * `generateMockTranscript` so huge counts stay memory-bounded.
 */
function richBodyFor(rng: () => number, i: number): string {
  const large = i % 2 === 0;
  const parts: string[] = [
    `# ${words(rng, 3, 6)}`,
    '',
    richParagraph(rng, 90, 160),
    '',
    `## ${words(rng, 3, 5)}`,
    '',
    richParagraph(rng, 70, 130),
    '',
    `- ${richParagraph(rng, 6, 14)}`,
    `- ${richParagraph(rng, 6, 14)}`,
    `  - ${richParagraph(rng, 5, 10)}`,
    `  - ${richParagraph(rng, 5, 10)}`,
    `- ${richParagraph(rng, 6, 14)}`,
    '',
    `### ${words(rng, 2, 4)}`,
    '',
    `1. ${richParagraph(rng, 6, 14)}`,
    `2. ${richParagraph(rng, 6, 14)}`,
    `3. ${richParagraph(rng, 6, 14)}`,
    '',
    `> ${richParagraph(rng, 20, 50)}`,
    '',
    `#### ${words(rng, 2, 4)}`,
    '',
    large ? LARGE_CODE_SAMPLE : CODE_SAMPLE,
    '',
    richParagraph(rng, 40, 90),
    '',
    large ? LARGE_TABLE_SAMPLE : TABLE_SAMPLE,
    '',
    richParagraph(rng, 70, 130),
  ];
  return parts.join('\n');
}

/** Thinking text — multi-paragraph reasoning block. */
function thinkingText(rng: () => number): string {
  return [
    words(rng, 15, 40) + '.',
    '',
    words(rng, 20, 50) + '.',
    '',
    `- ${words(rng, 5, 12)}`,
    `- ${words(rng, 5, 12)}`,
    `- ${words(rng, 5, 12)}`,
  ].join('\n');
}

const FILE_PATHS = [
  'packages/chat-ui/src/components/execute/Execute.tsx',
  'packages/chat-ui/src/components/file-op/FileOperation.tsx',
  'apps/emdash-desktop/src/core/features/conversations/browser/chat/chat-store.ts',
  'packages/ui/src/theme/theme.css',
  'packages/chat-ui/src/state/transcript.ts',
  'apps/emdash-desktop/src/main/core/acp/acp-session-manager.ts',
  'packages/chat-ui/src/model.ts',
  'packages/chat-ui/src/components/thinking/Thinking.tsx',
  'packages/chat-ui/src/ChatRoot.tsx',
  'apps/emdash-desktop/src/core/features/workbench/browser/tabs/tab-manager-store.ts',
];

const COMMANDS = [
  'ls -la',
  'pnpm run test',
  'pnpm run build',
  'find . -name "*.ts" -type f',
  'git diff --stat HEAD~1',
  'pnpm --filter @emdash/chat-ui run typecheck',
  'node scripts/db-migrate.js',
  'git log --oneline -20',
];

const GENERIC_TOOL_NAMES = ['search', 'fetch_url', 'think', 'web.run', 'list_files'];
const GENERIC_TOOL_SUMMARIES = [
  'emdash SolidJS component patterns',
  'https://solidjs.com/docs/latest',
  'how to implement a virtualized list',
  'latest ACP protocol specification',
  'packages/chat-ui/src/components',
];

/** Sample plan entries covering all statuses, priorities, and a long wrapping entry. */
const PLAN_ENTRIES: ChatPlanEntry[] = [
  {
    content: 'Analyze existing codebase structure and identify components to modify',
    status: 'completed',
    priority: 'high',
  },
  {
    content:
      'Update `generateMockTranscript` to include diff, thought-role, and plan rows with varied content magnitude',
    status: 'completed',
    priority: 'high',
  },
  {
    content:
      'Add `LARGE_CODE_SAMPLE` and `LARGE_TABLE_SAMPLE` for content-magnitude variety in the perf sweep',
    status: 'in_progress',
    priority: 'medium',
  },
  {
    content: 'Extend cycle length to cover every renderer kind and status',
    status: 'pending',
    priority: 'medium',
  },
  {
    content: 'Add HundredK Storybook story',
    status: 'pending',
    priority: 'low',
  },
  {
    content: 'Run typecheck, lint, and test suite; verify all 121+ tests pass',
    status: 'pending',
    priority: 'high',
  },
];

function pick<T>(rng: () => number, arr: T[]): T {
  return arr[Math.floor(rng() * arr.length)];
}

/** Varied resource-link targets for the mock cycle. */
const RESOURCE_LINK_TARGETS: ResourceTarget[] = [
  { kind: 'workspace-file', path: 'src/core/features/conversations/browser/chat/chat-store.ts' },
  { kind: 'workspace-file', path: 'packages/chat-ui/src/model.ts' },
  { kind: 'external', url: 'https://github.com/anthropics/anthropic-sdk-python' },
  { kind: 'opaque' },
];

const RESOURCE_LINK_NAMES = [
  'chat-store.ts',
  'model.ts',
  'anthropic-sdk-python',
  'resource://internal/plan',
];

/**
 * Generate a deterministic mix of ChatItems covering every current renderer:
 * user messages, thinking (done), file-op (single + multi), execute
 * (done/error), generic tool rows, diff (modify + new-file), thought-role
 * messages, plans, and resource-link rows.
 *
 * All rows have terminal status so the perf stories don't spin live timers.
 * IDs are stable (`msg-0`, `exec-4`, …) — the height cache and ViewStateStore
 * are keyed by item id.
 *
 * The 16-item cycle is:
 *   0  user message
 *   1  thinking done
 *   2  file-op single read
 *   3  assistant message (varied markdown, all 8 variants)
 *   4  execute done/error
 *   5  file-op multi edit (2-8 paths)
 *   6  generic tool
 *   7  diff modify (existing file)
 *   8  diff new file (oldText null)
 *   9  assistant message (code/table heavy)
 *   10 file-op delete or move
 *   11 thought-role message (short reasoning aside)
 *   12 file-op multi edit with error status (terminal)
 *   13 assistant message (heavy: large table or large code)
 *   14 plan (task list with mixed statuses and priorities)
 *   15 resource-link (workspace-file / external / opaque)
 */
export function generateMockTranscript(
  count = 6000,
  seed = 1,
  opts: { richProse?: boolean; bodyPoolSize?: number } = {}
): TranscriptTurn[] {
  const rng = makeRng(seed);
  const items: ChatItem[] = [];

  const CYCLE = 16;

  // For very large counts, intern a fixed pool of long heading/mention/inline-code
  // rich bodies and share string references across assistant rows. This keeps a
  // 1M-item transcript memory-bounded (1M unique multi-KB strings would OOM).
  const richPool = opts.richProse
    ? Array.from({ length: opts.bodyPoolSize ?? 640 }, (_, k) =>
        richBodyFor(makeRng(seed + 1 + k), k)
      )
    : null;
  const assistantBody = (idx: number, phase: number, fallback: () => string): string =>
    richPool ? richPool[(idx + phase) % richPool.length] : fallback();

  for (let i = 0; i < count; i++) {
    const slot = i % CYCLE;

    if (slot === 0) {
      // ── user message ─────────────────────────────────────────────────────
      items.push({
        kind: 'message',
        id: `msg-${i}`,
        role: 'user' as ChatRole,
        text: words(rng, 4, 16) + '?',
      });
    } else if (slot === 1) {
      // ── thinking done ────────────────────────────────────────────────────
      const hasDuration = rng() > 0.2;
      items.push({
        kind: 'thinking',
        id: `think-${i}`,
        status: 'done',
        text: thinkingText(rng),
        startedAt: 0,
        ...(hasDuration ? { durationMs: 1000 + Math.floor(rng() * 9000) } : {}),
      });
    } else if (slot === 2) {
      // ── file-op single read ───────────────────────────────────────────────
      items.push({
        kind: 'file-op',
        id: `fo-${i}`,
        op: 'read' as FileOpKind,
        status: 'done' as ToolStatus,
        ops: [{ path: pick(rng, FILE_PATHS) }],
      });
    } else if (slot === 3) {
      // ── assistant message (all 8 bodyFor variants) ────────────────────────
      items.push({
        kind: 'message',
        id: `msg-${i}`,
        role: 'assistant' as ChatRole,
        text: assistantBody(i, 0, () => bodyFor(rng, i)),
      });
    } else if (slot === 4) {
      // ── execute done (occasional error, ~20% no duration) ─────────────────
      const isError = rng() < 0.1;
      const hasDuration = rng() > 0.2;
      items.push({
        kind: 'execute',
        id: `exec-${i}`,
        command: pick(rng, COMMANDS),
        status: isError ? 'error' : ('done' as ToolStatus),
        startedAt: 0,
        ...(hasDuration ? { durationMs: 500 + Math.floor(rng() * 4500) } : {}),
      });
    } else if (slot === 5) {
      // ── file-op multi edit (2-8 paths) ───────────────────────────────────
      const opCount = 2 + Math.floor(rng() * 7); // 2-8 paths
      const ops = Array.from({ length: opCount }, () => ({ path: pick(rng, FILE_PATHS) }));
      items.push({
        kind: 'file-op',
        id: `fo-${i}`,
        op: 'edit' as FileOpKind,
        status: 'done' as ToolStatus,
        ops,
      });
    } else if (slot === 6) {
      // ── generic tool ─────────────────────────────────────────────────────
      items.push({
        kind: 'tool',
        id: `tool-${i}`,
        name: pick(rng, GENERIC_TOOL_NAMES),
        status: 'done' as ToolStatus,
        inputSummary: pick(rng, GENERIC_TOOL_SUMMARIES),
      });
    } else if (slot === 7) {
      // ── diff modify (existing file) ───────────────────────────────────────
      const path = pick(rng, FILE_PATHS);
      const sample = pick(
        rng,
        DIFF_SAMPLES.filter((s) => s.oldText !== null)
      ) as {
        oldText: string;
        newText: string;
      };
      items.push({
        kind: 'diff',
        id: `diff-${i}:${path}`,
        path,
        oldText: sample.oldText,
        newText: sample.newText,
        status: 'done' as ToolStatus,
      });
    } else if (slot === 8) {
      // ── diff new file (oldText null) ──────────────────────────────────────
      const path = pick(rng, FILE_PATHS);
      const sample = DIFF_SAMPLES.find((s) => s.oldText === null)!;
      items.push({
        kind: 'diff',
        id: `diff-${i}:${path}`,
        path,
        oldText: null,
        newText: sample.newText,
        status: 'done' as ToolStatus,
      });
    } else if (slot === 9) {
      // ── assistant message (varied markdown, offset phase from slot 3) ─────
      items.push({
        kind: 'message',
        id: `msg-${i}`,
        role: 'assistant' as ChatRole,
        text: assistantBody(i, 7, () => bodyFor(rng, i + 3)),
      });
    } else if (slot === 10) {
      // ── file-op delete or move ────────────────────────────────────────────
      const op: FileOpKind = rng() < 0.5 ? 'delete' : 'move';
      items.push({
        kind: 'file-op',
        id: `fo-${i}`,
        op,
        status: 'done' as ToolStatus,
        ops: [{ path: pick(rng, FILE_PATHS) }],
      });
    } else if (slot === 11) {
      // ── thought-role message (short reasoning aside) ───────────────────────
      items.push({
        kind: 'message',
        id: `msg-${i}`,
        role: 'thought' as ChatRole,
        text: words(rng, 10, 35) + '.',
      });
    } else if (slot === 12) {
      // ── file-op multi edit with error status (terminal) ───────────────────
      const opCount = 1 + Math.floor(rng() * 3); // 1-3 paths
      const ops = Array.from({ length: opCount }, () => ({ path: pick(rng, FILE_PATHS) }));
      items.push({
        kind: 'file-op',
        id: `fo-${i}`,
        op: 'edit' as FileOpKind,
        status: 'error' as ToolStatus,
        ops,
      });
    } else if (slot === 13) {
      // ── assistant message (heavy — large table or large code) ──────────────
      items.push({
        kind: 'message',
        id: `msg-${i}`,
        role: 'assistant' as ChatRole,
        text: assistantBody(i, 13, () => heavyBodyFor(rng, i)),
      });
    } else if (slot === 14) {
      // ── plan (task list with mixed statuses and priorities) ───────────────
      items.push({
        kind: 'plan',
        id: `plan-${i}`,
        entries: PLAN_ENTRIES,
      });
    } else {
      // slot === 15: resource-link row (workspace-file / external / opaque)
      const targetIdx = Math.floor(rng() * RESOURCE_LINK_TARGETS.length);
      const target = RESOURCE_LINK_TARGETS[targetIdx];
      const name = RESOURCE_LINK_NAMES[targetIdx];
      items.push({
        kind: 'resource-link',
        id: `rl-${i}`,
        uri:
          target.kind === 'workspace-file'
            ? `file:///${target.path}`
            : target.kind === 'external'
              ? target.url
              : `resource://internal/${i}`,
        name,
        title: target.kind === 'workspace-file' ? name : undefined,
        description: target.kind === 'external' ? 'External documentation reference' : undefined,
        mimeType: name.endsWith('.ts') ? 'text/typescript' : undefined,
        target,
        status: 'done',
      } satisfies ChatResourceLink);
    }
  }

  return items.map((item, index) => ({
    id: `mock-turn-${index}`,
    seq: index,
    initiator: item.kind === 'message' && item.role === 'user' ? 'user' : 'agent',
    items: [{ ...item, seq: 0 } as TranscriptTurn['items'][number]],
    outcome: { kind: 'done' },
  }));
}
