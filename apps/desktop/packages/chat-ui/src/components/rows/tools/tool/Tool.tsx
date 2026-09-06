/**
 * Tool — minimal single-row renderer for generic ChatToolCall items.
 *
 * Used as the desktop fallback for ACP tool kinds without a dedicated renderer
 * (search, fetch, think, other). Consistent with the file-op / execute style:
 * a plain text row with no status badge, no collapse, no detail view.
 *
 * Shimmer applied while status === 'running'. No error-specific chrome.
 *
 * Outer geometry (height, padding) is applied by tool.def.ts Render.
 * This component only describes inner content.
 */

import { IconError, IconShieldAlert } from '@components/primitives/icons';
import { Show } from 'solid-js';
import type { ChatToolCall } from '@/model';
import {
  textShimmer,
  toolErrorIcon,
  toolName,
  toolNameWithSummary,
  toolPermissionIcon,
  toolPreview,
  toolRow,
  toolStack,
  toolStatus,
  toolSummary,
} from './tool.css';

export type ToolProps = {
  item: ChatToolCall;
};

export function Tool(props: ToolProps) {
  const isRunning = () => props.item.status === 'running' && !props.item.awaitingPermission;
  const statusAnnouncement = () => {
    const summary = props.item.inputSummary ? `: ${props.item.inputSummary}` : '';
    const state = props.item.awaitingPermission
      ? 'Awaiting permission'
      : props.item.activity
        ? ''
        : props.item.status === 'running'
          ? 'Running'
          : props.item.status === 'error'
            ? 'Failed'
            : 'Completed';
    // Comma joins read naturally after a summary that ends in its own punctuation
    // (a question title followed by "Awaiting permission").
    const status = state ? `, ${state}` : '';
    const error = props.item.error ? `, ${props.item.error}` : '';
    return `${props.item.name}${summary}${status}${error}`;
  };
  return (
    <div class={toolStack}>
      <div class={toolRow}>
        <span
          class={toolName}
          classList={{
            [textShimmer]: isRunning(),
            [toolNameWithSummary]: Boolean(props.item.inputSummary),
          }}
        >
          {props.item.name}
        </span>
        <Show when={props.item.inputSummary}>
          <span class={toolSummary}>{props.item.inputSummary}</span>
        </Show>
        <Show
          when={props.item.awaitingPermission}
          fallback={
            <Show when={props.item.status === 'error'}>
              <span class={toolErrorIcon} title={props.item.error ?? 'Failed'} aria-hidden="true">
                <IconError />
              </span>
            </Show>
          }
        >
          <span class={toolPermissionIcon} title="Awaiting permission" aria-hidden="true">
            <IconShieldAlert />
          </span>
        </Show>
        <span class={toolStatus} role="status" aria-live="polite" aria-atomic="true">
          {statusAnnouncement()}
        </span>
      </div>
      <Show when={props.item.outputPreview}>
        <div class={toolPreview} title={props.item.outputPreview}>
          {props.item.outputPreview}
        </div>
      </Show>
    </div>
  );
}
