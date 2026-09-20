import { useCallback, useMemo, useState } from "react";
import { computeNextSelectionIds } from "./referenceSelection.js";

const EMPTY = Object.freeze([]);

// A robot selection is either named mesh objects (component ids, which are mesh part
// ids) or one link. The viewport already picks, hovers and highlights mesh parts, and
// every part names its link, so a link is shown as all of its parts: no second picking
// system. A part that is not a named object stands for its link, in both directions.
export function useRobotComponentSelection(components, geometry, file) {
  const [selection, setSelection] = useState(null);
  const [hover, setHover] = useState(null);
  const parts = geometry?.parts || EMPTY;
  const partIdsByLink = useMemo(() => {
    const byLink = new Map();
    for (const part of parts) {
      const linkName = String(part?.linkName || ""), id = String(part?.id || "");
      if (!linkName || !id) continue;
      if (byLink.has(linkName)) byLink.get(linkName).push(id);
      else byLink.set(linkName, [id]);
    }
    return byLink;
  }, [parts]);
  const linkNameByPartId = useMemo(() => new Map(parts.map(part => [String(part?.id || ""), String(part?.linkName || "")])), [parts]);
  const componentIds = useMemo(() => new Set(components.map(component => component.id)), [components]);

  // Component ids belong to one built geometry. A link is named by the description,
  // so its selection survives the geometry being rebuilt as link meshes arrive.
  const selectedLinkName = selection?.file === file ? selection.linkName || "" : "";
  const selectedComponentIds = useMemo(
    () => (!selectedLinkName && selection?.file === file && selection?.geometry === geometry
      ? selection.ids.filter(id => componentIds.has(id)) : EMPTY),
    [selection, selectedLinkName, componentIds, file, geometry]
  );
  const selectedIds = selectedLinkName ? partIdsByLink.get(selectedLinkName) || EMPTY : selectedComponentIds;
  const hoveredLinkName = hover?.file === file ? hover.linkName || "" : "";
  const hoveredId = hoveredLinkName
    ? partIdsByLink.get(hoveredLinkName) || ""
    : hover?.file === file && hover?.geometry === geometry && componentIds.has(hover.id) ? hover.id : "";

  const selectLink = useCallback((linkName) => {
    setSelection({ file, geometry, ids: [], linkName: String(linkName || "") });
  }, [file, geometry]);
  const select = useCallback((id, { multiSelect = false } = {}) => {
    if (id && !componentIds.has(id) && linkNameByPartId.get(id)) {
      selectLink(linkNameByPartId.get(id));
      return;
    }
    const nextId = componentIds.has(id) ? id : "";
    setSelection((current) => ({
      file,
      geometry,
      linkName: "",
      ids: nextId ? computeNextSelectionIds(
        current?.file === file && current?.geometry === geometry && !current.linkName ? current.ids : [],
        nextId,
        { multiSelect }
      ) : []
    }));
  }, [componentIds, linkNameByPartId, selectLink, file, geometry]);
  const hoverComponent = useCallback((id) => {
    const linkName = id && !componentIds.has(id) ? linkNameByPartId.get(id) || "" : "";
    setHover(linkName ? { file, geometry, id: "", linkName } : { file, geometry, id, linkName: "" });
  }, [componentIds, linkNameByPartId, file, geometry]);
  const hoverLink = useCallback((linkName) => setHover({ file, geometry, id: "", linkName: String(linkName || "") }), [file, geometry]);
  return { selectedIds, selectedComponentIds, selectedLinkName, hoveredId, select, selectLink, hover: hoverComponent, hoverLink };
}
