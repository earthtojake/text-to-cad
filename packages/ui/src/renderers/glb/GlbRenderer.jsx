import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { Axis3d } from "lucide-react";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { failureAlert } from "../kit/status/loadAlerts.js";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";

const emptyCommands = Object.freeze({});
const emptySubscribe = () => () => {};
const getEmptyCommands = () => emptyCommands;
const LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });
const fileKey = entry => String(entry?.file || "").trim();

function GlbSurface({ view, data }) {
  const { client, entry, services } = data;
  const commands = useSyncExternalStore(services.commands?.subscribe || emptySubscribe,
    services.commands?.getSnapshot || getEmptyCommands, getEmptyCommands);
  const preferences = useSyncExternalStore(services.preferences.subscribe, services.preferences.getSnapshot, services.preferences.getSnapshot);
  // The catalog is live: a rewritten file arrives as the same entry with a new hash.
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const modelKey = fileKey(entry);
  const liveEntry = catalog.entries.find(item => fileKey(item) === modelKey) || entry;
  const loaded = useGlbScene({ entry: liveEntry, resources: client.resources });
  const scene = loaded.scene;

  const resource = useMemo(() => ({
    kind: "workspace-file", workspaceId: view.source.id, path: view.file.path,
    revision: String(liveEntry?.documentHash || liveEntry?.hash || view.file.revision || "")
  }), [view.source.id, view.file.path, view.file.revision, liveEntry?.documentHash, liveEntry?.hash]);
  const loadAlert = useMemo(() => {
    if (catalog.error && !scene) return {
      severity: "error", kind: "status", title: "Couldn’t open the model",
      message: "The viewer couldn’t retrieve this file’s information.",
      tooltip: "The viewer couldn’t retrieve information about this file. Try reloading the viewer.",
      recovery: "Try again. If this continues, check that the viewer is running.",
      details: catalog.error, reload: true
    };
    if (!loaded.error) return null;
    const alert = failureAlert(modelKey, loaded.error?.message || loaded.error, loaded.error?.failure);
    return scene ? { ...alert, blocking: false, message: `${alert.message} The existing model remains visible.` } : alert;
  }, [catalog.error, loaded.error, modelKey, scene]);

  const services_ = useMemo(() => ({
    preferences, onPreferenceChange: services.preferences.update, live: services.live,
    captureRequest: commands.captureRequest, acknowledgeCommand: services.commands?.acknowledge
  }), [preferences, services, commands.captureRequest]);
  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.());
  const shell = useRendererShell({
    view, services: services_, resource, modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, toolModes: GLB_TOOL_MODES, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation, live: LIVE
  });
  requestRenderRef.current = shell.requestRender;

  // A host asking to select a reference here is answered, never dropped: the request
  // is consumed and the person is told why nothing was selected.
  const selectKey = commands.selectReference?.key ?? null;
  const declinedSelectKey = useRef(null);
  useEffect(() => {
    if (selectKey === null || declinedSelectKey.current === selectKey) return;
    declinedSelectKey.current = selectKey;
    services.commands?.acknowledge?.("selectReference", selectKey);
    shell.setCopyStatus(GLB_DECLINED_LIVE_COMMANDS.select);
  }, [selectKey, services.commands, shell.setCopyStatus]);

  // Orbit does nothing but leave the camera to the pointer, which every tool allows.
  const tools = [
    shell.tools.own({ id: GLB_TOOL.ORBIT, label: "Orbit", icon: <Axis3d className="size-3" strokeWidth={2} aria-hidden="true" /> }),
    shell.tools.draw,
    shell.tools.animate
  ].filter(Boolean);
  return <RendererShell shell={shell} tools={tools} inspector={{ title: "GLB", tabs: [shell.displayTab] }} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
