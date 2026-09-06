/**
 * MentionPill
 *
 * React NodeView for the TipTap `mention` atom node. Renders as an inline pill:
 *
 *   [icon] [name]
 *
 * On hover, a small ✕ button appears over the icon so the user can remove the
 * mention without keyboard navigation. The pill is `contentEditable=false`, so
 * Backspace / Delete at the node boundary deletes the entire atom at once.
 */

import { cx } from '@styles/utilities/cx';
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { AtSign, Braces, CircleDot, File, X } from 'lucide-react';
import React from 'react';
import { basename, fileIconClass } from './mention-pill-helpers';
import type { MentionKind, RenderMentionIcon } from './types';
import * as styles from './mention-pill.css';

// ── Kind → fallback lucide icon ───────────────────────────────────────────────

const ICON_SIZE_SM = { width: '0.75rem', height: '0.75rem' };

const KIND_ICONS: Record<MentionKind, React.ReactNode> = {
  file: <File style={ICON_SIZE_SM} />,
  issue: <CircleDot style={ICON_SIZE_SM} />,
  symbol: <Braces style={ICON_SIZE_SM} />,
  custom: <AtSign style={ICON_SIZE_SM} />,
};

function PillIcon({
  id,
  kind,
  label,
  renderMentionIcon,
}: {
  id: string;
  kind: MentionKind;
  label: string;
  renderMentionIcon?: RenderMentionIcon;
}) {
  const hostIcon = renderMentionIcon?.({ id, label, kind });
  if (hostIcon) return hostIcon;

  if (kind === 'file') {
    const cls = fileIconClass(label);
    if (cls) return <i className={cls} style={{ fontSize: '12px', lineHeight: 1 }} />;
  }
  return KIND_ICONS[kind] ?? KIND_ICONS.custom;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MentionPill({
  node,
  deleteNode,
  renderMentionIcon,
}: NodeViewProps & { renderMentionIcon?: RenderMentionIcon }) {
  const id = (node.attrs.id as string | null) ?? '';
  const label = (node.attrs.label as string | null) ?? (node.attrs.id as string | null) ?? '';
  const rawName = (node.attrs.name as string | null) ?? null;
  const name = rawName ?? (basename(label) || label);
  const kind = ((node.attrs.kind as string | null) ?? 'custom') as MentionKind;
  const pending = node.attrs.pending === true;

  return (
    <NodeViewWrapper as="span" className={cx('mention-pill-wrapper', styles.pillWrapper)}>
      <span
        contentEditable={false}
        className={cx(styles.pill, pending && styles.pillPending)}
        data-mention-id={node.attrs.id as string}
        data-mention-kind={kind}
        data-mention-pending={pending || undefined}
      >
        {/* Icon area — relative so the ✕ overlay is positioned inside it */}
        <span className={styles.pillIconArea}>
          <PillIcon id={id} kind={kind} label={label} renderMentionIcon={renderMentionIcon} />
          {/* Hover-x: overlaid over the icon on pill-hover */}
          <button
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              deleteNode();
            }}
            aria-label={`Remove @${name}`}
            className={styles.pillRemoveBtn}
          >
            <X style={{ width: '0.625rem', height: '0.625rem' }} />
          </button>
        </span>
        {/* Display name */}
        <span className={styles.pillName}>{name}</span>
      </span>
    </NodeViewWrapper>
  );
}
