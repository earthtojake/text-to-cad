/**
 * @ mention extension.
 *
 * Produces atomic inline `mention` nodes with attrs
 * { id, label, name, kind, pending, serializedText }.
 *  - `id`    – stable identifier (e.g. file path).
 *  - `label` – full-path text serialized as `@label` in clipboard/plain text.
 *  - `name`  – short display name shown inside the pill (basename by default).
 *  - `kind`  – semantic category (file | issue | symbol | custom).
 *
 * The pill visual is rendered by MentionPill via ReactNodeViewRenderer.
 * Serializes to `@label` for bare-safe labels, or `@"label"` for file mentions
 * whose path contains spaces or other characters outside the tokenizer's char class.
 *
 * The actual popup rendering is handled externally via the `suggestion.render`
 * callback injected by PromptEditor.
 */

import { Mention as TipTapMention } from '@tiptap/extension-mention';
import type { NodeViewProps } from '@tiptap/react';
import { ReactNodeViewRenderer } from '@tiptap/react';
import type { SuggestionOptions } from '@tiptap/suggestion';
import React from 'react';
import { MentionPill } from '../mention-pill';
import { serializeMentionLabel } from '../serialize';
import type { MentionItem, RenderMentionIcon } from '../types';

export function buildMentionExtension(
  // Omit the Selected generic (defaults to TipTap's internal type) so our richer
  // MentionItem attrs don't conflict with TipTap's narrower built-in MentionNodeAttrs type.
  suggestion: Partial<SuggestionOptions<MentionItem>>,
  options: { renderMentionIcon?: RenderMentionIcon } = {}
) {
  return TipTapMention.extend({
    name: 'mention',
    inline: true,
    group: 'inline',
    atom: true,
    addAttributes() {
      return {
        id: { default: null },
        label: { default: null },
        name: { default: null },
        kind: { default: 'custom' },
        pending: { default: false },
        serializedText: { default: null },
      };
    },
    addNodeView() {
      return ReactNodeViewRenderer(
        (props: NodeViewProps) =>
          React.createElement(MentionPill, {
            ...props,
            renderMentionIcon: options.renderMentionIcon,
          }),
        { as: 'span' }
      );
    },
  }).configure({
    HTMLAttributes: { class: 'mention-chip' },
    renderText({ node }) {
      const serializedText = node.attrs.serializedText as string | null;
      if (serializedText) return serializedText;
      const label = (node.attrs.label as string | null) ?? (node.attrs.id as string | null) ?? '';
      const name = node.attrs.name as string | null;
      return serializeMentionLabel(label, node.attrs.kind as string | null, name);
    },
    renderHTML({ node }) {
      const serializedText = node.attrs.serializedText as string | null;
      const label = (node.attrs.label as string | null) ?? (node.attrs.id as string | null) ?? '';
      const name = node.attrs.name as string | null;
      return [
        'span',
        {
          'data-type': 'mention',
          'data-id': node.attrs.id as string,
          'data-label': node.attrs.label as string,
          'data-name': (node.attrs.name as string | null) ?? '',
          'data-kind': node.attrs.kind as string,
          'data-serialized-text': serializedText ?? '',
          class: 'mention-chip',
        },
        serializedText ?? serializeMentionLabel(label, node.attrs.kind as string | null, name),
      ];
    },
    // Widen to the default SuggestionOptions to bypass the MentionNodeAttrs constraint;
    // we control the attrs shape.
    suggestion: {
      char: '@',
      allowSpaces: false,
      ...(suggestion as Partial<SuggestionOptions>),
    },
  });
}
