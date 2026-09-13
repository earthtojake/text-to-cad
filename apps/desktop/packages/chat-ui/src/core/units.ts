/**
 * Render-unit primitives — the flat virtualization model.
 *
 * The engine virtualizes over a flat `RenderUnit[]` array produced by
 * `state/flatten.ts`.  Each unit is one independently mounted, measured, and
 * rendered row.  Units that belong to the same source `ChatItem` share a
 * `groupId` and are decorated with `groupRole` / `gapBefore` by the flatten
 * pass so that chrome (bubble background, insets, inter-unit gaps) can be
 * painted per-unit without coordination between rows.
 *
 * ── Component authoring ───────────────────────────────────────────────────────
 *
 * Leaf kinds (single-row items):
 *   `defineUnit<D>({ kind, estimate?, measure, Render })`
 *   measure returns a number (row height only) — no `Measured<L>` tree.
 *
 * Multi-unit items (message blocks):
 *   `defineSegmenter<T>({ kind, chrome?, segment })`
 *   segment() returns RenderUnit[] — one per block, entry, etc.
 *   Composites (diff / plan / thinking / file-op) are single-unit segmenters:
 *   segment() returns exactly [unit(...)]; their Render handles internal layout.
 *
 * ── State split (Lane A vs Lane B) ───────────────────────────────────────────
 *
 * Identical to the `ComponentDef` contract in `core/define.ts`:
 * Lane A (layout-affecting): width, expanded(id).
 * Lane B (presentational): hover, shimmer, copied state, timers.
 * Only Lane A values must appear in `UnitDef.measure` and the fingerprint.
 */

import type { Component } from 'solid-js';
import type { ChatItem, PlanState, SyntheticItem, TerminalOutputSnapshot } from '@/model';
import type { ChatCaches } from './caches';
import type { MeasureCtx, RenderCtx } from './define';
import type { Margin } from './spacing';

export type { Margin };

// ── GroupRole ─────────────────────────────────────────────────────────────────

/**
 * Position of a unit within its group (all units from one ChatItem).
 *
 * Used by UnitRow to resolve per-unit chrome:
 *   solo   — only unit in the group (most items).
 *   first  — first unit in a multi-unit group (top corners / top padding).
 *   middle — interior unit (side chrome only).
 *   last   — last unit in a multi-unit group (bottom corners / bottom padding).
 */
export type GroupRole = 'solo' | 'first' | 'middle' | 'last';

// ── RenderUnit ────────────────────────────────────────────────────────────────

/**
 * One virtualized row.
 *
 * `id`        — stable, unique key: `${itemId}#${segmentKey}`.
 *               Must not change across streaming ticks or collapse toggles.
 * `itemId`    — id of the source ChatItem (for scrollToItem, grouping).
 * `groupId`   — usually itemId; could differ for cross-item groups (future).
 * `kind`      — dispatches to UNIT_REGISTRY.
 * `data`      — segment payload; typed per-kind in each UnitDef.
 * `groupRole` — stamped by flatten(); used by UnitRow for chrome.
 * `gapBefore` — space reserved above this unit inside its virtualizer slot.
 *               flatten() resolves every inter-group seam via margin-collapse
 *               (max of adjacent UnitDef margins, falling back to turnGap) and
 *               stamps the result here. Turn boundaries resolve to 8px because
 *               the user message margin (8/8) is >= all other unit margins.
 *               The first group in the transcript gets 0.
 * `chrome`    — optional group chrome carried from the ItemSegmenter, stamped
 *               by flatten(); undefined for solo legacy units.
 */
export type RenderUnit<D = unknown> = {
  id: string;
  itemId: string;
  groupId: string;
  kind: string;
  data: D;
  groupRole: GroupRole;
  gapBefore: number;
  chrome?: GroupChrome;
};

// ── GroupChrome ───────────────────────────────────────────────────────────────

/**
 * Declarative per-group chrome painted by UnitRow around each unit.
 *
 * Used for the multi-unit message group (user-bubble background + inset).
 * Composites (diff / plan / thinking / file-op) are single units and draw
 * their own borders/cards internally, so they do not use GroupChrome.
 *
 * `insetX` — horizontal padding (px) subtracted from the available width
 *             before measure(); also applied as left/right padding in the
 *             rendered row wrapper so the content is visually inset.
 */
export type GroupChrome = {
  insetX?: number;
};

export type SegmentItem = ChatItem | SyntheticItem;

// ── SegmentCtx ────────────────────────────────────────────────────────────────

/**
 * Minimal context available to every `segment()` call.
 *
 * Deliberately small: segment() decides *structure* (which units, which keys),
 * not *geometry* — it never measures. `expanded` is included because collapse
 * state changes the number of units emitted (e.g. expanded plan emits
 * per-entry units; collapsed emits just a preview unit).
 *
 * `caches.parseBlocks` is WeakMap-memoized; re-segmenting committed items is
 * cheap even if called on every tick.
 */
export type SegmentCtx = {
  caches: ChatCaches;
  expanded: (id: string) => boolean;
  active: boolean;
  plan: () => PlanState | null;
  pendingToolCallIds: () => Set<string>;
  terminalOutput: (terminalId: string) => TerminalOutputSnapshot | null;
};

