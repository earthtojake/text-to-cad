import { defineBlock } from '@components/rows/markdown/block-def';
import type { Measured, MeasureCtx } from '@core/define';
import type { MermaidLeafLayout } from '@core/layout/layout-types';
import type { MermaidBlock } from '@core/markdown/document';
import { Mermaid } from './Mermaid';

/** Fixed 21:9 aspect ratio: height = width * 9 / 21. */
function mermaidHeight(width: number): number {
  return Math.round((width * 9) / 21);
}

export const mermaidBlockDef = defineBlock<MermaidBlock, MermaidLeafLayout>({
  kind: 'mermaid',
  margin: () => ({ top: 8, bottom: 8 }),

  measure(block: MermaidBlock, ctx: MeasureCtx): Measured<MermaidLeafLayout> {
    const height = mermaidHeight(ctx.width);
    const layout: MermaidLeafLayout = {
      kind: 'mermaid',
      id: block.id,
      top: 0,
      height,
      contentWidth: ctx.width,
      source: block.source,
      raw: block,
    };
    return { height, width: ctx.width, layout };
  },

  Render(props: { node: Measured<MermaidLeafLayout> }) {
    const l = props.node.layout;
    return <Mermaid block={l} rawBlock={l.raw} />;
  },
});
