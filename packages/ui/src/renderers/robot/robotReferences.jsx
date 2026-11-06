import { useCallback, useMemo } from "react";
import { useI18n } from "@cad/ui/i18n";
import { formatPromptReference } from "@cad/core/prompt";
import { isLabelSelector } from "@cad/core/lib/cadRefs.js";
import { robotComponentItem, robotLinkItem } from "./LinkDetails.jsx";
import { buildRobotTree, robotLinkFacts, robotLinkNodeId } from "./robotTree.js";

// A link named by its label, as a file the engine does not draw names a pick (`cadRefs.js`):
// `robot.urdf#upper_arm`. A name outside it (a hyphen, a dot) has no reference to give, and is left
// out of the prompt.
const EMPTY = Object.freeze([]);

/**
 * A robot's picks described, as the Selected pane, their chips' cards and the hover tip read them
 * (`kit/inspector/inspect.js`): a link by its name (`robotLinkItem`), a named mesh object by its id
 * (`robotComponentItem`). Null for neither.
 *
 * @param {{ robot: object | null, components?: object[], selectLink?: ((name: string) => void) | null,
 *   onOpenFile?: ((path: string) => void) | null, groupNamesByLink?: Map<string, string[]> | null,
 *   resource?: import("@cad/core/prompt").ResourceRef | null }} options
 */
export function useRobotDescribe({ robot, components = EMPTY, selectLink = null, onOpenFile = null, groupNamesByLink = null, resource = null }) {
  const { t } = useI18n();
  // A link named in a card can be followed when the Links tree has its row: a frame-only root has none.
  const tree = useMemo(() => (robot ? buildRobotTree(robot, { components }) : null), [robot, components]);
  return useCallback((id) => {
    const component = components.find(item => item.id === id);
    if (component) return robotComponentItem(component, t);
    if (!robot || !tree) return null;
    const facts = robotLinkFacts(robot, id, { groupNamesByLink });
    if (!facts || !(robot.links || []).some(link => String(link?.name || "") === id)) return null;
    const hasLinkRow = name => tree.nodesById.has(robotLinkNodeId(name));
    const reference = resource?.kind === "workspace-file" && isLabelSelector(String(id || "")) ? id : "";
    return robotLinkItem(facts, { reference, onOpenFile, onSelectLink: selectLink, hasLinkRow, t });
  }, [robot, tree, components, selectLink, onOpenFile, groupNamesByLink, resource, t]);
}

/**
 * The hover tip's words for a robot's pick (`kit/inspector/inspect.js`'s `tip`), from the description as it
 * stands, building no facts: a link's name and the type of the joint that holds it ("Root link" for the
 * root), a mesh object's name and its link.
 */
export function useRobotTip({ robot, components = EMPTY }) {
  const { t } = useI18n();
  return useCallback((id) => {
    const component = components.find(item => item.id === id);
    if (component) return [component.name || component.link, component.link].filter(Boolean).join(" · ");
    if (!robot || !(robot.links || []).some(link => String(link?.name || "") === id)) return "";
    const joint = (robot.joints || []).find(item => String(item?.child || "") === id);
    return `${id} · ${joint ? String(joint.type || "") : t("robot.rootLink")}`;
  }, [robot, components, t]);
}

/**
 * What is picked in a robot, as its frame reads it (`kit/inspector/inspect.js`): its links, then its
 * mesh objects, each described (`describe`), what the pointer is on in the view (`pointed`), and what a
 * row does — a link's selects that link, an object's that object.
 */
export function useRobotInspect({ selection, components = EMPTY, describe, tip = null, frame = null, copyText = null, enabled = true }) {
  const { selectedLinkNames, selectedComponentIds, selectLink, select, hoverLink, hover, pointed } = selection;
  const selected = useMemo(() => [...selectedLinkNames, ...selectedComponentIds], [selectedLinkNames, selectedComponentIds]);
  const isComponent = useCallback(id => components.some(component => component.id === id), [components]);
  const pick = useCallback((id, options) => (isComponent(id) ? select(id, options) : selectLink(id, options)), [isComponent, select, selectLink]);
  const light = useCallback(id => (isComponent(id) ? hover(id) : hoverLink(id)), [isComponent, hover, hoverLink]);
  return useMemo(() => (enabled ? { selected, describe, tip, hovered: pointed || "", select: pick, hover: light, frame, copyText, data: "links" } : null),
    [enabled, selected, describe, tip, pointed, pick, light, frame, copyText]);
}

/**
 * What is selected in a robot, for Quick Edit: its references — each selected link by name, and a
 * selected mesh object by the link it belongs to, in the file on screen (`resource`) — and its
 * chips (`kit/tools/quick-edit/ReferenceChips.jsx`): a link or an object each, its card what the
 * description says of it (`describe`, the Selected pane's: a link's inertial, geometry and joints;
 * an object's link, triangles and size), lit in the view while the pointer rests on it, dropped from
 * the selection by its X. A click on a chip copies its link's reference (`/path/robot.urdf#upper_arm`);
 * a link's card shows its name as its ID.
 *
 * @param {{ robot: object | null, components?: object[], selection: ReturnType<typeof import("./useLinkSelection.js").useLinkSelection>,
 *   resource: import("@cad/core/prompt").ResourceRef | null, describe: (id: string) => object | null }} options
 */
export function useRobotReferences({ robot, components = EMPTY, selection, resource, describe }) {
  const { selectedLinkNames, selectedComponentIds, selectLink, select, hoverLink, hover } = selection;
  return useMemo(() => {
    const objects = components.filter(component => selectedComponentIds.includes(component.id));
    const names = [...new Set([...selectedLinkNames, ...objects.map(component => component.link)])].filter(name => isLabelSelector(String(name || "")));
    const reference = name => resource?.kind === "workspace-file" && isLabelSelector(String(name || ""))
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [name] } } : null;
    const references = names.map(reference).filter(Boolean);
    const copy = name => { const value = reference(name); return value ? { copy: formatPromptReference(value) } : {}; };
    const chips = [
      ...selectedLinkNames.map(name => ({ key: `link:${name}`, label: name, glyph: "solid", ...copy(name), ...(reference(name) ? { id: name } : {}),
        detail: robot ? describe(name) : null,
        onRemove: () => selectLink(name, { multiSelect: true }),
        onHover: on => hoverLink(on ? name : "") })),
      ...objects.map(component => ({ key: `object:${component.id}`, label: component.name || component.link, glyph: "solid", ...copy(component.link),
        detail: describe(component.id),
        onRemove: () => select(component.id, { multiSelect: true }),
        onHover: on => hover(on ? component.id : "") })),
    ];
    return { references, chips };
  }, [robot, components, selectedLinkNames, selectedComponentIds, resource, describe, selectLink, select, hoverLink, hover]);
}
