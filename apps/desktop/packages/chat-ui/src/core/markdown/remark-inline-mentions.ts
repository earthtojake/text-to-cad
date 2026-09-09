/**
 * remarkInlineMentions — unified transform plugin that rewrites inline mention
 * and command spans to `MdastMention` nodes.
 *
 * Runs two passes after remark's parse phase:
 *
 * Pass 1 — bracket fold: find `link` nodes whose immediately-preceding `text`
 *   sibling ends with `@`. Strip the `@` from the text, resolve the link URL
 *   via the mentionProvider, and replace the link with a `mention` node.
 *   This handles `@[label](target)` and `@[label](<path with spaces>)`.
 *
 * Pass 2 — text split: walk `text` nodes and split any `@bare` or `/command`
 *   spans into separate `mention` nodes, resolving via the providers.
 *   Inherits the same boundary rules as the old `splitAtMentions` helper.
 *
 * Per-call data (providers, uri) is read from `file.data` so the processor
 * can be built once at module scope and reused across calls.
 */

import { AT_BARE_PATTERN, SLASH_PATTERN } from '@emdash/shared/markdown';
import type { Link, Parent, Root, Text } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { SKIP, visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import type { CommandProvider } from './command-provider';
import type { MdastMention } from './mdast-mention';
import type { MentionProvider } from './mention-provider';

/** Shape of the per-call data threaded through the VFile. */
export interface ParseData {
  messageId: string;
  startN: number;
  uri?: string;
  mentionProvider?: MentionProvider;
  commandProvider?: CommandProvider;
}

type AnyNode = Text | MdastMention;

export function remarkInlineMentions() {
  return (tree: Root, file: VFile): void => {
    const { mentionProvider, commandProvider, uri } = file.data as unknown as ParseData;

    // ── Pass 1: fold @[label](target) links into mention nodes ──────────────
    //
    // remark has already parsed `[label](target)` as a `link` node; we detect
    // the `@` prefix by inspecting the immediately-preceding text sibling.
    if (mentionProvider) {
      visit(tree, 'link', (node: Link, index: number | undefined, parent: Parent | undefined) => {
        if (index == null || !parent) return;
        const prev = parent.children[index - 1];
        if (prev?.type !== 'text') return;
        const textNode = prev as Text;
        if (!textNode.value.endsWith('@')) return;

        // Strip the trailing '@' from the preceding text.
        textNode.value = textNode.value.slice(0, -1);

        const label = toString(node);
        const target = node.url; // angle-bracket wrapping already stripped by remark
        const meta = mentionProvider.resolve(target, uri) ?? null;

        const mention: MdastMention = {
          type: 'mention',
          syntax: 'at-bracket',
          label,
          target,
          name: meta?.name ?? label,
          mentionKind: meta?.kind ?? 'file',
          iconClass: meta?.iconClass,
          iconUrl: meta?.iconUrl,
        };

        // Replace the link node with the mention node.
        parent.children[index] = mention as unknown as (typeof parent.children)[number];
        return SKIP;
      });
    }

    // ── Pass 2: split text nodes on @bare and /command ──────────────────────
    visit(tree, 'text', (node: Text, index: number | undefined, parent: Parent | undefined) => {
      if (index == null || !parent) return;
      const replacements = splitTextNode(node.value, mentionProvider, commandProvider, uri);
      if (replacements.length === 1 && (replacements[0] as { type: string }).type === 'text')
        return;
      parent.children.splice(index, 1, ...(replacements as typeof parent.children));
      // Return the new index to skip re-visiting the injected nodes.
      return [SKIP, index + replacements.length] as [typeof SKIP, number];
    });
  };
}

/**
 * Split a text value on `@bare` and `/command` patterns, returning a mix of
 * Text and MdastMention nodes. Returns a single-element array with the
 * original text node when nothing is matched.
 */
function splitTextNode(
  value: string,
  mentionProvider: MentionProvider | undefined,
  commandProvider: CommandProvider | undefined,
  uri: string | undefined
): AnyNode[] {
  const hasAt = mentionProvider && value.includes('@');
  const hasSlash = commandProvider && value.includes('/');
  if (!hasAt && !hasSlash) return [{ type: 'text', value }];

  type Hit = { index: number; length: number; node: MdastMention };
  const hits: Hit[] = [];

  if (mentionProvider) {
    const re = new RegExp(AT_BARE_PATTERN, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(value)) !== null) {
      const token = m[1];
      const meta = mentionProvider.resolve(token, uri);
      if (!meta) continue;
      hits.push({
        index: m.index,
        length: m[0].length,
        node: {
          type: 'mention',
          syntax: 'at-bare',
          label: meta.label,
          target: meta.id,
          name: meta.name,
          mentionKind: meta.kind,
          iconClass: meta.iconClass,
          iconUrl: meta.iconUrl,
        },
      });
    }
  }

  if (commandProvider) {
    const re = new RegExp(SLASH_PATTERN, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(value)) !== null) {
      const token = m[1];
      const meta = commandProvider.resolve(token, uri);
      if (!meta) continue;
      // The full match may include a leading whitespace (the lookbehind alternative);
      // skip it so the slice starts at the actual '/'.
      const prefixLen = m[0].length - token.length - 1;
      hits.push({
        index: m.index + prefixLen,
        length: 1 + token.length,
        node: {
          type: 'mention',
          syntax: 'slash',
          label: `/${meta.name}`,
          tone: 'command',
          name: meta.name,
        },
      });
    }
  }

  if (hits.length === 0) return [{ type: 'text', value }];

  hits.sort((a, b) => a.index - b.index);

  const result: AnyNode[] = [];
  let last = 0;

  for (const hit of hits) {
    if (hit.index > last) {
      result.push({ type: 'text', value: value.slice(last, hit.index) });
    }
    result.push(hit.node);
    last = hit.index + hit.length;
  }

  if (last < value.length) {
    result.push({ type: 'text', value: value.slice(last) });
  }

  return result;
}
