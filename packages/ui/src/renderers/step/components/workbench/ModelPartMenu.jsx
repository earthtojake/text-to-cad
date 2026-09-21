import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from '@hardcore/ui/primitives/context-menu';
import { useHostReference } from '../../file-view/hostReference.js';
import { AssemblyPartMenuItems } from './AssemblyContextMenuItems.js';

// A Features tree row's menu. It is the SAME menu the viewport offers over that
// part — one descriptor (`controls.menuForNode`) and one set of actions
// (`controls.partMenuActions`) — and unlike the viewport's it is available under
// any tool, because every one of its actions returns to Select before it runs.

/** Built only once the menu is actually open, so a tree of rows never pays for it. */
function TreeNodeMenuItems({ id, controls, disabled }) {
  const hostReference = useHostReference();
  const actions = controls.partMenuActions || {};
  const menu = controls.menuForNode?.(id);
  if (!menu) return null;
  return <AssemblyPartMenuItems menu={menu} Item={ContextMenuItem} Separator={ContextMenuSeparator}
    disabled={disabled}
    actions={{ ...actions, onAddToPrompt: hostReference?.canAddToPrompt ? actions.onAddToPrompt : undefined }} />;
}

export default function ModelPartMenu({ node, controls, disabled, children }) {
  if (!node.selectionId || !controls.menuForNode) return children;
  return <ContextMenu><ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
    <ContextMenuContent className="w-44">
      <TreeNodeMenuItems id={node.selectionId} controls={controls} disabled={disabled} />
    </ContextMenuContent>
  </ContextMenu>;
}
