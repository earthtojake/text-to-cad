# Tube skins

A flexible swept body — a tendon, a hose, a valve spring — bent along a track. The
source works out where it is; this package only plays it, as a glTF player plays a skin. Nothing here compiles a path, projects a vertex or
refines a mesh.

## What cadgen handed over

A **skins payload** is a tube track's keys turned into centerlines, which a host names
for `loadSourceAnimation` (`tubeSkinsUrl`). No host writes one in cadgen 0.8: the CAD
Viewer opens every document through the cadgen engine, whose documents carry motions,
never clips, and no engine document carries a tube track. The player below stays with the effects pass that
carries it; the committed fixture (`src/common/fixtures/tube_skins`) is the one
payload its tests read. The payload is GLB-framed; its JSON says what each array is:

- a **binding** per occurrence a track bends: its component's mesh refined into
  bands along the rest centerline and bound to the track's joints, in the
  component's own frame (positions, normals, indices, the component triangle
  each refined triangle came from), each vertex's **joint coordinate** — the
  joint below it plus its weight toward the next — its braid material
  coordinates, and the component's edge polylines split and bound the same way;
  the rest joints, as origins and unit quaternions in the document's space.
- per tube track, every **key's joints**, one row per time of the sidecar track.

## Playing it (`common/tubeSkin.js`)

`loadSourceAnimation` (`common/animationRuntime.js`) reads the payload once, with
the clips, and attaches each track's skin, so evaluation stays synchronous. A
frame's tube pose is a key bracket and a fraction: the joints of the two keys
blend as glTF's LINEAR sampler blends them — origins lerped, rotations slerped
the short way with three's `slerpFlat` — and each vertex blends its two joints.

Joint j moves a component-local point by `base⁻¹ · joint_j · rest_j⁻¹ · base`,
`base` being the record's placement, so a record's effect and exploded matrices
compose over the bend exactly as over a rigid part. `applyRecordTubeSkin`:

- swaps the record's component geometry for the binding's (once per record; the
  component's stays in `tubeSkinState.original` for ownership), carries the
  component's face ids through the refined triangles, and keeps the skin's
  geometry at rest when the tube straightens: every publish resets the pose
  before the clip bends it again;
- moves the record's edges out of the component's instanced draw into private
  lines drawn from the binding's segments (`record.bindTubeEdges`), posed on the
  CPU — there is no way back, for the same reason;
- on the GPU (`record.gpuTubeSkinAllowed`), draws from rest attributes and a joint
  texture (three texels a joint, the rows of its 3x4) through the material's
  `skin` stage (`common/tubeMaterialShader.js`, also patched into the shadow
  depth materials), and poses the CPU copy only when a pick reaches the tube's
  box; without it, poses the copy every frame;
- bounds the pose by its joints' origins grown by the tube's reach from its
  joints: no point is further than that from a joint it rides, and a joint moves
  rigidly, so the box holds every pose.

A braid is a fragment finish (`common/tubeBraidMaterial.js`) over the binding's
material coordinates, which ride with each vertex however the tube bends.

## Exported files

An animated GLB cadgen exported carried the same skin: joints as nodes keyed LINEAR,
the bound mesh with `JOINTS_0`/`WEIGHTS_0`, so any glTF player draws what the viewer
drew.
