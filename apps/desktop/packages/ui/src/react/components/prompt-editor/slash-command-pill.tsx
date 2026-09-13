/**
 * SlashCommandPill
 *
 * React NodeView for the TipTap `slashCommand` atom node. Renders as an inline
 * pill containing the command name prefixed with a slash:
 *
 *   [/] [name]
 *
 * On hover a small ✕ button appears so the user can remove the command without
 * keyboard navigation. Matches the visual treatment of MentionPill.
 */

import { cx } from '@styles/utilities/cx';
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { X } from 'lucide-react';
import React from 'react';
import * as styles from './mention-pill.css';

export function SlashCommandPill({ node, deleteNode }: NodeViewProps) {
  const name = (node.attrs.name as string | null) ?? (node.attrs.id as string | null) ?? '';

  return (
    <NodeViewWrapper as="span" className={cx('slash-command-pill-wrapper', styles.pillWrapper)}>
      <span
        contentEditable={false}
        className={styles.pill}
        data-slash-command-id={node.attrs.id as string}
      >
        {/* Slash prefix area — relative so the ✕ overlay is positioned inside it */}
        <span className={styles.pillIconArea} aria-hidden="true">
          <span style={{ fontSize: '0.75rem', fontWeight: 400, lineHeight: 1 }}>/</span>
          {/* Hover-x: overlaid over the prefix on pill-hover */}
          <button
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              deleteNode();
            }}
            aria-label={`Remove /${name}`}
            className={styles.pillRemoveBtn}
          >
            <X style={{ width: '0.625rem', height: '0.625rem' }} />
          </button>
        </span>
        {/* Command name */}
        <span className={styles.pillName}>{name}</span>
      </span>
    </NodeViewWrapper>
  );
}
