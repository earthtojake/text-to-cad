/**
 * Unit tests for prompt-editor serialization.
 *
 * These tests exercise `serializeDoc` and `serializeMentionLabel` in isolation,
 * building lightweight ProseMirror node structures manually so the test can run
 * in vitest's node project without a browser/DOM.
 *
 * The serialized form for file mentions is now the bracket form:
 *   `@[name](target)` for paths without spaces/parens
 *   `@[name](<target with spaces>)` for paths that require angle-bracket destinations
 */

import type { Node } from '@tiptap/pm/model';
import { describe, expect, it } from 'vitest';
import { serializeDoc, serializeMentionLabel } from './serialize';

// ── Minimal node builders ─────────────────────────────────────────────────────

function makeNode(typeName: string, attrs: Record<string, unknown>, text?: string): Node {
  // Build a lightweight structural mock that satisfies serializeDoc's API surface.
  const children: Node[] = [];
  const forEachFn = (cb: (child: Node) => void) => children.forEach(cb);

  return {
    type: { name: typeName },
    attrs,
    isText: typeName === 'text',
    text: text ?? null,
    forEach: forEachFn,
    textContent: text ?? '',
  } as unknown as Node;
}

function textNode(t: string): Node {
  return makeNode('text', {}, t);
}

/**
 * Build a mention node.
 * @param label - Full path / id stored in the `label` attr (= the serialization target).
 * @param id    - Stable identifier (defaults to label).
 * @param name  - Short display name shown inside the pill (basename).
 */
function mentionNode(label: string, id?: string, name?: string): Node {
  return makeNode('mention', { label, id: id ?? label, kind: 'file', name: name ?? null });
}

function slashCommandNode(name: string): Node {
  return makeNode('slashCommand', { name, id: name });
}

function hardBreakNode(): Node {
  return makeNode('hardBreak', {});
}

/** Build a fake paragraph block containing the given inline nodes. */
function paragraph(...inlines: Node[]): Node {
  const block = makeNode('paragraph', {});
  (block as unknown as { _children: Node[] })._children = inlines;

  const forEachFn = (cb: (child: Node) => void) => {
    (block as unknown as { _children: Node[] })._children.forEach(cb);
  };
  (block as unknown as { forEach: typeof forEachFn }).forEach = forEachFn;
  return block;
}

/** Build a fake doc containing paragraph blocks. */
function makeDoc(...blocks: Node[]): Node {
  const doc = makeNode('doc', {});
  (doc as unknown as { _blocks: Node[] })._blocks = blocks;

  const forEachFn = (cb: (child: Node) => void) => {
    (doc as unknown as { _blocks: Node[] })._blocks.forEach(cb);
  };
  (doc as unknown as { forEach: typeof forEachFn }).forEach = forEachFn;
  return doc;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('serializeDoc', () => {
  it('serializes plain text', () => {
    const doc = makeDoc(paragraph(textNode('Hello world')));
    expect(serializeDoc(doc)).toBe('Hello world');
  });

  it('serializes a file mention node as @[label](target) bracket form', () => {
    // label == id == 'src/foo.ts', no name
    const doc = makeDoc(
      paragraph(textNode('Fix '), mentionNode('src/foo.ts'), textNode(' please'))
    );
    expect(serializeDoc(doc)).toBe('Fix @[src/foo.ts](src/foo.ts) please');
  });

  it('serializes a slash command node as /name', () => {
    const doc = makeDoc(paragraph(slashCommandNode('review'), textNode(' this')));
    expect(serializeDoc(doc)).toBe('/review this');
  });

  it('serializes a hard break as \\n within a paragraph', () => {
    const doc = makeDoc(paragraph(textNode('line1'), hardBreakNode(), textNode('line2')));
    expect(serializeDoc(doc)).toBe('line1\nline2');
  });

  it('joins multiple paragraphs with \\n', () => {
    const doc = makeDoc(paragraph(textNode('para1')), paragraph(textNode('para2')));
    expect(serializeDoc(doc)).toBe('para1\npara2');
  });

  it('trims trailing newlines', () => {
    const doc = makeDoc(paragraph(textNode('hello')), paragraph(textNode('')));
    expect(serializeDoc(doc)).toBe('hello');
  });

  it('serializes a complex mixed doc correctly', () => {
    const doc = makeDoc(
      paragraph(
        textNode('Add '),
        mentionNode('README.md'),
        textNode(' and run '),
        slashCommandNode('lint')
      ),
      paragraph(textNode('Thanks'))
    );
    expect(serializeDoc(doc)).toBe('Add @[README.md](README.md) and run /lint\nThanks');
  });

  it('falls back to id if label is null for a mention', () => {
    const node = makeNode('mention', { label: null, id: 'some-id', kind: 'file' });
    const doc = makeDoc(paragraph(node));
    // label = null ?? id = 'some-id', name = undefined -> bracket form
    expect(serializeDoc(doc)).toBe('@[some-id](some-id)');
  });

  it('uses name as the bracket label, label as the target', () => {
    // name='chat-composer.tsx' (display), label='src/components/chat-composer.tsx' (target)
    const doc = makeDoc(
      paragraph(mentionNode('src/components/chat-composer.tsx', undefined, 'chat-composer.tsx'))
    );
    expect(serializeDoc(doc)).toBe('@[chat-composer.tsx](src/components/chat-composer.tsx)');
  });
});

// ── serializeMentionLabel ────────────────────────────────────────────────────

describe('serializeMentionLabel', () => {
  it('emits @[label](target) bracket form for a space-free file path', () => {
    expect(serializeMentionLabel('src/auth/jwt.ts', 'file')).toBe(
      '@[src/auth/jwt.ts](src/auth/jwt.ts)'
    );
  });

  it('emits angle-bracket destination for a file path containing spaces', () => {
    expect(serializeMentionLabel('/Users/me/My Project/foo.ts', 'file')).toBe(
      '@[/Users/me/My Project/foo.ts](</Users/me/My Project/foo.ts>)'
    );
  });

  it('emits angle-bracket destination for a path with parentheses', () => {
    expect(serializeMentionLabel('/tmp/foo (copy).ts', 'file')).toBe(
      '@[/tmp/foo (copy).ts](</tmp/foo (copy).ts>)'
    );
  });

  it('escapes a non-file kind when the label has spaces', () => {
    expect(serializeMentionLabel('my issue label', 'issue')).toBe(
      '@[my issue label](<my issue label>)'
    );
    expect(serializeMentionLabel('my issue label', null)).toBe('@my issue label');
  });

  it('emits @[label](target) for an absolute path with no special chars', () => {
    expect(serializeMentionLabel('/Users/me/projects/emdash/src/main.ts', 'file')).toBe(
      '@[/Users/me/projects/emdash/src/main.ts](/Users/me/projects/emdash/src/main.ts)'
    );
  });

  it('uses name as bracket label when provided', () => {
    expect(serializeMentionLabel('/path/to/file.ts', 'file', 'file.ts')).toBe(
      '@[file.ts](/path/to/file.ts)'
    );
  });

  it('uses name as bracket label with angle-bracket target for spaced paths', () => {
    expect(serializeMentionLabel('/Users/me/My Project/foo.ts', 'file', 'foo.ts')).toBe(
      '@[foo.ts](</Users/me/My Project/foo.ts>)'
    );
  });
});

// ── Shared grammar tests (stringifyMention) ───────────────────────────────────
// These are co-located here since serializeMentionLabel delegates to stringifyMention.
// The canonical grammar tests live in packages/shared/src/markdown/mention-grammar.test.ts.
