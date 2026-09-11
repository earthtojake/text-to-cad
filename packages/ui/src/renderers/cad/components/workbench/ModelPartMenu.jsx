import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from '@hardcore/ui/primitives/context-menu';
import { useHostReference } from '../../file-view/hostReference.js';
import AssemblyContextMenuItems from './AssemblyContextMenuItems.js';

export default function ModelPartMenu({node, controls, disabled, selectDisabled, selected, children, onSelect}) {
  const hostReference=useHostReference();
  if(!node.selectionId)return children;
  const id=node.selectionId, focused=controls.focusedNodeIds?.includes(id);
  const hidden=node.leafPartIds?.length > 0 && node.leafPartIds.every(leaf=>controls.hiddenPartIds?.includes(leaf));
  return <ContextMenu><ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
    <ContextMenuContent className="w-44">
      <AssemblyContextMenuItems Item={ContextMenuItem} Separator={ContextMenuSeparator}
        selected={selected} isolated={focused} hidden={hidden}
        copyReferenceDisabled={!controls.onCopyTreeNodeReference || disabled}
        selectDisabled={selectDisabled || hidden} showIsolate={controls.isAssemblyView} isolateDisabled={disabled}
        showHideOther={false} showVisibility={!focused} visibilityDisabled={disabled}
        showExitAllIsolate={controls.focusedNodeIds?.length > 0} exitAllIsolateDisabled={disabled}
        onAddToPrompt={hostReference ? ()=>controls.onCopyTreeNodeReference?.(id,{toPrompt:true}) : undefined}
        onCopyReference={()=>controls.onCopyTreeNodeReference?.(id)} onSelect={onSelect}
        onIsolate={()=>focused ? controls.onUnfocusTreeNode?.(id) : controls.onFocusTreeNode?.(id)}
        onToggleVisibility={()=>controls.onTogglePartVisibility?.(id)} onExitAllIsolate={controls.onExitAllIsolate}/>
    </ContextMenuContent>
  </ContextMenu>;
}
