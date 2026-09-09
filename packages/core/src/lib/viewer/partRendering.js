import { meshDataRequiresPartRendering } from "../../common/cadScene.js";
import { VIEWER_PICK_MODE } from "./constants.js";

/** Whether to draw a model as separate per-part meshes, AND which parts to draw.
 *
 * One function for both answers on purpose. These used to be two expressions listing the same
 * reasons, and a reason present in one and missing from the other is not a small bug: the
 * caller passes `parts: []`, which cadScene reads as "draw the merged mesh", so the model
 * renders through a path nobody asked for. That is how a single-part STEP came to render with
 * no CAD edges at all -- its edge attributes live on each part's `sourceMesh`, the merged mesh
 * has none, and assemblies were unaffected only because they qualified for per-part rendering
 * on other grounds.
 *
 * The reasons, all of them:
 *
 * * the caller asked for it (a URDF, a parameter module, an exploded view);
 * * the theme rotates fill colours, which are per part;
 * * the parts carry their own source colours or opacities;
 * * the mesh data can ONLY be drawn per part -- a composed component-GLB package, whose
 *   top-level arrays are per COMPONENT in local frames (see meshDataRequiresPartRendering);
 * * something is pickable, which needs a mesh per pickable part. This is the one reason that
 *   narrows the LIST rather than taking all parts: only the pickable ones need their own mesh.
 */
export function resolveScenePartRendering({
  meshData = null,
  renderPartsIndividually = false,
  fillRotationParts = false,
  sourceColorParts = false,
  pickableParts = null,
  pickMode = VIEWER_PICK_MODE.AUTO,
} = {}) {
  const allParts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  const pickable = Array.isArray(pickableParts) ? pickableParts : [];
  const needsEveryPart = Boolean(
    renderPartsIndividually ||
    fillRotationParts ||
    sourceColorParts ||
    meshDataRequiresPartRendering(meshData)
  );
  const picksParts = pickable.length > 0 && (
    pickMode === VIEWER_PICK_MODE.PARTS ||
    pickMode === VIEWER_PICK_MODE.ASSEMBLY ||
    pickMode === VIEWER_PICK_MODE.AUTO
  );
  const parts = needsEveryPart ? allParts : (picksParts ? pickable : []);
  return {
    // Never true with an empty list: "render parts" and "here are none" is the contradiction
    // this function exists to prevent.
    renderParts: parts.length > 0,
    parts,
  };
}
