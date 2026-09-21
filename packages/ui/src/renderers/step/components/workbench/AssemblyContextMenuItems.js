import { Fragment } from "react";

// The part menu: what can be done to one node of the model, wherever it was
// asked for. The camera is NOT here — framing lives in the zoom menu beside the
// Inspector's readout, so no item of this menu can contradict the active tool.
//
// It is ONE list (`assemblyPartMenuEntries`) with two presentations: the Features
// tree renders it into its own context menu (`AssemblyPartMenuItems`), and the
// viewport hands the same entries to the shell's viewport menu, which owns the
// gesture, the anchor and the dismissal. Neither can drift from the other.
function AssemblyContextMenuItemLabel({ children }) {
  return <span className="min-w-0 truncate">{children}</span>;
}

const entry = (id, text, disabled, onSelect, separatorBefore = false) => ({
  id, label: <AssemblyContextMenuItemLabel>{text}</AssemblyContextMenuItemLabel>, disabled: disabled === true, separatorBefore, onSelect
});

/**
 * The entries of the part menu for the descriptor the workspace builds for a node
 * (`assemblyNodeMenu` in `CadFileView`): `{ id, label, disabled, separatorBefore, onSelect }`.
 *
 * `actions` holds the handlers, each called with the descriptor; `onAddToPrompt` is
 * offered only where the host has somewhere to put it, so a caller leaves it out
 * otherwise. `disabled` disables every item at once, for a tree whose selection is blocked.
 */
export function assemblyPartMenuEntries(menu, { disabled = false, actions = {} } = {}) {
  const run = (action) => () => action?.(menu);
  const off = (flag) => disabled || flag === true;
  const copyDisabled = disabled || !String(menu.copyText || "").trim();
  const entries = [];
  if (actions.onAddToPrompt) entries.push(entry("add-to-prompt", "Add to prompt", copyDisabled, run(actions.onAddToPrompt)));
  entries.push(entry("copy-reference", "Copy Reference", copyDisabled, run(actions.onCopyReference)));
  entries.push(entry("select", menu.selected === true ? "Deselect" : "Select", off(menu.selectDisabled), run(actions.onSelect), true));
  if (menu.showIsolate !== false) {
    entries.push(entry("isolate", menu.focused === true ? "Exit isolate" : "Isolate", off(menu.isolateDisabled), run(actions.onIsolate)));
  }
  if (menu.showExitAllIsolate === true) {
    entries.push(entry("exit-all-isolates", "Exit all isolates", off(menu.exitAllIsolateDisabled), run(actions.onExitAllIsolate)));
  }
  // One separator ahead of the visibility group, whichever of its items comes first.
  let visibilitySeparator = true;
  const visibility = (id, text, isDisabled, onSelect) => {
    entries.push(entry(id, text, isDisabled, onSelect, visibilitySeparator));
    visibilitySeparator = false;
  };
  if (menu.showHideOther !== false) visibility("hide-others", "Hide others", off(menu.hideOtherDisabled), run(actions.onHideOther));
  if (menu.showHideAll === true) {
    visibility("hide-all", String(menu.hideAllLabel || "").trim() || "Show all", off(menu.hideAllDisabled), run(actions.onHideAll));
  }
  if (menu.showVisibility !== false) {
    visibility("visibility", menu.hidden === true ? "Reveal" : "Hide", off(menu.visibilityDisabled),
      run(menu.hidden === true ? actions.onReveal : actions.onHide));
  }
  if (menu.showExpandCollapse === true) {
    entries.push(entry("expand", "Expand", disabled || menu.expandSelectedDisabled !== false, run(actions.onExpandSelected), true));
    entries.push(entry("collapse", "Collapse", disabled || menu.collapseSelectedDisabled !== false, run(actions.onCollapseSelected)));
    entries.push(entry("expand-all", "Expand all", disabled || menu.expandAllDisabled !== false, run(actions.onExpandAll)));
    entries.push(entry("collapse-all", "Collapse all", disabled || menu.collapseAllDisabled !== false, run(actions.onCollapseAll)));
  }
  return entries;
}

/**
 * What a secondary tap on EMPTY space offers: the model as a whole (Show all, Expand all,
 * Collapse all). The workspace only builds this descriptor when one of them can do something.
 */
export function modelMenuEntries(menu, { actions = {} } = {}) {
  const run = (action) => () => action?.(menu);
  const entries = [];
  if (menu.showShowAll === true) entries.push({ id: "show-all", label: "Show all", onSelect: run(actions.onHideAll) });
  if (menu.showExpandCollapse === true) {
    entries.push({ id: "expand-all", label: "Expand all", disabled: menu.expandAllDisabled === true,
      separatorBefore: menu.showShowAll === true, onSelect: run(actions.onExpandAll) });
    entries.push({ id: "collapse-all", label: "Collapse all", disabled: menu.collapseAllDisabled === true, onSelect: run(actions.onCollapseAll) });
  }
  return entries;
}

/** The viewport's menu for whatever the workspace resolved under the press. */
export function viewportMenuEntries(menu, options) {
  if (!menu) return [];
  return menu.global === true ? modelMenuEntries(menu, options) : assemblyPartMenuEntries(menu, options);
}

/** That same list as the items of a menu primitive (the Features tree's context menu). */
export function AssemblyPartMenuItems({ menu, Item, Separator, itemClassName = "text-xs", disabled = false, actions = {} }) {
  return assemblyPartMenuEntries(menu, { disabled, actions }).map((item) => (
    <Fragment key={item.id}>
      {item.separatorBefore ? <Separator /> : null}
      <Item className={itemClassName} disabled={item.disabled} onSelect={item.onSelect}>{item.label}</Item>
    </Fragment>
  ));
}
