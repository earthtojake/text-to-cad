/**
 * The standalone viewer's half of the shared entry menu.
 *
 * What is IN the menu is `cad-viewer/shell`'s `entry-menu.js`, the same table
 * the desktop app draws from. What each item DOES is per host, and a browser
 * tab can do four of the thirteen: open a file, and put three names for it on
 * the clipboard. The rest — open with the default app, open with…, reveal,
 * rename, duplicate, move to trash, new file, new folder, open in terminal —
 * need an operating system to hand the request to, and a web page has none.
 *
 * They are absent as CAPABILITIES rather than present and broken. The menu is
 * filtered by the set below, so an item a browser cannot perform is not in the
 * menu at all, the keyboard shortcuts behind two of them (F2, ⌘⌫) do nothing,
 * and no code path here can be reached without the item that reaches it.
 */
import { useCallback, useMemo } from "react";

import { WEB_ENTRY_CAPABILITIES } from "@/shell/index.js";
import { cadFileParamForEntry, fileKey } from "@/workbench/sidebar";

/**
 * What this browser tab can do, given whether the backend can answer with a
 * path on disk.
 *
 * `Copy path` is an absolute path, which only means something when the viewer
 * is serving a local directory; a backend that is not drops it, and the menu
 * closes over the gap rather than offering an item that copies "".
 *
 * @param {boolean} canCopyFileAssetPaths
 * @returns {ReadonlySet<string>}
 */
export function webEntryCapabilities(canCopyFileAssetPaths) {
  if (canCopyFileAssetPaths) {
    return WEB_ENTRY_CAPABILITIES;
  }
  const capabilities = new Set(WEB_ENTRY_CAPABILITIES);
  capabilities.delete("copy-path");
  return capabilities;
}

/** Which OS the browser is on, for the menu's labels. Nothing here acts on it. */
export function currentPlatform() {
  const agent = typeof navigator === "undefined" ? "" : navigator.userAgent;
  return agent.includes("Macintosh") ? "darwin" : agent.includes("Windows") ? "win32" : "linux";
}

/**
 * The handler the shared menu calls when an item is chosen, over the surface's
 * own catalog and clipboard.
 *
 * @param {object} chrome The surface's chrome contract (`file-view/CadFileView.js`).
 */
export function useStandaloneEntryActions(chrome) {
  const { catalogEntries, onOpenPath, onCopyFileAssetReference } = chrome;

  // The menu deals in paths; the copy handler deals in catalog entries, which
  // carry the asset descriptors it needs. This is where the two meet.
  const entryForPath = useCallback(
    (path) => catalogEntries.find((entry) => cadFileParamForEntry(entry) === path) ?? null,
    [catalogEntries]
  );

  const onAction = useCallback((action, target) => {
    if (action === "open") {
      onOpenPath(target.path);
      return;
    }
    const entry = entryForPath(target.path);
    if (!entry || typeof onCopyFileAssetReference !== "function") {
      return;
    }
    if (action === "copy-path") {
      void onCopyFileAssetReference(entry, "output", null, "path");
      return;
    }
    // `Copy reference` and `Copy relative path` put the same string on the
    // clipboard here, and that is correct rather than a duplicate: a whole
    // file's CAD reference IS its served-root-relative path (the selector half
    // is what a picked face adds). The desktop's two differ only in that its
    // reference also drops a chip in the composer, and a browser tab has no
    // composer to drop one in.
    if (action === "copy-relative-path" || action === "copy-reference") {
      void onCopyFileAssetReference(entry, "output", null, "relativePath");
    }
  }, [entryForPath, onCopyFileAssetReference, onOpenPath]);

  const platform = useMemo(() => currentPlatform(), []);

  return { onAction, platform };
}
