import { useEffect, useMemo, useRef, useState } from "react";
import { entryHasMesh, entryMeshAssetSignature } from "@text-to-cad/core/lib/entryAssets.js";
import { editingBuildActive, previewAnnotationsFor } from "../../../workbench/editingPreview.js";
import { createPreviewPartsGate, previewRevisionEntry } from "../../../workbench/previewRevision.js";
import { loadPackageDescriptor } from "./packageDescriptorCache.js";
import { meshStateIsComplete } from "./packageProgressiveLoad.js";

const NONE = Object.freeze({ entry: null, gate: null, saved: "" });

/**
 * The build feed's preview revision for `file` as the surface draws it (`previewRevisionEntry`):
 * from the moment the feed names it, once its view is read, until the catalog names the file the
 * build saved -- or until the feed drops it: a superseded build, a newer one, a daemon that no
 * longer lists it. A build first seen already done is the file on disk, never its preview.
 *
 * `editing` is the feed's state (`useEditingPreview`); `inHand` the catalog's entry for the file,
 * whose articulation, routines and finishes stay in hand while the build may still resolve its
 * own; `meshState` what is on screen, which says when the preview's geometry is whole and its own
 * finishes may bind. Out: `entry`, the preview to draw in the catalog entry's place, or null;
 * `gate`, the parts its load waits on (`useCadAssets`); and `saved`, the catalog hash that replaced
 * the last preview as its own save -- a swap that clears nothing, since the tokens are the same --
 * against "" for any other change of tree.
 */
export function usePreviewRevision(editing, { client, file, inHand, meshState }) {
  const preview = editing.preview;
  const build = editing.epoch && editing.revision ? `${editing.epoch}:${editing.revision}` : "";
  const key = build && preview ? `${build}:${preview.tree}` : "";
  const object = preview?.annotations || "";
  const catalogHash = entryHasMesh(inHand) ? String(inHand.hash || "") : "";

  // Each build, as first seen: whether its preview may be shown (the save was not on disk yet) and
  // the catalog's revision then, which the save moves.
  const adoptedRef = useRef({ build: "", shown: false, catalogHash: "" });
  if (build && adoptedRef.current.build !== build) {
    adoptedRef.current = { build, shown: editing.state !== "done", catalogHash };
  }
  const adopted = adoptedRef.current.build === build && adoptedRef.current.shown;
  // The save landed: the catalog named a revision past the one the build began over. Its hash is
  // the preview's save unless the file moved past the build.
  const retiredRef = useRef({ build: "", saved: "" });
  if (adopted && catalogHash && catalogHash !== adoptedRef.current.catalogHash && retiredRef.current.build !== build) {
    retiredRef.current = { build, saved: editing.superseded ? "" : catalogHash };
  }
  const retired = Boolean(build) && retiredRef.current.build === build;
  const active = adopted && !retired && Boolean(key);

  // The preview's view, read once per revision as any tree's is; null while it is read, and for a
  // tree the store no longer holds.
  const url = active ? client.storeTreeUrl(preview.tree, { producer: preview.producer }) : "";
  const [view, setView] = useState({ key: "", descriptor: null });
  useEffect(() => {
    if (!active) return undefined;
    const controller = new AbortController();
    loadPackageDescriptor(url, { resources: client.resources, signal: controller.signal })
      .then(descriptor => { if (!controller.signal.aborted) setView({ key, descriptor: descriptor?.kind === "assembly-package" ? descriptor : null }); })
      .catch(() => { if (!controller.signal.aborted) setView({ key, descriptor: null }); });
    return () => controller.abort();
  }, [active, key, url, client]);

  // Its annotations, read once named, and bound only when resolved against the preview's tree.
  const [annotations, setAnnotations] = useState({ key: "", object: "", value: null });
  useEffect(() => {
    if (!active || !object) return undefined;
    const controller = new AbortController();
    client.previewAnnotations(object, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setAnnotations({ key, object, value }); })
      .catch(() => { if (!controller.signal.aborted) setAnnotations({ key, object, value: null }); });
    return () => controller.abort();
  }, [active, key, object, client]);
  const bound = annotations.key === key && annotations.object === object ? previewAnnotationsFor(preview, annotations.value) : null;
  // The build may still resolve its declarations: while it runs, and while a named object is read.
  const pending = !bound && (editingBuildActive(editing) || Boolean(object));

  // The parts its build has named so far, one gate per revision (none for a build that could not
  // name them: the view keys them as for a saved file, and the load reads them so).
  const gateRef = useRef(null);
  if (!active || !preview.producer) gateRef.current = null;
  else if (gateRef.current?.key !== key) gateRef.current = { key, gate: createPreviewPartsGate(preview.tree) };
  const gate = gateRef.current?.gate || null;
  useEffect(() => { gate?.update(preview?.parts, preview?.complete); }, [gate, preview]);

  const descriptor = view.key === key ? view.descriptor : null;
  const undressed = useMemo(() => (active && descriptor
    ? previewRevisionEntry({ file, preview, view: descriptor, url, annotations: bound, inHand, pending, dressed: false })
    : null), [active, descriptor, file, preview, url, bound, inHand, pending]);
  // The preview's own finishes bind once its geometry is on screen whole, and stay bound: a change
  // of finishes reloads the composition, which must not be a load cancelled part way.
  const dressedRef = useRef("");
  const dressing = `${key}:${object}`;
  if (bound && undressed && dressedRef.current !== dressing && meshState?.file === file
    && meshState.meshHash === entryMeshAssetSignature(undressed) && meshStateIsComplete(meshState)) {
    dressedRef.current = dressing;
  }
  const dressed = dressedRef.current === dressing;
  const entry = useMemo(() => (dressed && undressed
    ? previewRevisionEntry({ file, preview, view: descriptor, url, annotations: bound, inHand, pending, dressed: true })
    : undressed), [dressed, undressed, descriptor, file, preview, url, bound, inHand, pending]);

  return useMemo(() => (entry ? { entry, gate, saved: "" } : { ...NONE, saved: retired ? retiredRef.current.saved : "" }),
    [entry, gate, retired]);
}
