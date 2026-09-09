/**
 * The standalone viewer's panel list.
 *
 * The nav row draws a toggle per panel and the column draws the open one, so
 * both have to agree about what there is — one declaration, read by both,
 * rather than a list in the row and another in the column.
 *
 * The declaration itself is the shared one (`cad-viewer/shell`'s `cadPanels`),
 * the same call the desktop app's CAD renderer makes: the theme editor and the
 * Inspector, with the file tree appended last by `panelsFor`. That is why the
 * two apps' rows carry the same buttons, in the same order, with the same
 * names and the same glyphs.
 */
import { useMemo } from "react";

import { cadPanels, panelsFor } from "@/shell/index.js";

/**
 * @param {object} chrome The surface's chrome contract (`file-view/CadFileView.js`).
 * @returns {import("@/shell/panels.js").FilePanel[]}
 */
export function useWorkspacePanels(chrome) {
  /*
    "Ready" is the surface having a file sheet with something in it. With no
    file open there is nothing to inspect and nothing to theme, so the tree is
    the only panel and the only toggle — which is the state a person arrives
    in, and the same answer the desktop app gives for a tab with no file.
  */
  const ready = Boolean(chrome.fileSheetKind) && !chrome.previewMode;
  const open = chrome.openPanel;
  return useMemo(() => panelsFor(cadPanels(ready), open), [ready, open]);
}
