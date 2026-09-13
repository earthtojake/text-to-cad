import { BLOCK_REGISTRY } from '@components/rows/markdown/block-registry';
import type { StackLayout } from '@core/compose';
import type { Measured } from '@core/define';
import type { BlockLeafLayout } from '@core/layout/layout-types';
import { For } from 'solid-js';
import { Dynamic } from 'solid-js/web';

function BlockLeafRender(props: { node: Measured<BlockLeafLayout> }) {
  const def = BLOCK_REGISTRY[props.node.layout.kind];
  if (!def) return null;
  // oxlint-disable-next-line typescript/no-explicit-any -- registry boundary
  return <Dynamic component={def.Render} node={props.node as any} />;
}

export type BlockStackViewProps = {
  node: Measured<StackLayout>;
};

export function BlockStackView(props: BlockStackViewProps) {
  const placed = () => props.node.layout.placed;
  return (
    <div style={{ position: 'relative', height: `${props.node.height}px`, width: '100%' }}>
      {/*
       * Key by reference. stack() rebuilds placed[] with fresh wrapper objects
       * every layout pass, so <For> recreates each row on every streaming chunk.
       * That remount is intentional: block defs snapshot props.node.layout at
       * mount (e.g. `const l = props.node.layout` in code.def / prose.def), so a
       * growing block's content only stays in sync if its row is recreated when
       * the layout changes. (A persistent-row optimization keyed by block id was
       * tried and reverted — it left growing blocks frozen at their first layout
       * while the reserved height kept growing, producing one-line code blocks
       * surrounded by blank space until the turn committed.)
       */}
      <For each={placed()}>
        {(p) => (
          <div
            style={{
              position: 'absolute',
              top: `${p.top}px`,
              left: 0,
              right: 0,
              height: `${p.child.height}px`,
            }}
          >
            <BlockLeafRender node={p.child as Measured<BlockLeafLayout>} />
          </div>
        )}
      </For>
    </div>
  );
}
