import { defineBlock } from '@components/rows/markdown/block-def';
import type { Measured, MeasureCtx } from '@core/define';
import type { TableLeafLayout } from '@core/layout/layout-types';
import type { TableBlock } from '@core/markdown/document';
import { layoutTable } from './layout';
import { Table } from './Table';

export const tableBlockDef = defineBlock<TableBlock, TableLeafLayout>({
  kind: 'table',
  margin: () => ({ top: 8, bottom: 8 }),

  measure(block: TableBlock, ctx: MeasureCtx): Measured<TableLeafLayout> {
    const laid = layoutTable(block, 0, ctx.width);
    const layout: TableLeafLayout = { ...laid, raw: block };
    return { height: laid.height, width: laid.contentWidth, layout };
  },

  Render(props: { node: Measured<TableLeafLayout> }) {
    return <Table block={props.node.layout} />;
  },
});
