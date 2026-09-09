/**
 * ToolStateMatrix — stacks labelled rows for each tool status in a single
 * ChatHost, driven by a `build(status) => ChatItem` callback.
 *
 * Currently renders: Running, Awaiting Permission, Done, Error.
 */

import { DEFAULT_THEME } from '@core/theme';
import { For, type JSX, onCleanup } from 'solid-js';
import { createChatContext } from '@/chat-context';
import { ChatRoot } from '@/ChatRoot';
import type {
  AcpPermissionRequest,
  ChatItem,
  PlanState,
  ToolNode,
  ToolStatus,
  TranscriptTurn,
} from '@/model';
import { createChatState } from '@/state/chat-state';
import { storyViewport } from './chat-host.css';

export type MatrixStatus = ToolStatus;

export type MatrixRow = {
  label: string;
  status: MatrixStatus;
  awaitingPermission?: boolean;
  error?: string;
};

/** Default rows displayed in the matrix. */
const DEFAULT_MATRIX_ROWS: MatrixRow[] = [
  { label: 'Running', status: 'running' },
  { label: 'Awaiting Permission', status: 'running', awaitingPermission: true },
  { label: 'Done', status: 'done' },
  { label: 'Error', status: 'error', error: 'Command failed with exit code 1' },
];

export type ToolStateMatrixProps = {
  /**
   * Build a ChatItem for a given status. The item id must be unique — use a
   * suffix derived from status (e.g. `\`${base}-${status}\``) so each row is
   * independent in the virtualizer.
   */
  build: (status: MatrixStatus, row: MatrixRow) => ChatItem;
  rows?: MatrixRow[];
  /** Height of each individual row viewport in px (default: 80). */
  rowHeight?: number;
  /** Width of the viewport in px (default: 880). */
  width?: number;
};

export type ToolNodeStateMatrixProps = {
  /**
   * Build a ToolNode for a given status. Use the status in the id/toolCallId so
   * each row is independent in the virtualizer.
   */
  build: (status: MatrixStatus, row: MatrixRow) => ToolNode;
  rows?: MatrixRow[];
  /** Optional plan snapshot used by create-plan-tool-call rows. */
  plan?: (row: MatrixRow) => PlanState | null;
  rowHeight?: number;
  width?: number;
};

export type PlanMatrixRow = {
  label: string;
  item: ChatItem;
};

export type PlanStateMatrixProps = {
  rows: PlanMatrixRow[];
  rowHeight?: number;
  width?: number;
};

function matrixTurnId(label: string): string {
  return `matrix-turn-${label.toLowerCase().replaceAll(' ', '-')}`;
}

function MatrixRows(props: {
  rows: readonly { label: string }[];
  rowHeight: number;
  width: number;
  renderRow: (row: { label: string }) => JSX.Element;
}) {
  return (
    <div style={{ display: 'flex', 'flex-direction': 'column', gap: '12px' }}>
      <For each={props.rows}>
        {(row) => (
          <div>
            <div
              style={{
                'font-size': '11px',
                'font-family': 'monospace',
                color: '#888',
                'margin-bottom': '4px',
                'padding-left': '4px',
              }}
            >
              {row.label}
            </div>
            <div
              class={storyViewport}
              style={{ width: `${props.width}px`, height: `${props.rowHeight}px` }}
            >
              {props.renderRow(row)}
            </div>
          </div>
        )}
      </For>
    </div>
  );
}

type ToolCallNode = Extract<ToolNode, { toolCallId: string }>;

function firstToolCall(node: ToolNode): ToolCallNode | null {
  if ('toolCallId' in node) return node;
  for (const child of node.children) {
    const match = firstToolCall(child);
    if (match) return match;
  }
  return null;
}

function permissionFor(node: ToolNode): AcpPermissionRequest | null {
  const toolCall = firstToolCall(node);
  if (!toolCall) return null;
  return {
    requestId: `req-${toolCall.toolCallId}`,
    toolCall,
    options: [
      { optionId: 'allow-once', name: 'Allow once', kind: 'allow_once' },
      { optionId: 'reject-once', name: 'Reject', kind: 'reject_once' },
    ],
  };
}

