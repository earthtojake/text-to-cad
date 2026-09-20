import { normalizeViewSettings, resetViewSettings, VIEW_GROUP_KEYS } from "@hardcore/core/common/viewSettings.js";
import { resolveViewSceneSettings } from "@hardcore/core/common/sceneSettings.js";
import { mergeViewerDisplaySettings, viewerDisplaySettingsForMode } from "./viewerDisplaySettings.js";
import { shareSettingsValue } from "./shareSettingsValue.js";

// One per mounted file. UI actions, agent commands and session restoration all
// write here. Resolved defaults are outputs, never written back as new edits.
export function createViewSettingsStore(initial = {}, defaults = {}) {
  let context = defaults;
  let snapshot;
  const listeners = new Set();
  function commit(settings) {
    const display = normalizeViewSettings(settings);
    const next = shareSettingsValue(snapshot, {
      display,
      scene: resolveViewSceneSettings({ ...context, display })
    });
    if (next === snapshot) return snapshot;
    snapshot = next;
    for (const listener of listeners) listener();
    return snapshot;
  }
  commit(initial);
  return {
    getSnapshot: () => snapshot,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    // Partial: the appearance and the file's capabilities are configured by different owners.
    configure(defaults) { context = { ...context, ...defaults }; return commit(snapshot.display); },
    restore: commit,
    patch: patch => commit(mergeViewerDisplaySettings(snapshot.display, patch)),
    selectPreset: mode => commit(viewerDisplaySettingsForMode(snapshot.display, mode)),
    reset: () => commit(resetViewSettings(snapshot.display)),
    resetModelTools: () => commit({ ...snapshot.display, clip: { enabled: false }, exploded: { enabled: false } }),
    setEnabled(group, enabled) {
      if (!["clip", "exploded", ...VIEW_GROUP_KEYS].includes(group)) throw new Error(`Unknown view group: ${group}`);
      if (snapshot.scene.view[group].enabled === enabled) return snapshot;
      // A gate replaces its group rather than merging edits. Reopening any
      // feature (including Clip) starts from defaults, never its old values.
      return commit({ ...snapshot.display, [group]: { enabled } });
    }
  };
}
