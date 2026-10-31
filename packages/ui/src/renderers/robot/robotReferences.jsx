import { useMemo } from "react";
import { formatPromptReference } from "@text-to-cad/core/prompt";
import { isLabelSelector } from "@text-to-cad/core/lib/cadRefs.js";
import RobotComponentDetails, { RobotLinkDetails } from "./LinkDetails.jsx";
import { buildRobotTree, robotLinkFacts, robotLinkNodeId } from "./robotTree.js";

// A link named by its label, as a file the engine does not draw names a pick (`cadRefs.js`):
// `robot.urdf#upper_arm`. A name outside it (a hyphen, a dot) has no reference to give, and is left
// out of the prompt.
const EMPTY = Object.freeze([]);

/**
 * What is selected in a robot, for Quick Edit: its references — each selected link by name, and a
 * selected mesh object by the link it belongs to, in the file on screen (`resource`) — and its
 * chips (`kit/tools/quick-edit/ReferenceChips.jsx`): a link or an object each, its card what the
 * description says of it (a link's inertial, geometry and joints; an object's link, triangles and
 * size), lit in the view while the pointer rests on it, dropped from the selection by its X. A
 * click on a chip copies its link's reference (`/path/robot.urdf#upper_arm`); a link's card shows
 * its name as its ID.
 *
 * @param {{ robot: object | null, components?: object[], selection: ReturnType<typeof import("./useLinkSelection.js").useLinkSelection>,
 *   resource: import("@text-to-cad/core/prompt").ResourceRef | null, onOpenFile?: ((path: string) => void) | null,
 *   meshPath?: ((filename: string) => string) | null, groupNamesByLink?: Map<string, string[]> | null }} options
 */
export function useRobotReferences({ robot, components = EMPTY, selection, resource, onOpenFile = null, meshPath = null, groupNamesByLink = null }) {
  const { selectedLinkNames, selectedComponentIds, selectLink, select, hoverLink, hover } = selection;
  // A link named in a card can be followed when the Links tree has its row: a frame-only root has none.
  const tree = useMemo(() => (robot ? buildRobotTree(robot, { components }) : null), [robot, components]);
  return useMemo(() => {
    const hasLinkRow = name => Boolean(tree?.nodesById.has(robotLinkNodeId(name)));
    const objects = components.filter(component => selectedComponentIds.includes(component.id));
    const names = [...new Set([...selectedLinkNames, ...objects.map(component => component.link)])].filter(name => isLabelSelector(String(name || "")));
    const reference = name => resource?.kind === "workspace-file" && isLabelSelector(String(name || ""))
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [name] } } : null;
    const references = names.map(reference).filter(Boolean);
    const copy = name => { const value = reference(name); return value ? { copy: formatPromptReference(value) } : {}; };
    const chips = [
      ...selectedLinkNames.map(name => {
        const facts = robot ? robotLinkFacts(robot, name, { groupNamesByLink }) : null;
        return { key: `link:${name}`, label: name, glyph: "solid", ...copy(name), ...(reference(name) ? { id: name } : {}),
          card: facts ? <RobotLinkDetails facts={facts} meshPath={meshPath} onOpenFile={onOpenFile} onSelectLink={selectLink} hasLinkRow={hasLinkRow}/> : null,
          onRemove: () => selectLink(name, { multiSelect: true }),
          onHover: on => hoverLink(on ? name : "") };
      }),
      ...objects.map(component => ({ key: `object:${component.id}`, label: component.name || component.link, glyph: "solid", ...copy(component.link),
        card: <RobotComponentDetails components={components} selectedIds={[component.id]}/>,
        onRemove: () => select(component.id, { multiSelect: true }),
        onHover: on => hover(on ? component.id : "") })),
    ];
    return { references, chips };
  }, [robot, tree, components, selectedLinkNames, selectedComponentIds, resource, onOpenFile, meshPath, groupNamesByLink, selectLink, select, hoverLink, hover]);
}
