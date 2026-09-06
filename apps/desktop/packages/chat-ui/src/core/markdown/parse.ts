/**
 * parse — Markdown string to Block[].
 *
 * Converts raw markdown text into the chat-ui document model (Block[]) using
 * a unified pipeline:
 *   1. remarkParse  — tokenise / parse the string into an mdast Root
 *   2. remarkGfm    — tables, strikethrough, task-lists, autolinks
 *   3. remarkMath   — block-level and inline LaTeX / KaTeX
 *   4. remarkInlineMentions — fold `@[label](target)` links and split `@bare` /
 *      `/command` text spans into `MdastMention` nodes (reads per-call data
 *      from the VFile so the processor can be built once at module scope)
 *
 * The transformed mdast tree is then walked by `blockToBlocks` which converts
 * it into the flat `Block[]` consumed by the chat-ui renderer.
 *
 * Identity-stable caching of parsed Block arrays lives in the per-instance
 * `ChatCaches.parseBlocks` bundle (core/caches.ts), not here.
 *
 * This module is PURE: no geometry, no pretext/fonts, no DOM imports.
 */

import type {
  BlockContent,
  DefinitionContent,
  Heading,
  Image,
  InlineCode,
  Link,
  ListItem,
  Parent,
  PhrasingContent,
  Root,
  TableCell,
  TableRow,
} from 'mdast';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import remarkParse from 'remark-parse';
import { unified } from 'unified';
import { VFile } from 'vfile';
import type { CommandProvider } from './command-provider';
import type {
  Block,
  BlockId,
  InlineBreak,
  InlineCode as ICode,
  InlineMention,
  InlineRun,
  InlineText,
  ProseBlock,
  ProseVariant,
  RuleBlock,
  TableBlock,
} from './document';
import type { MdastMention } from './mdast-mention';
import type { MentionProvider } from './mention-provider';
import { remarkInlineMentions } from './remark-inline-mentions';
import type { ParseData } from './remark-inline-mentions';

// ── Shared processor instance ────────────────────────────────────────────────
//
// Built once at module scope. Per-call data (providers, uri, messageId, startN)
// is threaded through the VFile's `data` field so this instance is stateless.

const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkMath)
  .use(remarkInlineMentions)
  .freeze();

// ── Inline phrasing → InlineRun[] ───────────────────────────────────────────

function phrasingsToRuns(
  nodes: PhrasingContent[],
  opts: { bold?: boolean; italic?: boolean; strike?: boolean; href?: string } = {}
): InlineRun[] {
  const runs: InlineRun[] = [];

  for (const rawNode of nodes) {
    // MdastMention nodes are injected by the remarkInlineMentions plugin and
    // are not in the standard PhrasingContent union — handle them first.
    if ((rawNode as { type: string }).type === 'mention') {
      const m = rawNode as unknown as MdastMention;
      // Slash commands keep their '/name' label; file/issue mentions use the
      // short display name (m.name) when available, falling back to label.
      const displayLabel = m.tone === 'command' ? m.label : (m.name ?? m.label);
      runs.push({
        kind: 'mention',
        label: displayLabel,
        id: m.target ?? m.label,
        name: m.name,
        mentionKind: m.mentionKind,
        iconClass: m.iconClass,
        iconUrl: m.iconUrl,
        tone: m.tone,
      } satisfies InlineMention);
      continue;
    }

    const node = rawNode as PhrasingContent;

    switch (node.type) {
      case 'text': {
        // Split on literal newlines (soft breaks inside a paragraph) and emit
        // an InlineBreak between each segment so layoutProse can force a new line.
        const segments = node.value.split('\n');
        for (let i = 0; i < segments.length; i++) {
          if (i > 0) runs.push({ kind: 'break' } satisfies InlineBreak);
          const seg = segments[i];
          if (seg.length > 0) {
            runs.push({
              kind: 'text',
              text: seg,
              bold: opts.bold,
              italic: opts.italic,
              strike: opts.strike,
              href: opts.href,
            } satisfies InlineText);
          }
        }
        break;
      }

      case 'inlineCode': {
        runs.push({ kind: 'code', text: (node as InlineCode).value } satisfies ICode);
        break;
      }

      case 'strong': {
        runs.push(
          ...phrasingsToRuns((node as Parent).children as PhrasingContent[], {
            ...opts,
            bold: true,
          })
        );
        break;
      }

      case 'emphasis': {
        runs.push(
          ...phrasingsToRuns((node as Parent).children as PhrasingContent[], {
            ...opts,
            italic: true,
          })
        );
        break;
      }

      case 'delete': {
        runs.push(
          ...phrasingsToRuns((node as Parent).children as PhrasingContent[], {
            ...opts,
            strike: true,
          })
        );
        break;
      }

      // Hard break (two trailing spaces or backslash before newline in markdown).
      case 'break': {
        runs.push({ kind: 'break' } satisfies InlineBreak);
        break;
      }

      case 'link': {
        const link = node as Link;
        runs.push(
          ...phrasingsToRuns(link.children as PhrasingContent[], { ...opts, href: link.url })
        );
        break;
      }

      case 'image': {
        // Images inside prose are treated as inline text (alt text); the slot path
        // for block-level images is handled in blockToBlocks via the 'image' mdast type.
        const img = node as Image;
        runs.push({ kind: 'text', text: img.alt || '[image]', href: img.url } satisfies InlineText);
        break;
      }

      // mdast extension — math inline (remark-math attaches 'inlineMath' type)
      case 'inlineMath': {
        const run: InlineMention = { kind: 'mention', label: '∑ math', tone: 'math' };
        runs.push(run);
        break;
      }

      default:
        // Ignore unknown inline node types (html, footnote references, …)
        break;
    }
  }

  return runs;
}

