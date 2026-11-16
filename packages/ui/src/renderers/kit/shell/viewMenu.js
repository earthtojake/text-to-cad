import { Fragment } from "react";
import { english } from "../../../i18n/core.js";

/**
 * The entries of every view's menu (`ViewportContextMenu.jsx` over the picture, a list row's own menu
 * beside it), the same groups in the same order whatever the file:
 *
 * 1. the reference: Copy Reference, what a pick would put in Quick Edit;
 * 2. the pick: Select or Deselect, Isolate or Exit isolate, Exit all isolates, then, in a 3D view, Select
 *    tangent faces and Select tangent edges where they apply (`tangentGroup`);
 * 3. what is shown: Hide others, Show all, Hide or Reveal (where the view hides anything);
 * 4. the view's own (a tree's Expand and Collapse, a schematic's sheets, a drawing's layers);
 * 5. the framing, last, always: Zoom to fit and Zoom to selection, which is off while nothing is picked.
 *
 * Over something, the menu opens with its reference; over empty space it is the view as a whole,
 * with the framing, so a press anywhere brings back a view zoomed off its picture. A renderer builds
 * its groups from these helpers and joins them (`menuGroups`), which puts a rule between groups.
 * An entry is `{ id, label, disabled, separatorBefore, onSelect }`, the shell menu's descriptor.
 */

function MenuItemLabel({ children }) {
  return <span className="min-w-0 truncate">{children}</span>;
}

/** One entry: its id (stable, what a test asks for), its words, and what it does. */
export function menuEntry(id, text, { disabled = false, onSelect = null, separatorBefore = false } = {}) {
  return { id, label: <MenuItemLabel>{text}</MenuItemLabel>, disabled: disabled === true, separatorBefore, onSelect };
}

/** The groups as one list: a rule before each group's first entry but the first group's; empty groups drop out. */
export function menuGroups(...groups) {
  const entries = [];
  for (const group of groups) {
    const items = (group || []).filter(Boolean);
    items.forEach((item, at) => entries.push({ ...item, separatorBefore: at === 0 && entries.length > 0 }));
  }
  return entries;
}

/** Copy Reference: off when there is nothing to copy. */
export function referenceGroup({ copyText = "", onCopy = null, disabled = false, t = english } = {}) {
  return [menuEntry("copy-reference", t("menu.copyReference"), { disabled: disabled || !String(copyText || "").trim(), onSelect: onCopy })];
}

/**
 * Select or Deselect, then Isolate or Exit isolate (where the view isolates: `isolated` true or
 * false, absent where it does not), then Exit all isolates while more than one thing is.
 */
export function pickGroup({ selected = false, onSelect = null, isolated = null, onIsolate = null, isolatedCount = 0, onExitIsolates = null,
  disabled = false, t = english } = {}) {
  const items = [menuEntry("select", selected ? t("menu.deselect") : t("tool.select"), { disabled, onSelect })];
  if (isolated !== null && onIsolate) items.push(menuEntry("isolate", isolated ? t("tree.exitIsolate") : t("tree.isolate"), { disabled, onSelect: onIsolate }));
  if (isolatedCount > 1 && onExitIsolates) items.push(menuEntry("exit-all-isolates", t("menu.exitAllIsolates"), { disabled, onSelect: onExitIsolates }));
  return items;
}

/**
 * Select tangent faces and Select tangent edges: actions, not settings (Fusion's and SolidWorks' tangent
 * chain), each adding the tangent chain of the face or edge pressed, and of those of its kind selected, to
 * the selection. Each is there only where it applies (`faces`, `edges`: over a face or while faces are
 * selected; likewise edges), so the group can be empty.
 */
export function tangentGroup({ faces = false, edges = false, onFaces = null, onEdges = null, disabled = false, t = english } = {}) {
  return [
    faces ? menuEntry("select-tangent-faces", t("menu.selectTangentFaces"), { disabled, onSelect: onFaces }) : null,
    edges ? menuEntry("select-tangent-edges", t("menu.selectTangentEdges"), { disabled, onSelect: onEdges }) : null,
  ].filter(Boolean);
}

/** The framing, the same everywhere: the whole picture, and what is picked (off while nothing is). */
export function zoomGroup({ onZoomFit = null, onZoomSelection = null, selectionAvailable = false, disabled = false, t = english } = {}) {
  return [
    menuEntry("zoom-fit", t("menu.zoomToFit"), { disabled, onSelect: onZoomFit }),
    menuEntry("zoom-selection", t("menu.zoomToSelection"), { disabled: disabled || !selectionAvailable || !onZoomSelection, onSelect: onZoomSelection })
  ];
}

/** Exit isolate, over empty space, while anything is isolated: the view as a whole comes back. */
export function exitIsolateEntry({ isolatedCount = 0, onExitIsolates = null, t = english } = {}) {
  return isolatedCount > 0 && onExitIsolates
    ? menuEntry("exit-all-isolates", isolatedCount > 1 ? t("menu.exitAllIsolates") : t("tree.exitIsolate"), { onSelect: onExitIsolates }) : null;
}

/** A list's row menu from the same entries (a menu primitive's `Item` and `Separator`): a row and the picture offer one menu. */
export function ViewMenuItems({ entries, Item, Separator, itemClassName = "text-xs" }) {
  return entries.map(item => <Fragment key={item.id}>
    {item.separatorBefore ? <Separator /> : null}
    <Item className={itemClassName} disabled={item.disabled} onSelect={() => item.onSelect?.()}>{item.label}</Item>
  </Fragment>);
}
