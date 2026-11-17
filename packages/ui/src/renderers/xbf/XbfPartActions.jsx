import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { Blend, Box, Eye, EyeOff, Focus, Layers2, X } from 'lucide-react';
import { Button } from '@cad/ui/primitives/button';
import { cn } from '@cad/ui/utils';
import { TreeRowActions } from '@cad/ui/primitives/tree-row';
import { useControlUsage } from '../../usage/controls.js';
import { useI18n } from "@cad/ui/i18n";

// A row's actions show on hover (or keyboard focus) and stay shown while they are ON: an
// isolated row's Isolate is its way out, an X, a hidden row keeps its crossed-out eye, so what is
// isolated or hidden can be read down the tree without hovering. Isolate is an assembly's; a single
// part has nothing to isolate it from.
// What a baked part's button goes to from what it shows now, with its hint and its name.
const SHOWN_NEXT = {
  exact: { value: 'concept', tip: 'menu.showConcept', named: 'tree.showConceptNamed' },
  concept: { value: 'both', tip: 'menu.showBoth', named: 'tree.showBothNamed' },
  both: { value: 'exact', tip: 'menu.showExact', named: 'tree.showExactNamed' }
};
const REVEAL_ON_HOVER = 'opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100';

/**
 * Whether a row's actions are showing without a hover — an isolated row's X, a hidden
 * row's crossed-out eye — and how many of them there are, which is how much of the row's right end
 * they take (the row's `actions`): the row's name fades out under them (`ROW_NAME_UNDER_ACTIONS`),
 * never a backing drawn behind them.
 */
export function rowActionsLayout(node, controls) {
  const { focusedNodeIds = [], isAssemblyView, onFocusTreeNode } = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const canIsolate = isAssemblyView && typeof onFocusTreeNode === 'function';
  // A part baked from a concept has one more: how it is shown, which stays in view while it is not its exact body.
  const shownAs = controls.representationOf?.(node) || null;
  return { shown: Boolean(node.selectionId) && (focused || hidden || Boolean(shownAs && shownAs !== 'exact')),
    count: (canIsolate ? 2 : 1) + (shownAs ? 1 : 0) };
}

export default function ModelPartActions({ node, controls, disabled }) {
  const {focusedNodeIds=[], onTogglePartVisibility, onFocusTreeNode, onUnfocusTreeNode, isAssemblyView} = controls;
  const usage = useControlUsage();
  const { t } = useI18n();
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const canIsolate = isAssemblyView && typeof onFocusTreeNode === 'function';
  const isolateLabel = t(focused ? "tree.exitIsolateNamed" : "tree.isolateNamed", { name: node.label });
  // The actions float over the row's right end rather than taking width from it: the name runs the
  // row's full width and fades out under them (`ROW_NAME_UNDER_ACTIONS`), with nothing drawn behind
  // the buttons, so the row reads in its own (hover) colour throughout.
  // How a part baked from a concept is shown: its exact body, the concept, both. The button wears what is shown
  // now and goes to the next; it stays in view while the part is not its exact body, as a hidden row's eye does.
  const shownAs = controls.representationOf?.(node) || null;
  const next = SHOWN_NEXT[shownAs];
  const ShownIcon = shownAs === 'concept' ? Blend : shownAs === 'both' ? Layers2 : Box;
  const persistent = focused || hidden || Boolean(shownAs && shownAs !== 'exact');
  return <TreeRowActions persistent={persistent}>
    {shownAs && <TooltipHint content={t(next.tip)}><Button variant="ghost" size="icon-xs" disabled={disabled || hidden} aria-label={t(next.named, { name: node.label })}
      className={cn('h-5 w-4', shownAs !== 'exact' ? 'text-foreground' : cn('text-muted-foreground', REVEAL_ON_HOVER))} data-shown-as={shownAs}
      onClick={() => controls.onShowAs?.(node, next.value)}>
      <ShownIcon className="size-3"/>
    </Button></TooltipHint>}
    {/* Isolated, the row's Isolate is the way out: an X, there the whole time, which leaves isolation. */}
    {canIsolate && <TooltipHint content={focused ? t("tree.exitIsolate") : t("tree.isolate")}><Button variant="ghost" size="icon-xs" disabled={disabled || hidden} aria-label={isolateLabel}
      className={cn('h-5 w-4', focused ? 'text-foreground' : cn('text-muted-foreground', REVEAL_ON_HOVER))} data-isolate-exit={focused ? '' : undefined}
      onClick={() => { if (!focused) usage.used('isolate'); return focused ? onUnfocusTreeNode?.(node.selectionId) : onFocusTreeNode(node.selectionId); }}>
      {focused ? <X className="size-3"/> : <Focus className="size-3"/>}
    </Button></TooltipHint>}
    <TooltipHint content={hidden ? t("tree.reveal") : t("tree.hide")}><Button variant="ghost" size="icon-xs" disabled={disabled || focused} aria-label={t(hidden ? "tree.revealNamed" : "tree.hideNamed", { name: node.label })}
      className={cn('h-5 w-4 text-muted-foreground', !hidden && REVEAL_ON_HOVER)}
      onClick={() => { usage.used('tree_visibility'); onTogglePartVisibility?.(node.selectionId); }}>
      {hidden ? <EyeOff className="size-3"/> : <Eye className="size-3"/>}
    </Button></TooltipHint>
  </TreeRowActions>;
}
