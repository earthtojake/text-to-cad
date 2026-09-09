/**
 * parse.test.ts — unit tests for the remark-based markdown parser.
 *
 * Covers:
 *  - Bracket @[label](target) form (new canonical form for file mentions)
 *  - Bare @token form (legacy agent output, still supported)
 *  - AT_TOKEN_RE trailing-dot stripping
 *  - /command slash tokens
 *  - Rule, blockquote, and block structural tests
 *
 * Runs in jsdom because parse.ts → remark-parse → decode-named-character-reference
 * accesses document at module load time.
 *
 * @vitest-environment jsdom
 */

import { describe, expect, it } from 'vitest';
import type { CommandProvider } from './command-provider';
import type { InlineMention, InlineRun, InlineText, ProseBlock, RuleBlock } from './document';
import type { MentionProvider } from './mention-provider';
import { parseMarkdownToBlocks } from './parse';

// Stub provider that resolves any token it receives as a 'file' mention so
// every matched token becomes a pill without needing a registry of known paths.
const echoProvider: MentionProvider = {
  resolve: (token) => ({ id: token, label: token, kind: 'file' }),
};

const nullProvider: MentionProvider = { resolve: () => null };

function firstProseRuns(text: string, mentionProvider?: MentionProvider): InlineRun[] {
  const blocks = parseMarkdownToBlocks('t', text, mentionProvider ?? echoProvider);
  const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
  return prose?.runs ?? [];
}

/** Display labels (m.name ?? m.label) of mention runs. */
function mentionLabels(runs: InlineRun[]): string[] {
  return runs.filter((r): r is InlineMention => r.kind === 'mention').map((r) => r.label);
}

/** Stable ids (target path) of mention runs. */
function mentionIds(runs: InlineRun[]): Array<string | undefined> {
  return runs.filter((r): r is InlineMention => r.kind === 'mention').map((r) => r.id);
}

function textSegments(runs: InlineRun[]): string[] {
  return runs.filter((r): r is InlineText => r.kind === 'text').map((r) => r.text);
}

// ── Bracket @[label](target) form ─────────────────────────────────────────────

describe('bracket @[label](target) mention form', () => {
  it('resolves @[file.ts](/path/to/file.ts) to a single mention run', () => {
    const runs = firstProseRuns('@[file.ts](/path/to/file.ts)');
    expect(mentionLabels(runs)).toEqual(['file.ts']);
    expect(mentionIds(runs)).toEqual(['/path/to/file.ts']);
    // No stray text runs
    expect(textSegments(runs).filter((t) => t.trim())).toHaveLength(0);
  });

  it('resolves a bracket mention with angle-bracket destination (path with spaces)', () => {
    const runs = firstProseRuns('@[a](<path with spaces/a.ts>)');
    expect(mentionLabels(runs)).toEqual(['a']);
    expect(mentionIds(runs)).toEqual(['path with spaces/a.ts']);
  });

  it('resolves an absolute path with spaces using angle brackets', () => {
    const runs = firstProseRuns('@[foo.ts](</Users/me/My Project/foo.ts>)');
    expect(mentionLabels(runs)).toEqual(['foo.ts']);
    expect(mentionIds(runs)).toEqual(['/Users/me/My Project/foo.ts']);
  });

  it('resolves a bracket mention preceded by prose text', () => {
    const runs = firstProseRuns('See @[foo.ts](/path/foo.ts) for details');
    expect(mentionLabels(runs)).toEqual(['foo.ts']);
    expect(mentionIds(runs)).toEqual(['/path/foo.ts']);
    expect(textSegments(runs).some((t) => t.includes('See'))).toBe(true);
    expect(textSegments(runs).some((t) => t.includes('for details'))).toBe(true);
  });

  it('resolves a bare and a bracket mention in the same paragraph', () => {
    const runs = firstProseRuns('Look at @src/foo.ts and @[bar.ts](/path/bar.ts)');
    expect(mentionLabels(runs)).toEqual(['src/foo.ts', 'bar.ts']);
    expect(mentionIds(runs)).toEqual(['src/foo.ts', '/path/bar.ts']);
  });

  it('still folds bracket form when provider returns null (bracket = explicitly authored)', () => {
    const runs = firstProseRuns('@[file.ts](/path/to/file.ts)', nullProvider);
    // The fold always happens for bracket form regardless of provider resolution
    expect(runs.filter((r) => r.kind === 'mention')).toHaveLength(1);
    expect(mentionLabels(runs)).toEqual(['file.ts']);
  });

  it('does not fold when no mention provider is supplied', () => {
    // Without a provider, bracket links appear as linked text (not pills)
    const blocks = parseMarkdownToBlocks('t', '@[file.ts](/path/to/file.ts)');
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    const mentions = (prose?.runs ?? []).filter((r) => r.kind === 'mention');
    expect(mentions).toHaveLength(0);
  });
});

// ── Trailing dot stripping ─────────────────────────────────────────────────

describe('bare @token trailing-dot stripping', () => {
  it('strips a sentence-final dot: @hello.ts. -> token hello.ts', () => {
    const runs = firstProseRuns('Edit @hello.ts.');
    expect(mentionLabels(runs)).toEqual(['hello.ts']);
    // The trailing period should appear as a plain text run after the mention
    const texts = textSegments(runs);
    expect(texts.some((t) => t.includes('.'))).toBe(true);
  });

  it('strips trailing dot from a path mention: @src/auth/jwt.ts.', () => {
    const runs = firstProseRuns('See @src/auth/jwt.ts.');
    expect(mentionLabels(runs)).toEqual(['src/auth/jwt.ts']);
  });

  it('does not strip a non-terminal dot (internal dot preserved)', () => {
    const runs = firstProseRuns('@src/auth/jwt.ts is new');
    expect(mentionLabels(runs)).toEqual(['src/auth/jwt.ts']);
  });

  it('handles two sentence-final mentions: @a.ts. and @b.ts.', () => {
    const runs = firstProseRuns('@a.ts. and @b.ts.');
    expect(mentionLabels(runs)).toEqual(['a.ts', 'b.ts']);
  });
});

