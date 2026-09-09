/**
 * ResourceLink — single-line renderer for ChatResourceLink rows.
 *
 * Layout (fixed single-line row, no background):
 *   [resource || fileIcon] title path
 *
 * The icon is the file-type devicon when resolvable, else a generic resource
 * glyph. Title and path sit inline; the path keeps the muted secondary styling.
 *
 * Click: workspace-file targets open in the editor via onOpenFile.
 *        external targets follow the URI in a new tab.
 *        opaque targets do nothing (URI is shown for copy).
 *
 * Outer geometry (height) is applied by resource-link.def.tsx Render.
 */

import { useCommands } from '@components/contexts/CommandsContext';
import { GenericFileIcon, IconError } from '@components/primitives/icons';
import { resolveFileIconClass } from '@lib/file-icons';
import { Show } from 'solid-js';
import type { ChatResourceLink, ResourceTarget } from '@/model';
import {
  iconWrap,
  pathText,
  rowClickable,
  rowStatic,
  sizeText,
  titleText,
} from './resource-link.css';
import { vars } from '@styles/theme.css';

// ── Secondary label ─────────────────────────────────────────────────────────

function secondaryLabel(uri: string, target: ResourceTarget): string {
  if (target.kind === 'workspace-file') {
    return target.path;
  }
  if (target.kind === 'external') {
    try {
      return new URL(target.url).hostname;
    } catch {
      return target.url;
    }
  }
  // opaque: show the scheme or the raw uri, capped
  const colon = uri.indexOf(':');
  return colon > 0 ? uri.slice(0, colon + 1) + '//' + '…' : uri;
}

// ── Size formatting ─────────────────────────────────────────────────────────

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Component ────────────────────────────────────────────────────────────────

export type ResourceLinkProps = {
  item: ChatResourceLink;
};

export function ResourceLink(props: ResourceLinkProps) {
  const commands = useCommands();

  const displayName = () => props.item.title ?? props.item.name;
  const iconName = () => {
    const name = props.item.name;
    return resolveFileIconClass(name) ?? null;
  };
  const secondary = () => secondaryLabel(props.item.uri, props.item.target);
  const isClickable = () => props.item.target.kind !== 'opaque';

  const handleClick = () => {
    const target = props.item.target;
    if (target.kind === 'workspace-file') {
      commands().onOpenFile?.({
        path: target.path,
        itemId: props.item.id,
        source: 'resource-link',
      });
    } else if (target.kind === 'external') {
      window.open(target.url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div
      class={isClickable() ? rowClickable : rowStatic}
      style={{ height: '100%' }}
      onClick={isClickable() ? handleClick : undefined}
      role={isClickable() ? 'button' : undefined}
    >
      <div class={iconWrap}>
        <Show when={iconName()} fallback={<GenericFileIcon />}>
          <span class={iconName()!} />
        </Show>
      </div>
      <span class={titleText}>{displayName()}</span>
      <span class={pathText}>{secondary()}</span>
      <Show when={props.item.size !== undefined}>
        <span class={sizeText}>{formatSize(props.item.size!)}</span>
      </Show>
      <Show when={props.item.status === 'error'}>
        <span
          style={{ display: 'inline-flex', 'vertical-align': 'middle', color: vars.fgError }}
          title={props.item.error ?? 'Failed'}
          aria-label="error"
        >
          <IconError />
        </span>
      </Show>
    </div>
  );
}
