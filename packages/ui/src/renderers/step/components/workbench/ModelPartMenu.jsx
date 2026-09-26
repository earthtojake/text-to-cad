import { useEffect } from 'react';
import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from '@hardcore/ui/primitives/context-menu';
import { useHostReference } from '../../file-view/hostReference.js';
import { AssemblyPartMenuItems } from './AssemblyContextMenuItems.js';

// A Features tree row's menu. It is the SAME menu the viewport offers over what the
// row stands for — one descriptor per kind and one set of actions
// (`controls.partMenuActions`) — and unlike the viewport's it is available under
// any tool, because every one of its actions returns to Select before it runs.
//
// A part row is a node of the model: its menu is the part menu (`controls.menuForNode`).
// Every other selectable row — a feature, a group, a body — stands for faces and edges,
// and its menu is the viewport's menu over that topology (`controls.menuForReferences`):
// never its owning part's, whose Hide or Select would act on more than the row names.

/** Built only once the menu is actually open, so a tree of rows never pays for it. */
function TreeNodeMenuItems({ menu, actions, disabled }) {
  const hostReference = useHostReference();
  if (!menu) return null;
  return <AssemblyPartMenuItems menu={menu} Item={ContextMenuItem} Separator={ContextMenuSeparator}
    disabled={disabled}
    actions={{ ...actions, onAddToPrompt: hostReference?.canAddToPrompt ? actions.onAddToPrompt : undefined }} />;
}

function PartMenuItems({ id, controls, disabled }) {
  return <TreeNodeMenuItems menu={controls.menuForNode(id)} actions={controls.partMenuActions || {}} disabled={disabled} />;
}

// `feature` is the row's own reach into the tree: the reference ids its topology resolves to
// (none while that topology is loading), how to load it, and the row's own click.
function FeatureMenuItems({ node, controls, feature, disabled }) {
  const referenceIds = feature.referenceIds(node);
  const waiting = referenceIds.length === 0;
  // A row whose faces are not loaded yet asks for them the moment its menu opens, as its click
  // would; the menu fills in when they arrive rather than offering nothing to copy.
  useEffect(() => {
    if (waiting && node.occurrenceId) feature.loadTopology?.([node.occurrenceId]);
  }, [waiting, node.occurrenceId, feature.loadTopology]);
  const actions = controls.partMenuActions || {};
  const menu = controls.menuForReferences(referenceIds, node.label);
  // Select here IS the row's click, so the two cannot disagree about what the row selects
  // (and it waits for loading faces as the click does); Deselect is the viewport's own.
  return <TreeNodeMenuItems menu={menu} disabled={disabled}
    actions={{ ...actions, onSelect: () => (menu.selected ? actions.onSelect?.(menu) : feature.choose(node)) }} />;
}

export default function ModelPartMenu({ node, controls, feature, disabled, children }) {
  const part = Boolean(node.selectionId && controls.menuForNode);
  const topology = !node.selectionId && Boolean(feature && controls.menuForReferences)
    && Boolean(node.faces?.length || node.edges?.length);
  if (!part && !topology) return children;
  return <ContextMenu><ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
    <ContextMenuContent className="w-44">
      {part
        ? <PartMenuItems id={node.selectionId} controls={controls} disabled={disabled} />
        : <FeatureMenuItems node={node} controls={controls} feature={feature} disabled={disabled} />}
    </ContextMenuContent>
  </ContextMenu>;
}
