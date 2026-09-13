/**
 * / command extension.
 *
 * Reuses the Mention node infrastructure from @tiptap/extension-mention under a
 * different node name (`slashCommand`) and trigger char (`/`).
 *
 * Behaviors (determined per-item):
 *  - 'insert'  → inserts a slashCommand atom node serialized as `/${name}`.
 *  - 'insert-text' → inserts the item's raw text directly into the editor.
 *  - 'execute' → calls onCommand(item) and removes the trigger range without
 *                inserting any node.
 */

import { Mention as TipTapMention } from '@tiptap/extension-mention';
import { PluginKey } from '@tiptap/pm/state';
import { ReactNodeViewRenderer } from '@tiptap/react';
import type { SuggestionOptions } from '@tiptap/suggestion';
import { SlashCommandPill } from '../slash-command-pill';
import type { CommandItem } from '../types';

const slashCommandPluginKey = new PluginKey('slashCommand');

function plainTextInsertContent(text: string) {
  const lines = text.length > 0 ? text.split(/\r?\n/) : [''];
  return lines.map((line) => ({
    type: 'paragraph',
    ...(line.length > 0 ? { content: [{ type: 'text', text: line }] } : {}),
  }));
}

export function buildSlashCommandExtension(
  suggestion: Partial<SuggestionOptions<CommandItem>>,
  onExecute: (item: CommandItem) => void
) {
  return TipTapMention.extend({
    name: 'slashCommand',
    addAttributes() {
      return {
        id: { default: null },
        name: { default: null },
      };
    },
    addNodeView() {
      return ReactNodeViewRenderer(SlashCommandPill, { as: 'span' });
    },
  }).configure({
    HTMLAttributes: { class: 'slash-command-chip' },
    renderText({ node }) {
      return `/${(node.attrs.name as string | null) ?? (node.attrs.id as string | null) ?? ''}`;
    },
    renderHTML({ node }) {
      return [
        'span',
        {
          'data-type': 'slash-command',
          'data-id': node.attrs.id as string,
          'data-name': node.attrs.name as string,
          class: 'slash-command-chip',
        },
        `/${(node.attrs.name as string | null) ?? (node.attrs.id as string | null) ?? ''}`,
      ];
    },
    suggestion: {
      char: '/',
      allowSpaces: false,
      pluginKey: slashCommandPluginKey,
      // Wrap the command handler so 'execute' items don't insert a node.
      command({ editor, range, props }) {
        // TipTap types `props` as MentionNodeAttrs; cast to CommandItem since we control what gets passed.
        const item = props as unknown as CommandItem;
        if (item.behavior === 'execute') {
          editor.chain().focus().deleteRange(range).run();
          onExecute(item);
        } else if (item.behavior === 'insert-text') {
          editor
            .chain()
            .focus()
            .deleteRange(range)
            .insertContentAt(range.from, plainTextInsertContent(item.insertText ?? ''))
            .run();
        } else {
          editor
            .chain()
            .focus()
            .deleteRange(range)
            .insertContentAt(range.from, [
              {
                type: 'slashCommand',
                attrs: { id: item.id, name: item.name ?? item.id },
              },
              { type: 'text', text: ' ' },
            ])
            .run();
        }
      },
      ...(suggestion as Partial<SuggestionOptions>),
    },
  });
}
