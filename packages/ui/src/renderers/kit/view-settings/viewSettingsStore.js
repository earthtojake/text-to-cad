import { normalizePreviewSettings, normalizeViewSettings } from "@text-to-cad/core/common/viewSettings.js";
import { resolveViewSceneSettings } from "@text-to-cad/core/common/sceneSettings.js";
import { mergePreviewSettings, mergeViewerDisplaySettings } from "./viewerDisplaySettings.js";
import { shareSettingsValue } from "./shareSettingsValue.js";

// One per mounted file. UI actions, agent commands and session restoration all
// write here. Resolved defaults are outputs, never written back as new edits.
// The display is a mode and the Grid switch (and what modes share: the model tools, the camera's
// lens); a mode has no settings of its own. Preview's settings are kept beside it (`preview`):
// Preview is no mode, but its own view (`renderScene()`), drawn in Render over the same display.
export function createViewSettingsStore(initial = {}, defaults = {}, initialPreview = {}) {
  let context = defaults;
  let snapshot;
  const listeners = new Set();
  function commit(settings, look = snapshot?.preview ?? {}) {
    const display = normalizeViewSettings(settings);
    const preview = normalizePreviewSettings(look);
    const next = shareSettingsValue(snapshot, {
      display,
      preview,
      scene: resolveViewSceneSettings({ ...context, display })
    });
    if (next === snapshot) return snapshot;
    snapshot = next;
    for (const listener of listeners) listener();
    return snapshot;
  }
  commit(initial, initialPreview);
  return {
    getSnapshot: () => snapshot,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    // Partial: the appearance and the file's capabilities are configured by different owners.
    configure(defaults) { context = { ...context, ...defaults }; return commit(snapshot.display); },
    /** The display as stored, and Preview's settings when they are given too. */
    restore: (display, preview) => commit(display, preview ?? snapshot.preview),
    /** Merges a patch in the display's own shape: the mode, the grid, what modes share. */
    patch: patch => commit(mergeViewerDisplaySettings(snapshot.display, patch)),
    selectMode: mode => commit(mergeViewerDisplaySettings(snapshot.display, { mode })),
    setGrid: grid => commit(mergeViewerDisplaySettings(snapshot.display, { grid })),
    /** Merges a patch into Preview's settings, group by group. */
    patchPreview: patch => commit(snapshot.display, mergePreviewSettings(snapshot.preview, patch)),
    resetPreview: () => commit(snapshot.display, {}),
    /** Render over the file's display as it stands, in Preview's settings (Preview's scene): nothing is committed. */
    renderScene: () => resolveViewSceneSettings({ ...context, display: snapshot.display, preview: true, previewSettings: snapshot.preview })
  };
}
