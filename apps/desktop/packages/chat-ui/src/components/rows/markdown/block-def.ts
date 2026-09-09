import type { Measured, MeasureCtx } from '@core/define';
import type { BlockLeafLayout } from '@core/layout/layout-types';
import type { Block } from '@core/markdown/document';
import type { Margin } from '@core/spacing';
import type { JSX } from 'solid-js';

export type { Margin };

export type BlockDef<B extends Block, L extends BlockLeafLayout> = {
  kind: B['kind'];
  /**
   * Required vertical margins for this block kind.
   *
   * Receives the block so prose can branch on `block.variant`. At each seam
   * `layoutBlockStack` collapses adjacent margins to max(prev.bottom, cur.top).
   * Hidden/collapsed blocks are skipped. No fallback — every def must declare margins.
   */
  margin(block: B): Margin;
  measure(block: B, ctx: MeasureCtx): Measured<L>;
  Render(props: { node: Measured<L> }): JSX.Element;
};

export function defineBlock<B extends Block, L extends BlockLeafLayout>(
  d: BlockDef<B, L>
): BlockDef<B, L> {
  return d;
}
