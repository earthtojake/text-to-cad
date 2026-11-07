/**
 * The board's 3D models table (`client.boardModels`, `GET /api/v1/documents/kicad_pcb/<id>/models`): each
 * model name its footprints write, the STEP the engine serves by a document id or why there is none, as
 * the computer has it now. Asked again on every revision of the board and when the window takes the focus
 * back (a model file added or edited meanwhile: its stamp is in the table). A small JSON the server answers
 * from `stat` alone, so the Selected pane's 3D model fact and the Parts' No 3D model block read it in 2D
 * too; the meshes themselves are the 3D view's (`Board3dView.jsx`). The same table answered again is the
 * same object, so nothing downstream rebuilds. Null until it is in, or where the host serves none.
 *
 * Importing this module has no environmental effects.
 */
import { useEffect, useState } from "react";

export function useBoardModels({ client, file, revision = "", enabled = true }) {
  const [table, setTable] = useState(null);
  const [focus, setFocus] = useState(0);
  useEffect(() => {
    if (!enabled) return undefined;
    const regained = () => setFocus(count => count + 1);
    window.addEventListener("focus", regained);
    return () => window.removeEventListener("focus", regained);
  }, [enabled]);
  useEffect(() => {
    if (!enabled || !file || typeof client?.boardModels !== "function") return undefined;
    const controller = new AbortController();
    client.boardModels(file, { signal: controller.signal })
      .then(next => setTable(current => (current && JSON.stringify(current) === JSON.stringify(next) ? current : next)))
      .catch(() => {});
    return () => controller.abort();
  }, [client, file, revision, focus, enabled]);
  return enabled ? table : null;
}
