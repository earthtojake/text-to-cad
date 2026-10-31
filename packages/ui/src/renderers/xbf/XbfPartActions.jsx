import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Eye, EyeOff, Focus } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';
import { cn } from '@text-to-cad/ui/utils';
import { treeRowActionsClass } from '@text-to-cad/ui/primitives/tree-row';
import { useControlUsage } from '../../usage/controls.js';
import { useI18n } from "@text-to-cad/ui/i18n";

// A row's actions show on hover (or keyboard focus) and stay shown while they are ON: an
// isolated row keeps its lit Isolate, a hidden row its crossed-out eye, so what is isolated
// or hidden can be read down the tree without hovering. Isolate is an assembly's; a single
// part has nothing to isolate it from.
const REVEAL_ON_HOVER = 'opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100';

/**
 * Whether a row's actions are showing without a hover — an isolated row's lit Isolate, a hidden
 * row's crossed-out eye — and how much of the row's right end they take: the row's name fades out
 * under them (`ROW_NAME_UNDER_ACTIONS`), never a backing drawn behind them.
 */
export function rowActionsLayout(node, controls) {
  const { focusedNodeIds = [], isAssemblyView, onFocusTreeNode } = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const canIsolate = isAssemblyView && typeof onFocusTreeNode === 'function';
  return { shown: Boolean(node.selectionId) && (focused || hidden), width: canIsolate ? '2.5rem' : '1.5rem' };
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
  const persistent = focused || hidden;
  return <div data-row-actions="" className={treeRowActionsClass(persistent)}>
    {canIsolate && <TooltipHint content={focused ? t("tree.exitIsolate") : t("tree.isolate")}><Button variant="ghost" size="icon-xs" disabled={disabled || hidden} aria-label={isolateLabel} aria-pressed={focused}
      className={cn('h-5 w-4', focused ? 'text-foreground' : cn('text-muted-foreground', REVEAL_ON_HOVER))}
      onClick={() => { if (!focused) usage.used('isolate'); return focused ? onUnfocusTreeNode?.(node.selectionId) : onFocusTreeNode(node.selectionId); }}>
      <Focus className="size-3"/>
    </Button></TooltipHint>}
    <TooltipHint content={hidden ? t("tree.reveal") : t("tree.hide")}><Button variant="ghost" size="icon-xs" disabled={disabled || focused} aria-label={t(hidden ? "tree.revealNamed" : "tree.hideNamed", { name: node.label })}
      className={cn('h-5 w-4 text-muted-foreground', !hidden && REVEAL_ON_HOVER)}
      onClick={() => { usage.used('tree_visibility'); onTogglePartVisibility?.(node.selectionId); }}>
      {hidden ? <EyeOff className="size-3"/> : <Eye className="size-3"/>}
    </Button></TooltipHint>
  </div>;
}