/**
 * Renders one labeled ChatHost viewport per status row so all states are
 * visible side-by-side in the Storybook canvas.
 */
export function ToolStateMatrix(props: ToolStateMatrixProps) {
  const rows = props.rows ?? DEFAULT_MATRIX_ROWS;
  const rowHeight = props.rowHeight ?? 80;
  const width = props.width ?? 880;

  return (
    <MatrixRows
      rows={rows}
      rowHeight={rowHeight}
      width={width}
      renderRow={(row) => {
        const matrixRow = row as MatrixRow;
        const ctx = createChatContext({ theme: DEFAULT_THEME });
        const state = createChatState(ctx);
        onCleanup(() => {
          state.dispose();
          ctx.dispose();
        });
        const item = props.build(matrixRow.status, matrixRow);
        const matrixItem = {
          ...item,
          ...(matrixRow.awaitingPermission ? { awaitingPermission: true } : {}),
          ...(matrixRow.error && !('error' in item && item.error)
            ? { error: matrixRow.error }
            : {}),
        } as ChatItem;
        state.transcript.history.seed([
          {
            id: matrixTurnId(matrixRow.label),
            seq: 0,
            initiator: 'agent',
            items: [{ ...matrixItem, seq: 0 } as TranscriptTurn['items'][number]],
          },
        ]);
        return <ChatRoot context={ctx} state={state} stickToBottom pinUserMessages />;
      }}
    />
  );
}

export function ToolNodeStateMatrix(props: ToolNodeStateMatrixProps) {
  const rows = props.rows ?? DEFAULT_MATRIX_ROWS;
  const rowHeight = props.rowHeight ?? 80;
  const width = props.width ?? 880;

  return (
    <MatrixRows
      rows={rows}
      rowHeight={rowHeight}
      width={width}
      renderRow={(row) => {
        const matrixRow = row as MatrixRow;
        const ctx = createChatContext({ theme: DEFAULT_THEME });
        const state = createChatState(ctx);
        onCleanup(() => {
          state.dispose();
          ctx.dispose();
        });
        const item = props.build(matrixRow.status, matrixRow);
        const matrixItem = {
          ...item,
          ...(matrixRow.error && !('error' in item && item.error)
            ? { error: matrixRow.error }
            : {}),
        } as ToolNode;
        const permission = matrixRow.awaitingPermission ? permissionFor(matrixItem) : null;
        state.session.setPermissions(permission ? [permission] : []);
        state.session.setPlan(props.plan?.(matrixRow) ?? null);
        state.transcript.history.seed([
          {
            id: matrixTurnId(matrixRow.label),
            seq: 0,
            initiator: 'agent',
            items: [{ ...matrixItem, seq: 0 } as TranscriptTurn['items'][number]],
          },
        ]);
        return <ChatRoot context={ctx} state={state} stickToBottom pinUserMessages />;
      }}
    />
  );
}

export function PlanStateMatrix(props: PlanStateMatrixProps) {
  const rowHeight = props.rowHeight ?? 120;
  const width = props.width ?? 880;

  return (
    <MatrixRows
      rows={props.rows}
      rowHeight={rowHeight}
      width={width}
      renderRow={(row) => {
        const planRow = row as PlanMatrixRow;
        const ctx = createChatContext({ theme: DEFAULT_THEME });
        const state = createChatState(ctx);
        onCleanup(() => {
          state.dispose();
          ctx.dispose();
        });
        state.transcript.history.seed([
          {
            id: matrixTurnId(planRow.label),
            seq: 0,
            initiator: 'agent',
            items: [{ ...planRow.item, seq: 0 } as TranscriptTurn['items'][number]],
          },
        ]);
        return <ChatRoot context={ctx} state={state} stickToBottom pinUserMessages />;
      }}
    />
  );
}
