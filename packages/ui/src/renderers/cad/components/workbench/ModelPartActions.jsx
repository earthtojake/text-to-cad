import { Eye, EyeOff, Focus, X } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';

export default function ModelPartActions({ node, controls, disabled }) {
  const {focusedNodeIds=[], onFocusTreeNode, onUnfocusTreeNode, onTogglePartVisibility, isAssemblyView} = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  return <div className="flex shrink-0 items-center">
    {isAssemblyView && <Button variant="ghost" size="icon-xs" disabled={disabled}
      aria-label={`${focused ? 'Exit isolate' : 'Isolate'} ${node.label}`} title={focused ? 'Exit isolate' : 'Isolate'}
      onClick={() => focused ? onUnfocusTreeNode?.(node.selectionId) : onFocusTreeNode?.(node.selectionId)}>
      {focused ? <X className="size-3.5"/> : <Focus className="size-3.5"/>}
    </Button>}
    <Button variant="ghost" size="icon-xs" disabled={disabled || focused} aria-label={`${hidden ? 'Reveal' : 'Hide'} ${node.label}`}
      title={hidden ? 'Reveal' : 'Hide'} onClick={() => onTogglePartVisibility?.(node.selectionId)}>
      {hidden ? <EyeOff className="size-3.5"/> : <Eye className="size-3.5"/>}
    </Button>
  </div>;
}
