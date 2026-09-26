import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { failureAlert } from "../kit/status/loadAlerts.js";

const emptyCommands = Object.freeze({});
const emptySubscribe = () => () => {};
const getEmptyCommands = () => emptyCommands;
const fileKey = entry => String(entry?.file || "").trim();

/**
 * The half of a shell renderer's surface that is about its workspace, not its
 * scene: the live catalog entry of the prepared file, the host's command and
 * preference stores, the prompt resource, and the `services` object
 * `useRendererShell` takes. A renderer loads its scene from `entry` and hands
 * the rest on.
 *
 * @param {{ view: import("../../file-viewer/types.js").RendererViewProps,
 *   data: import("./prepare.js").PreparedWorkspaceEntry & { services: object } }} options
 */
export function useWorkspaceDocument({ view, data }) {
  const { client, entry, services } = data;
  const commands = useSyncExternalStore(services.commands?.subscribe || emptySubscribe,
    services.commands?.getSnapshot || getEmptyCommands, getEmptyCommands);
  const preferences = useSyncExternalStore(services.preferences.subscribe, services.preferences.getSnapshot, services.preferences.getSnapshot);
  // The catalog is live: a rewritten file arrives as the same entry with a new hash.
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const modelKey = fileKey(entry);
  const liveEntry = catalog.entries.find(item => fileKey(item) === modelKey) || entry;
  const resource = useMemo(() => ({
    kind: "workspace-file", workspaceId: view.source.id, path: view.file.path,
    revision: String(liveEntry?.documentHash || liveEntry?.hash || view.file.revision || "")
  }), [view.source.id, view.file.path, view.file.revision, liveEntry?.documentHash, liveEntry?.hash]);
  const shellServices = useMemo(() => ({
    preferences, onPreferenceChange: services.preferences.update, live: services.live,
    captureRequest: commands.captureRequest, acknowledgeCommand: services.commands?.acknowledge
  }), [preferences, services, commands.captureRequest]);
  return { client, entry: liveEntry, modelKey, resource, commands, services: shellServices,
    acknowledgeCommand: services.commands?.acknowledge, catalogError: catalog.error };
}

/**
 * The alert for a document load, as `useRendererShell` takes it in `load.alert`:
 * the catalog could not be read, or the file's loader raised. With a scene
 * already on screen a failed reload can be dismissed, leaving that scene to use.
 *
 * @param {{ catalogError?: unknown, error?: any, modelKey: string, hasScene: boolean }} state
 */
export function workspaceLoadAlert({ catalogError, error, modelKey, hasScene }) {
  if (catalogError && !hasScene) return {
    severity: "error", kind: "status", title: "Couldn’t open the model",
    message: "The viewer couldn’t retrieve this file’s information.",
    recovery: "Try again. If this continues, check that the viewer is running.",
    details: catalogError, reload: true
  };
  if (!error) return null;
  const alert = failureAlert(modelKey, error?.message || error, error?.failure);
  return hasScene ? { ...alert, blocking: false, message: `${alert.message} The existing model remains visible.` } : alert;
}

/**
 * A host asking to select a reference in a file that has none is answered, never
 * dropped: unsupported selection requests are consumed without changing the view.
 *
 * @param {ReturnType<typeof useWorkspaceDocument>} document
 */
export function useDeclinedSelectReference(document) {
  const key = document.commands.selectReference?.key ?? null;
  const declined = useRef(null);
  useEffect(() => {
    if (key === null || declined.current === key) return;
    declined.current = key;
    document.acknowledgeCommand?.("selectReference", key);
  }, [key, document.acknowledgeCommand]);
}