// ── UnitDef ───────────────────────────────────────────────────────────────────

/**
 * Definition of one leaf unit kind.
 *
 * `kind`     — matches the `RenderUnit.kind` dispatch key in UNIT_REGISTRY.
 * `vars`     — typed numeric geometry constants declared once on the def and
 *              threaded into `measure`, `estimate`, and `Render`. Defs that
 *              have not yet been migrated to the Box algebra omit this field.
 * `margin`   — optional vertical margins (px). At every inter-group seam
 *              `flatten()` collapses adjacent margins to max(prev.bottom,
 *              cur.top) and assigns the result to the lower unit's `gapBefore`.
 *              Falls back to `density.turnGap` when absent. Turn boundaries
 *              resolve to 8px via the user message's margin (top: 8, bottom: 8).
 * `estimate` — O(1) height heuristic for off-screen units at setCount/prepend.
 *              Falls back to `genericEstimate` when omitted.
 * `heightAnimationKey` — optional semantic state key. A changed key lets a
 *              unit animate a measured-height transition that is not a manual
 *              expand/collapse toggle (for example active thinking → done).
 *              Ordinary streaming growth still snaps.
 * `measure`  — exact height (px); called only for visible units.
 *              Returns a number — no Measured<L> tree.
 * `Render`   — Solid component; receives `data` (the unit payload), `ctx`,
 *              and `vars` (the def's typed geometry constants).
 */
export type UnitDef<D, V extends Record<string, number> = {}> = {
  kind: string;
  vars?: V;
  margin?: Margin;
  estimate?(data: D, ctx: MeasureCtx, vars: V): number;
  heightAnimationKey?(data: D, ctx: MeasureCtx, vars: V): string | number | boolean | null;
  measure(data: D, ctx: MeasureCtx, vars: V): number;
  Render: Component<{ data: D; ctx: RenderCtx; vars: V }>;
};

// ── ItemSegmenter ─────────────────────────────────────────────────────────────

/**
 * Definition of how one ChatItem kind is split into RenderUnits.
 *
 * `kind`    — matches ChatItem.kind.
 * `chrome`  — optional group chrome applied by UnitRow around each emitted unit.
 * `segment` — pure function: item + ctx → ordered RenderUnit[].
 *             Must return stable ids across streaming ticks.
 *             For single-unit composites (diff / plan / etc.), returns exactly
 *             one unit whose Render handles internal layout.
 */
export type ItemSegmenter = {
  kind: string;
  chrome?: GroupChrome;
  segment(item: SegmentItem, ctx: SegmentCtx): RenderUnit[];
};

// ── Factories ─────────────────────────────────────────────────────────────────

/** Identity factory for UnitDef — enables TypeScript inference. */
export function defineUnit<D, V extends Record<string, number> = {}>(
  def: UnitDef<D, V>
): UnitDef<D, V> {
  return def;
}

/** Identity factory for ItemSegmenter — enables TypeScript inference. */
export function defineSegmenter(seg: ItemSegmenter): ItemSegmenter {
  return seg;
}

// ── unit() helper ─────────────────────────────────────────────────────────────

/**
 * Construct a single RenderUnit with the correct id format.
 *
 * `groupRole` is initialized to 'solo'; `stampGroupRoles` overwrites it after
 * all units in a group have been collected.
 *
 * Usage in a segmenter:
 *   unit('prose', item, block, { key: block.id })
 *   unit('prose', item, block, { key: block.id, gapBefore: PROSE_GAP })
 */
export function unit<D>(
  kind: string,
  item: SegmentItem,
  data: D,
  opts: { key: string; gapBefore?: number }
): RenderUnit<D> {
  return {
    id: `${item.id}#${opts.key}`,
    itemId: item.id,
    groupId: item.id,
    kind,
    data,
    groupRole: 'solo',
    gapBefore: opts.gapBefore ?? 0,
  };
}

// ── unitReservedHeight ────────────────────────────────────────────────────────

/**
 * Compute the total virtualizer-reserved height for a native unit.
 *
 * Formula: gapBefore + contentH
 *
 * All inter-row spacing lives in `gapBefore` (resolved by flatten() via
 * margin-collapse). No chrome overhead or trailing gap is added.
 *
 * Exported so ChatRoot (estimate / prefetch paths) and UnitRow can share
 * the same formula without duplicating it.
 */
export function unitReservedHeight(unit: RenderUnit, contentH: number): number {
  return unit.gapBefore + contentH;
}

// ── stampGroupRoles ───────────────────────────────────────────────────────────

/**
 * Overwrite the `groupRole` field on a group of units produced by one
 * segmenter call.  Called by flatten() after each item's units are collected,
 * before they are appended to the flat array.
 *
 * A single unit stays 'solo'.  Multiple units get 'first' / 'middle' / 'last'.
 * Mutates in place for performance (units are freshly constructed each call).
 */
export function stampGroupRoles(units: RenderUnit[]): void {
  if (units.length === 0) return;
  if (units.length === 1) {
    units[0].groupRole = 'solo';
    return;
  }
  for (let i = 0; i < units.length; i++) {
    if (i === 0) units[i].groupRole = 'first';
    else if (i === units.length - 1) units[i].groupRole = 'last';
    else units[i].groupRole = 'middle';
  }
}
