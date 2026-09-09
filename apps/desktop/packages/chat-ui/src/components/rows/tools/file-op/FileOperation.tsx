import { useCommands } from '@components/contexts/CommandsContext';
import { CollapseHeader } from '@components/primitives/CollapseHeader';
import { IconError, IconShieldAlert } from '@components/primitives/icons';
import { basename } from '@lib/path';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { For, Show, createEffect } from 'solid-js';
import type { ChatFileOpToolCall, FileOpKind } from '@/model';
import {
  chevronSm,
  fileOpErrorIcon,
  fileOpHeader,
  fileOpPermissionIcon,
  fileRow,
  runningLabel,
  singleOpRow,
} from './file-op.css';
import { fileOpCardVars } from './file-op.css';
import { textShimmer } from '@styles/effects.css';

// ── Verb map ──────────────────────────────────────────────────────────────────

const VERB: Record<FileOpKind, string> = {
  read: 'Read',
  edit: 'Edited',
  delete: 'Deleted',
  move: 'Moved',
};

// ── Internal: FileRowItem ─────────────────────────────────────────────────────

function FileRowItem(props: { verb: string; path: string; lineH: number; onClick?: () => void }) {
  return (
    <div
      class={fileRow({ clickable: !!props.onClick })}
      style={{ height: `${props.lineH}px` }}
      role={props.onClick ? 'button' : undefined}
      onClick={props.onClick}
    >
      <span>{props.verb}</span>
      <span title={props.path}>{basename(props.path)}</span>
    </div>
  );
}

// ── FileOpRow (single-file) ───────────────────────────────────────────────────

export type FileOpRowProps = {
  item: ChatFileOpToolCall;
  rowH: number;
  lineH: number;
};

export function FileOpRow(props: FileOpRowProps) {
  const commands = useCommands();
  const verb = () => VERB[props.item.op];

  const openFile = (path: string) => {
    commands().onOpenFile?.({ path, itemId: props.item.id, source: 'file-op' });
  };

  return (
    <div class={singleOpRow} style={{ height: `${props.rowH}px` }}>
      <Show
        when={props.item.ops[0]}
        fallback={
          <span
            class={runningLabel}
            classList={{
              [textShimmer]: props.item.status === 'running' && !props.item.awaitingPermission,
            }}
          >
            {verb()}…
          </span>
        }
      >
        {(op) => (
          <FileRowItem
            verb={verb()}
            path={op().path}
            lineH={props.lineH}
            onClick={() => openFile(op().path)}
          />
        )}
      </Show>
      <Show
        when={props.item.awaitingPermission}
        fallback={
          <Show when={props.item.status === 'error'}>
            <span class={fileOpErrorIcon} title={props.item.error ?? 'Failed'} aria-label="error">
              <IconError />
            </span>
          </Show>
        }
      >
        <span
          class={fileOpPermissionIcon}
          title="Awaiting permission"
          aria-label="awaiting permission"
        >
          <IconShieldAlert />
        </span>
      </Show>
    </div>
  );
}

// ── FileOpHeader (multi-file header) ─────────────────────────────────────────

export type FileOpHeaderProps = {
  item: ChatFileOpToolCall;
  expanded: boolean;
  rowH: number;
};

export function FileOpHeader(props: FileOpHeaderProps) {
  return (
    <CollapseHeader
      id={props.item.id}
      expanded={props.expanded}
      active={props.item.status === 'running' && !props.item.awaitingPermission}
      error={props.item.status === 'error'}
      errorTitle={props.item.error}
      awaitingPermission={props.item.awaitingPermission}
      height={props.rowH}
    >
      {VERB[props.item.op]} {props.item.ops.length} files
    </CollapseHeader>
  );
}

// ── FileOpList (expanded per-file list) ───────────────────────────────────────

export type FileOpListProps = {
  item: ChatFileOpToolCall;
  lineH: number;
  padY: number;
};

export function FileOpList(props: FileOpListProps) {
  const commands = useCommands();
  const verb = () => VERB[props.item.op];

  const openFile = (path: string) => {
    commands().onOpenFile?.({ path, itemId: props.item.id, source: 'file-op' });
  };

  return (
    <div
      style={{
        ...assignInlineVars({ [fileOpCardVars.padY]: `${props.padY}px` }),
        'padding-block': fileOpCardVars.padY,
      }}
    >
      <For each={props.item.ops}>
        {(op) => (
          <FileRowItem
            verb={verb()}
            path={op.path}
            lineH={props.lineH}
            onClick={() => openFile(op.path)}
          />
        )}
      </For>
    </div>
  );
}

// ── FileOpPreviewBody (streaming ops body inside ProjectWindow) ───────────────

export type FileOpPreviewBodyProps = {
  item: ChatFileOpToolCall;
  lineH: number;
  padY: number;
};

export function FileOpPreviewBody(props: FileOpPreviewBodyProps) {
  const verb = () => VERB[props.item.op];
  let innerEl: HTMLDivElement | undefined;

  createEffect(() => {
    const _n = props.item.ops.length; // reactive tracking
    if (innerEl) innerEl.scrollTop = innerEl.scrollHeight;
    return _n;
  });

  return (
    <div
      ref={(el) => {
        innerEl = el;
      }}
      style={{ height: '100%', 'overflow-y': 'auto', 'scrollbar-gutter': 'stable' }}
    >
      <div
        style={{
          ...assignInlineVars({ [fileOpCardVars.padY]: `${props.padY}px` }),
          'padding-block': fileOpCardVars.padY,
        }}
      >
        <For each={props.item.ops}>
          {(op) => <FileRowItem verb={verb()} path={op.path} lineH={props.lineH} />}
        </For>
      </div>
    </div>
  );
}

// ── FileOperation (legacy component kept for open-file contract test) ──────────

/** @deprecated Use fileOpDef.Render via Project instead. Kept for open-file.contract.test.tsx. */
export type FileOperationProps = {
  item: ChatFileOpToolCall;
  /** Inverted semantics: stored "collapsed" bool means "expanded". */
  collapsed?: boolean;
};

export function FileOperation(props: FileOperationProps) {
  const commands = useCommands();
  const verb = () => VERB[props.item.op];
  const expanded = () => !!props.collapsed;

  const openFile = (path: string) => {
    commands().onOpenFile?.({ path, itemId: props.item.id, source: 'file-op' });
  };

  return (
    <Show
      when={props.item.ops.length > 1}
      fallback={
        <Show
          when={props.item.ops[0]}
          fallback={
            <span
              class={runningLabel}
              classList={{ [textShimmer]: props.item.status === 'running' }}
            >
              {verb()}…
            </span>
          }
        >
          {(op) => (
            <FileRowItem
              verb={verb()}
              path={op().path}
              lineH={16}
              onClick={() => openFile(op().path)}
            />
          )}
        </Show>
      }
    >
      <div>
        <div
          class={fileOpHeader}
          role="button"
          aria-expanded={expanded() ? 'true' : 'false'}
          data-collapse-id={props.item.id}
        >
          <span classList={{ [textShimmer]: props.item.status === 'running' }}>
            {verb()} {props.item.ops.length} files
          </span>
          <span class={chevronSm({ expanded: expanded() })} aria-hidden="true">
            ›
          </span>
        </div>
        <Show when={expanded()}>
          <For each={props.item.ops}>
            {(op) => (
              <FileRowItem
                verb={verb()}
                path={op.path}
                lineH={16}
                onClick={() => openFile(op.path)}
              />
            )}
          </For>
        </Show>
      </div>
    </Show>
  );
}
