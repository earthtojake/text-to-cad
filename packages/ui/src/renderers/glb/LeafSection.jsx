import { useCallback, useMemo } from "react";
import { createPromptContext, referencePart, textPart } from "@text-to-cad/core/prompt";
import { cn } from "@text-to-cad/ui/utils";
import { PromptContextAction } from "../../host/PromptContextAction.js";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { InfoRow, MonoValue } from "../kit/inspector/referenceRows.jsx";

/** The line an agent needs: which file, which leaf, and where in the source it was written. */
export function leafPromptText(fileName, leaf) {
  const kind = leaf.kind ? ` (${leaf.kind})` : "";
  const site = leaf.site ? `, written at ${leaf.site}` : "";
  return `${fileName}: leaf "${leaf.label}"${kind}${site}`;
}

/**
 * The prompt context for the selected leaves of an implicit part's GLB: the file as a
 * whole-resource reference (a GLB has no CAD selector), and one line per leaf naming
 * it and the source line that made it — which is what the agent edits.
 */
export function createLeafPromptContext({ resource, fileName, leaves }) {
  const parts = [referencePart({ resource: { ...resource }, target: { kind: "whole-resource" }, label: leaves.map(leaf => leaf.label).join(", ") }, "part")];
  leaves.forEach((leaf, index) => parts.push(textPart(leafPromptText(fileName, leaf), `leaf-${index}`)));
  return createPromptContext(parts);
}

/**
 * Select's panels for an implicit part's GLB: the leaves the file names, and the
 * Reference for the picked ones with the action that hands them to the agent.
 *
 * @param {{ leaves: object[], selection: object, resource: object, fileName: string, active?: boolean,
 *   onResult?: (result: object) => void }} props
 */
export default function LeafSection({ leaves, selection, resource, fileName, active = true, onResult = null }) {
  const { selected, select, clear, hover } = selection;
  const picked = useMemo(() => leaves.filter(leaf => selected.includes(leaf.id)), [leaves, selected]);
  const createContext = useCallback(() => createLeafPromptContext({ resource, fileName, leaves: picked }), [resource, fileName, picked]);
  const title = picked.length === 1 ? picked[0].label : `${picked.length} leaves`;

  return <>
    <ToolPanel label="Leaves" fit="tree" hidden={!active}>
      <ul className="m-0 list-none p-0" role="listbox" aria-label="Leaves" aria-multiselectable="true">
        {leaves.map(leaf => {
          const isSelected = selected.includes(leaf.id);
          return <li key={leaf.id} role="option" aria-selected={isSelected}
            className={cn("flex cursor-default items-baseline gap-2 px-2 py-1 text-xs", isSelected ? "bg-accent text-accent-foreground" : "hover:bg-muted")}
            onClick={event => select(leaf.id, { multiSelect: event.shiftKey || event.metaKey || event.ctrlKey })}
            onPointerEnter={() => hover(leaf.id)} onPointerLeave={() => hover("")}>
            <span className="truncate">{leaf.label}</span>
            <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">{leaf.kind}</span>
          </li>;
        })}
      </ul>
    </ToolPanel>
    {picked.length ? <ToolPanel title={title} label="Reference details" closeLabel="Clear selection" fit="details" capped hidden={!active} onClose={clear}>
      <div className="flex flex-col gap-1 px-2 pb-2">
        {picked.map(leaf => <div key={leaf.id} className="flex flex-col">
          {picked.length > 1 ? <InfoRow label="Leaf"><MonoValue>{leaf.label}</MonoValue></InfoRow> : null}
          <InfoRow label="Kind"><MonoValue>{leaf.kind || "leaf"}</MonoValue></InfoRow>
          {leaf.site ? <InfoRow label="Source" title="The line of the part's script that made this leaf"><MonoValue>{leaf.site}</MonoValue></InfoRow> : null}
          <InfoRow label="Triangles"><MonoValue>{leaf.triangles}</MonoValue></InfoRow>
        </div>)}
        <div className="pt-1">
          <PromptContextAction size="sm" variant="secondary" createContext={createContext} onResult={onResult || undefined} />
        </div>
      </div>
    </ToolPanel> : null}
  </>;
}