// ── mdast node → Block[] ────────────────────────────────────────────────────

function blockToBlocks(
  node: BlockContent | DefinitionContent,
  messageId: string,
  counter: { n: number },
  depth = 0,
  inQuote = false
): Block[] {
  const nextId = (): BlockId => `${messageId}#${counter.n++}`;
  const blocks: Block[] = [];

  switch (node.type) {
    case 'paragraph': {
      const parent = node as Parent;
      const runs = phrasingsToRuns(parent.children as PhrasingContent[]);
      if (runs.length > 0) {
        blocks.push({
          kind: 'prose',
          id: nextId(),
          variant: inQuote ? 'quote' : 'body',
          runs,
          depth,
        } satisfies ProseBlock);
      }
      break;
    }

    case 'heading': {
      const h = node as Heading;
      const variant = `h${h.depth}` as ProseVariant;
      const runs = phrasingsToRuns(h.children as PhrasingContent[]);
      if (runs.length > 0) {
        blocks.push({
          kind: 'prose',
          id: nextId(),
          variant,
          runs,
        } satisfies ProseBlock);
      }
      break;
    }

    case 'blockquote': {
      for (const child of (node as Parent).children) {
        blocks.push(...blockToBlocks(child as BlockContent, messageId, counter, depth + 1, true));
      }
      break;
    }

    case 'list': {
      const list = node as Parent;
      for (const child of list.children) {
        const item = child as ListItem;
        for (const itemChild of (item as Parent).children) {
          if (itemChild.type === 'paragraph') {
            const runs = phrasingsToRuns((itemChild as Parent).children as PhrasingContent[]);
            if (runs.length > 0) {
              blocks.push({
                kind: 'prose',
                id: nextId(),
                variant: 'list-item',
                runs,
                depth,
              } satisfies ProseBlock);
            }
          } else {
            blocks.push(
              ...blockToBlocks(itemChild as BlockContent, messageId, counter, depth + 1, false)
            );
          }
        }
      }
      break;
    }

    case 'code': {
      const codeLang = node.lang?.toLowerCase();
      if (codeLang === 'mermaid' || codeLang === 'mmd') {
        blocks.push({
          kind: 'mermaid',
          id: nextId(),
          source: node.value,
        });
      } else {
        blocks.push({
          kind: 'code',
          id: nextId(),
          code: node.value,
          lang: node.lang ?? undefined,
        });
      }
      break;
    }

    case 'table': {
      const tableNode = node as Parent;
      const allRows = tableNode.children.map((row) =>
        (row as TableRow).children.map((cell) => {
          const cellNode = cell as TableCell & Parent;
          // Table cell text is plain: @mentions and /commands become their label text
          return phrasingsToRuns(cellNode.children as PhrasingContent[])
            .map((r) => ('text' in r ? r.text : 'label' in r ? r.label : ''))
            .join('');
        })
      );
      const [header = [], ...rows] = allRows;
      blocks.push({
        kind: 'table',
        id: nextId(),
        header,
        rows,
      } satisfies TableBlock);
      break;
    }

    case 'thematicBreak': {
      blocks.push({
        kind: 'rule',
        id: nextId(),
      } satisfies RuleBlock);
      break;
    }

    // remark-math adds 'math' (block-level) — rendered as plain text for now.
    case 'math': {
      blocks.push({
        kind: 'prose',
        id: nextId(),
        variant: 'body',
        runs: [{ kind: 'text', text: node.value }],
      } satisfies ProseBlock);
      break;
    }

    default:
      // Unknown block types — skip
      break;
  }

  return blocks;
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Parse a markdown string into a stable `Block[]` that both the measurement
 * engine and block renderer components consume.
 *
 * The unified pipeline (remarkParse → remarkGfm → remarkMath →
 * remarkInlineMentions) runs first, folding `@[label](target)` links and
 * splitting `@bare` / `/command` text spans into `MdastMention` nodes. The
 * resulting mdast tree is then compiled to `Block[]` by `blockToBlocks`.
 *
 * Block IDs are in the form `${messageId}#${index}` where `index` is the
 * position in the flat block list produced by the parse. IDs are stable as
 * long as the full text is re-parsed (not incrementally mutated). A streaming
 * message is kept as a single prose unit until `finalizeTurn()` freezes the
 * text and re-parses with the complete content.
 *
 * @param messageId       - Stable item id used as the block-id prefix.
 * @param markdown        - Raw markdown string to parse.
 * @param mentionProvider - Optional @-mention resolver; when supplied, `@token` spans
 *                          that resolve to metadata are emitted as InlineMention runs.
 * @param commandProvider - Optional /-command resolver; when supplied, `/token` spans
 *                          that resolve to metadata are emitted as InlineMention runs
 *                          with `tone: 'command'`.
 * @param startN          - Starting block counter (default 0). Used by the incremental
 *                          streaming parser to assign continuation IDs when parsing tail
 *                          chunks so they join seamlessly with the stable prefix IDs.
 * @param uri             - Conversation URI forwarded to provider `.resolve()` so
 *                          a global provider can scope resolution to the right context.
 */
export function parseMarkdownToBlocks(
  messageId: string,
  markdown: string,
  mentionProvider?: MentionProvider,
  commandProvider?: CommandProvider,
  startN = 0,
  uri?: string
): Block[] {
  if (!markdown.trim()) return [];

  const data: ParseData = { messageId, startN, uri, mentionProvider, commandProvider };
  const file = new VFile({ value: markdown, data: data as unknown as Record<string, unknown> });

  // Parse the markdown into an mdast tree, then run transforms (including
  // our mention-folding plugin which reads providers from file.data).
  const tree = processor.runSync(processor.parse(file), file) as Root;

  const counter = { n: startN };
  const blocks: Block[] = [];

  for (const child of tree.children) {
    blocks.push(...blockToBlocks(child as BlockContent | DefinitionContent, messageId, counter));
  }

  return blocks;
}

// ── Block normalization helpers ───────────────────────────────────────────────

/**
 * Demote every heading variant (h1–h6) to `'body'` so the text measures and
 * renders at body size/weight. Inline runs (bold, code, links, mentions) are
 * preserved untouched.
 *
 * Use when large headings are not appropriate for the rendering context (e.g.
 * the reasoning / thinking row where AI-generated section headers would be
 * visually disruptive).
 *
 * @param blocks - Block array to transform (not mutated; returns a new array).
 */
export function flattenBlockHeadings(blocks: Block[]): Block[] {
  return blocks.map((b) =>
    b.kind === 'prose' && b.variant !== 'body' && b.variant !== 'list-item' && b.variant !== 'quote'
      ? { ...b, variant: 'body' as const }
      : b
  );
}
