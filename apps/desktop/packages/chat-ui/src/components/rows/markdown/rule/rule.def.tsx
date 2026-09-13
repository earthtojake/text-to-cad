import { BlockFrame } from '@components/engine/block-frame';
import { defineBlock } from '@components/rows/markdown/block-def';
import type { Measured, MeasureCtx } from '@core/define';
import type { RuleLeafLayout } from '@core/layout/layout-types';
import type { RuleBlock } from '@core/markdown/document';
import { ruleLine } from './rule.css';

/** Fixed height of the rendered 1px separator line (px). */
const SEPARATOR_HEIGHT = 1;

export const ruleBlockDef = defineBlock<RuleBlock, RuleLeafLayout>({
  kind: 'rule',
  margin: () => ({ top: 12, bottom: 12 }),

  measure(block: RuleBlock, ctx: MeasureCtx): Measured<RuleLeafLayout> {
    const layout: RuleLeafLayout = {
      kind: 'rule',
      id: block.id,
      top: 0,
      height: SEPARATOR_HEIGHT,
      raw: block,
    };
    return { height: SEPARATOR_HEIGHT, width: ctx.width, layout };
  },

  Render(props: { node: Measured<RuleLeafLayout> }) {
    return (
      <BlockFrame layout={props.node.layout}>
        <div class={ruleLine} />
      </BlockFrame>
    );
  },
});
