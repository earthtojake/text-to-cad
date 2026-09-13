import type { MeasureCtx, RenderCtx } from '@core/define';
import type { SegmentCtx } from '@core/units';
import { defineUnit } from '@core/units';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import { Show, createMemo } from 'solid-js';
import type { ChatDiff, ToolNode } from '@/model';
import { DiffHeader, DiffLines } from './Diff';
import { countChanges, selectPreview, type DiffRow } from './diff-lines';
import { langFromPath } from './lang';
import { diffCardVars, diffRoot, type DiffStyleVars } from './diff.css';

export type DiffVars = {
  /** Style-relevant: consumed by diffCardVars contract. */
  headerH: number;
  /** Measure-only: not in CSS contract. */
  maxLines: number;
  /** Measure-only: not in CSS contract. */
  context: number;
  /** Measure-only: border width on each side of the diff block. */
  border: number;
};

const DIFF_VARS: DiffVars = {
  headerH: 32,
  maxLines: 8,
  context: 1,
  border: 1,
};

export function createFileDiffFromItem(
  item: Extract<ToolNode, { kind: 'create-file-tool-call' }>,
  ctx: SegmentCtx
): ChatDiff {
  return {
    kind: 'diff',
    id: item.id,
    path: item.path,
    oldText: null,
    newText: item.content,
    status: item.status,
    ...(item.error !== undefined ? { error: item.error } : {}),
    awaitingPermission: ctx.pendingToolCallIds().has(item.toolCallId),
  };
}

export function modifyFileDiffFromItem(
  item: Extract<ToolNode, { kind: 'modify-file-tool-call' }>,
  ctx: SegmentCtx
): ChatDiff {
  return {
    kind: 'diff',
    id: item.id,
    path: item.path,
    oldText: item.oldText,
    newText: item.newText,
    status: item.status,
    ...(item.error !== undefined ? { error: item.error } : {}),
    awaitingPermission: ctx.pendingToolCallIds().has(item.toolCallId),
  };
}

export type DiffLayout = {
  kind: 'diff';
  previewRows: DiffRow[];
  adds: number;
  dels: number;
  lang: string | undefined;
  truncated: boolean;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function diffBodyH(previewRows: DiffRow[], codeLineH: number, border: number): number {
  return previewRows.length === 0 ? 2 * border : previewRows.length * codeLineH + 2 * border;
}

function diffUnitH(item: ChatDiff, ctx: MeasureCtx, vars: DiffVars): number {
  if (item.status === 'running' && item.newText.length === 0) return vars.headerH;
  const codeLineH = ctx.theme.fonts.code.lineHeight;
  const rows = ctx.caches.computeDiff(item.oldText, item.newText);
  const previewRows = selectPreview(rows, vars.maxLines, vars.context);
  return vars.headerH + diffBodyH(previewRows, codeLineH, vars.border);
}

// ── Render ────────────────────────────────────────────────────────────────────

function DiffUnitRender(props: { data: ChatDiff; ctx: RenderCtx; vars: DiffVars }) {
  const mCtx = () => props.ctx.measureCtx?.();

  const layout = createMemo<DiffLayout | null>(() => {
    const ctx = mCtx();
    if (!ctx) return null;
    const rows = ctx.caches.computeDiff(props.data.oldText, props.data.newText);
    const { adds, dels } = countChanges(rows);
    const { maxLines, context } = props.vars;
    const previewRows = selectPreview(rows, maxLines, context);
    const lang = langFromPath(props.data.path);
    const truncated = previewRows.length > 0 && previewRows.at(-1) !== rows.at(-1);
    return { kind: 'diff', previewRows, adds, dels, lang, truncated };
  });

  const totalH = createMemo(() => {
    const ctx = mCtx();
    if (!ctx) return props.vars.headerH;
    return diffUnitH(props.data, ctx, props.vars);
  });

  const headerOnly = () => props.data.status === 'running' && props.data.newText.length === 0;
  const codeLineH = () => mCtx()?.theme.fonts.code.lineHeight ?? 0;

  const styleVars = (): DiffStyleVars => ({ height: totalH(), headerH: props.vars.headerH });

  return (
    <div class={diffRoot} style={assignInlineVars(diffCardVars, pxTokens(styleVars()))}>
      <Show when={layout()}>
        {(l) => (
          <>
            <DiffHeader
              item={props.data}
              adds={l().adds}
              dels={l().dels}
              headerH={props.vars.headerH}
              hasBody={!headerOnly()}
            />
            <Show when={!headerOnly()}>
              <DiffLines item={props.data} layout={l()} codeLineHeight={codeLineH} />
            </Show>
          </>
        )}
      </Show>
    </div>
  );
}

// ── UnitDef ───────────────────────────────────────────────────────────────────

export const diffUnitDef = defineUnit<ChatDiff, DiffVars>({
  kind: 'diff',
  margin: { top: 2, bottom: 6 },
  vars: DIFF_VARS,

  estimate(item, ctx, vars): number {
    if (item.status === 'running' && item.newText.length === 0) return vars.headerH;
    return vars.headerH + vars.maxLines * ctx.theme.fonts.code.lineHeight + 2 * vars.border;
  },

  measure(item, ctx, vars): number {
    return diffUnitH(item, ctx, vars);
  },

  Render: DiffUnitRender,
});
