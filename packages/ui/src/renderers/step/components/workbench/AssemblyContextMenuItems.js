import { Fragment } from "react";

// The part menu: what can be done to one node of the model, wherever it was
// asked for.
//
// It is ONE list (`assemblyPartMenuEntries`) with two presentations: the Features
// tree renders it into its own context menu (`AssemblyPartMenuItems`), and the
// viewport hands the same entries to the shell's viewport menu, which owns the
// gesture, the anchor and the dismissal. Neither can drift from the other.
//
// Its last group is the model's framing, and it is the only zoom control the
// viewer has left: a percentage readout and its menu used to sit in the panel
// header, and nothing replaced them. Framing cannot contradict the active tool,
// and every action here returns to Select first anyway (`partMenuActions`).
function AssemblyContextMenuItemLabel({ children }) {
  return <span className="min-w-0 truncate">{children}</span>;
}

const entry = (id, text, disabled, onSelect, separatorBefore = false) => ({
  id, label: <AssemblyContextMenuItemLabel>{text}</AssemblyContextMenuItemLabel>, disabled: disabled === true, separatorBefore, onSelect
});

/**
 * The framing group, identical wherever the menu was asked for: over a part, over a
 * tree row, or over empty space. "Zoom to fit" frames the whole model from where the
 * camera looks now — the one act the viewer calls `resetZoom` — and "Zoom to selection"
 * frames what is selected, so it is off when nothing is (`menu.zoomSelectionAvailable`).
 */
function zoomEntries(menu, { disabled = false, actions = {} } = {}) {
  const run = (action) => () => action?.(menu);
  return [
    entry("zoom-fit", "Zoom to fit", disabled, run(actions.onZoomFit), true),
    entry("zoom-selection", "Zoom to selection", disabled || menu.zoomSelectionAvailable !== true, run(actions.onZoomSelection))
  ];
}

/**
 * The entries of the part menu for the descriptor the workspace builds for a node
 * (`assemblyNodeMenu` in `CadFileView`): `{ id, label, disabled, separatorBefore, onSelect }`.
 *
 * `actions` holds the handlers, each called with the descriptor; `onAddToPrompt` is
 * offered only where the host has somewhere to put it, so a caller leaves it out
 * otherwise. `disabled` disables every item at once, for a tree whose selection is blocked.
 */
/**
 * The reference group that opens a menu about something with a reference: Add to prompt (only
 * where the host offers it) and Copy Reference, both off when there is nothing to copy.
 */
function referenceEntries(menu, { disabled = false, actions = {} } = {}) {
  const run = (action) => () => action?.(menu);
  const copyDisabled = disabled || !String(menu.copyText || "").trim();
  const entries = [];
  if (actions.onAddToPrompt) entries.push(entry("add-to-prompt", "Add to prompt", copyDisabled, run(actions.onAddToPrompt)));
  entries.push(entry("copy-reference", "Copy Reference", copyDisabled, run(actions.onCopyReference)));
  return entries;
}

export function assemblyPartMenuEntries(menu, { disabled = false, actions = {} } = {}) {
  const run = (action) => () => action?.(menu);
  const off = (flag) => disabled || flag === true;
  const entries = referenceEntries(menu, { disabled, actions });
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
  entries.push(...zoomEntries(menu, { disabled, actions }));
  return entries;
}

/**
 * What a secondary tap on EMPTY space offers: the model as a whole (Show all, Expand all,
 * Collapse all) and the framing group — which is why this menu always has something to
 * show, and why somebody who has zoomed off the model can press anywhere to get it back.
 * A lone part's model menu is also the menu over the part itself, so when the descriptor
 * carries the whole part's reference (`menu.copyText`) it opens with the part menu's
 * reference group.
 */
export function modelMenuEntries(menu, { actions = {} } = {}) {
  const run = (action) => () => action?.(menu);
  const entries = String(menu.copyText || "").trim() ? referenceEntries(menu, { actions }) : [];
  if (menu.showShowAll === true) {
    entries.push({ id: "show-all", label: "Show all", separatorBefore: entries.length > 0, onSelect: run(actions.onHideAll) });
  }
  if (menu.showExpandCollapse === true) {
    entries.push({ id: "expand-all", label: "Expand all", disabled: menu.expandAllDisabled === true,
      separatorBefore: entries.length > 0, onSelect: run(actions.onExpandAll) });
    entries.push({ id: "collapse-all", label: "Collapse all", disabled: menu.collapseAllDisabled === true, onSelect: run(actions.onCollapseAll) });
  }
  const zoom = zoomEntries(menu, { actions });
  // Nothing above it: the group opens the menu rather than following a separator.
  if (!entries.length) zoom[0] = { ...zoom[0], separatorBefore: false };
  entries.push(...zoom);
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