// ── Internal and leading dots preserved ───────────────────────────────────

describe('bare @token dot preservation', () => {
  it('preserves internal dots in file path: @src/auth/jwt.ts', () => {
    const runs = firstProseRuns('@src/auth/jwt.ts');
    expect(mentionLabels(runs)).toEqual(['src/auth/jwt.ts']);
  });

  it('preserves leading dot (dotfile): @.gitignore', () => {
    const runs = firstProseRuns('Ignored @.gitignore file');
    expect(mentionLabels(runs)).toEqual(['.gitignore']);
  });

  it('preserves multiple internal dots: @foo.bar.baz', () => {
    const runs = firstProseRuns('@foo.bar.baz');
    expect(mentionLabels(runs)).toEqual(['foo.bar.baz']);
  });
});

// ── Other bare token shapes ──────────────────────────────────────────────

describe('bare @token standard shapes', () => {
  it('matches issue ref: @issue-42', () => {
    const runs = firstProseRuns('Closes @issue-42');
    expect(mentionLabels(runs)).toEqual(['issue-42']);
  });

  it('matches symbol with parens: @handleSubmit()', () => {
    const runs = firstProseRuns('Call @handleSubmit()');
    expect(mentionLabels(runs)).toEqual(['handleSubmit()']);
  });

  it('matches multiple mentions in one paragraph', () => {
    const runs = firstProseRuns('@foo.ts and @bar-baz and @qux()');
    expect(mentionLabels(runs)).toEqual(['foo.ts', 'bar-baz', 'qux()']);
  });

  it('returns no mentions when provider returns null for bare tokens', () => {
    const blocks = parseMarkdownToBlocks('t', '@hello.ts', nullProvider);
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    const mentions = (prose?.runs ?? []).filter((r) => r.kind === 'mention');
    expect(mentions).toHaveLength(0);
  });
});

// ── /command slash tokens ─────────────────────────────────────────────────

describe('/command slash tokens', () => {
  it('resolves /review at start of line', () => {
    const commandProvider: CommandProvider = {
      resolve: (name) => (name === 'review' ? { name: 'review' } : null),
    };
    const blocks = parseMarkdownToBlocks('t', '/review the changes', undefined, commandProvider);
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    const mentions = (prose?.runs ?? []).filter((r): r is InlineMention => r.kind === 'mention');
    expect(mentions).toHaveLength(1);
    expect(mentions[0].label).toBe('/review');
    expect(mentions[0].tone).toBe('command');
  });

  it('does not match a slash in the middle of a path', () => {
    const commandProvider: CommandProvider = {
      resolve: (name) => ({ name }),
    };
    // Bare text — the slash in "path/to" is NOT at line start or after whitespace
    // so SLASH_PATTERN should not match it.
    const blocks = parseMarkdownToBlocks('t', 'See path/to/file', undefined, commandProvider);
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    const mentions = (prose?.runs ?? []).filter((r) => r.kind === 'mention');
    expect(mentions).toHaveLength(0);
  });
});

// ── Rule block ──────────────────────────────────────────────────────────────

describe('thematicBreak → rule block', () => {
  it('emits a rule block for ---', () => {
    const blocks = parseMarkdownToBlocks('t', '---');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe('rule');
  });

  it('rule block has a stable id', () => {
    const blocks = parseMarkdownToBlocks('t', 'before\n\n---\n\nafter');
    const rule = blocks.find((b): b is RuleBlock => b.kind === 'rule');
    expect(rule).toBeDefined();
    expect(rule!.id).toMatch(/^t#/);
  });

  it('prose blocks appear before and after the rule', () => {
    const blocks = parseMarkdownToBlocks('t', 'before\n\n---\n\nafter');
    expect(blocks[0].kind).toBe('prose');
    expect(blocks[1].kind).toBe('rule');
    expect(blocks[2].kind).toBe('prose');
  });

  it('does not emit a prose block for ---', () => {
    const blocks = parseMarkdownToBlocks('t', '---');
    const prose = blocks.find((b) => b.kind === 'prose');
    expect(prose).toBeUndefined();
  });
});

// ── Blockquote → quote variant ───────────────────────────────────────────────

describe('blockquote paragraphs → variant: quote', () => {
  it('blockquote paragraph emits variant: quote', () => {
    const blocks = parseMarkdownToBlocks('t', '> Hello world');
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    expect(prose?.variant).toBe('quote');
  });

  it('regular paragraph emits variant: body', () => {
    const blocks = parseMarkdownToBlocks('t', 'Hello world');
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    expect(prose?.variant).toBe('body');
  });

  it('nested blockquote paragraphs also emit variant: quote', () => {
    const blocks = parseMarkdownToBlocks('t', '> > Nested');
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    expect(prose?.variant).toBe('quote');
  });

  it('blockquote depth is incremented', () => {
    const blocks = parseMarkdownToBlocks('t', '> Hello');
    const prose = blocks.find((b): b is ProseBlock => b.kind === 'prose');
    expect(prose?.depth).toBe(1);
  });
});
