import { useLayoutEffect, useState } from "react";

/**
 * Preview's own scene while it is open: the editor's scene's sibling (`createSibling()`,
 * core's scene builders: its own objects, materials and look over the editor's geometry), made as
 * Preview opens and disposed as it closes, before the scene it shares geometry with. Null while
 * Preview is closed, or for a scene that has no sibling to give.
 *
 * @param {import("../scene.js").KitScene & { createSibling?: () => object } | null} scene  The editor's.
 * @param {boolean} open  `shell.previewing`.
 */
export function usePreviewScene(scene, open) {
  const [sibling, setSibling] = useState(null);
  useLayoutEffect(() => {
    if (!open || typeof scene?.createSibling !== "function") {
      setSibling(null);
      return undefined;
    }
    const next = scene.createSibling();
    setSibling(next);
    return () => next.dispose();
  }, [scene, open]);
  return sibling;
}
