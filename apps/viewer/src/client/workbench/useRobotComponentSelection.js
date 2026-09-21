import { useCallback, useState } from "react";
import { computeNextSelectionIds } from "./referenceSelection";

export function useRobotComponentSelection(components, geometry, file) {
  const [selection, setSelection] = useState(null);
  const [hover, setHover] = useState(null);
  const validId = (id) => components.some((component) => component.id === id);
  const matches = (state) => state?.file === file && state?.geometry === geometry;
  const selectedIds = matches(selection) ? selection.ids.filter(validId) : [];
  const hoveredId = matches(hover) && validId(hover.id) ? hover.id : "";
  const select = useCallback((id, { multiSelect = false } = {}) => {
    const nextId = components.some((component) => component.id === id) ? id : "";
    setSelection((current) => ({
      file,
      geometry,
      ids: nextId ? computeNextSelectionIds(
        current?.file === file && current?.geometry === geometry ? current.ids : [],
        nextId,
        { multiSelect }
      ) : []
    }));
  }, [components, file, geometry]);
  const hoverComponent = useCallback((id) => setHover({ file, geometry, id }), [file, geometry]);
  return { selectedIds, hoveredId, select, hover: hoverComponent };
}
