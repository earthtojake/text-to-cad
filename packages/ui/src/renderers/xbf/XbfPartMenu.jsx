import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from '@text-to-cad/ui/primitives/context-menu';
import { AssemblyPartMenuItems } from './xbfMenuItems.js';

// A Features tree row's menu: the SAME menu the viewport offers over the node the row stands
// for -- one descriptor (`controls.menuForNode`) and one set of actions
// (`controls.partMenuActions`) -- and unlike the viewport's it is available under any tool,
// because every one of its actions returns to Select before it runs. A row with no node of its
// own (a folded repeat) has none.

/** Built only once the menu is actually open, so a tree of rows never pays for it. */
function PartMenuItems({ id, controls, disabled }) {
  const menu = controls.menuForNode(id);
  if (!menu) return null;
  return <AssemblyPartMenuItems menu={menu} Item={ContextMenuItem} Separator={ContextMenuSeparator}
    disabled={disabled} actions={controls.partMenuActions || {}} />;
}

export default function ModelPartMenu({ node, controls, disabled, children }) {
  if (!node.selectionId || !controls.menuForNode) return children;
  return <ContextMenu><ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
    <ContextMenuContent className="w-44">
      <PartMenuItems id={node.selectionId} controls={controls} disabled={disabled} />
    </ContextMenuContent>
  </ContextMenu>;
}
