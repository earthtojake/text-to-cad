# Mesh Preparation and References

Bad mesh handling is a top URDF and MJCF failure mode, and it usually happens *before* any XML is written: source CAD is split into per-link assets incorrectly, exported in the wrong frame, or referenced at the wrong scale. Prepare assets first, then author XML that matches them. A description references geometry and mesh assets; it does not regenerate them.

## Generated Descriptions

A description generated from a CAD model (`cad model export <id> robot.xml` or `robot.urdf`, or `cad.mujoco.spec`) writes its own meshes, and none of the steps below apply:

- one binary STL per part prototype, in **metres** and in the part's own frame, written once however many links place it, named `<model>_<part>.stl`; the description places it in its link with an origin, so no `scale` is needed or written;
- beside the file: in `assets/` for an MJCF (its `meshdir`), in `meshes/` for a URDF, each named by relative path, so the file and its meshes move together as one folder;
- with `cad.mujoco.spec(..., assets="dir")`, written in that folder (relative to the working directory), and without it in the engine's cache; either way the spec names every mesh by absolute path, as it does an MJCF's own. `cad.mujoco.save` copies every mesh a spec names into `assets/` beside the file it writes, so that folder travels ([mujoco-environment.md](mujoco-environment.md#the-mujoco-function));
- meshed at the viewer's tolerance unless the export or `spec` is given `tolerance=` (millimetres);
- each part's own mesh as its collision (which MuJoCo hulls); a MuJoCo function's `decompose()` adds the convex hulls CoACD cuts a part's mesh into, one STL per hull, `<model>_<part>_hull<i>.stl`, beside the part's whole visual.

A vendor arm's folder holds a few hundred files and some MB, and that is expected: most files are hulls (a decomposed part writes one per hull, up to its `max_hulls`, 16 by default; `decompose(s, part, max_hulls=8)` halves them), and its visual geoms come from far fewer part prototypes, each file placed as often as it is used (a board's many identical components, every screw of one size). Merging a link's visuals into one mesh a colour makes fewer geoms but more bytes, since every repeated screw and servo part is copied where it was placed. So every visual stays a part, named for it.

A wrong mesh is fixed in the model and exported again; a mesh file in such a folder is never edited or replaced by hand. The rest of this file is for a description written by hand.

## Splitting Source CAD Into Link Assets

The unit of export is the **link**, not the assembly and not the CAD feature tree:

1. Enumerate the links from the design ledger first. Every link that shows geometry gets exactly one visual asset (or an explicit set of assets); rigidly-joined parts that belong to one link are merged into that link's single export.
2. Never point multiple links at one combined assembly mesh with compensating origins. If two links share a source body, the body must be split at the joint in CAD before export.
3. Export each link's mesh **in that link's own frame** — the frame the ledger defines, coincident with the parent joint frame at zero position. Done right, every `<visual><origin>` is identity (`0 0 0`, `0 0 0`), which is the convention to follow and the easiest state to audit.
4. If an export cannot be re-framed (vendor mesh, scanned part), a nonzero visual origin is acceptable but must be recorded in the ledger with its source; it is a per-link constant, not a tuning knob.
5. Splitting, re-framing, and exporting STEP/STL/3MF/GLB assets belongs to the owning CAD workflow: with a text-to-cad model, each link is a model of its own returning the link's part in the link's frame, and `cad model export <id> link.stl` writes its mesh. Do not attempt to fix a wrong split by editing URDF origins or MJCF body positions.

Checklist after export, before authoring:

- one file per link, named after the link (`3MF/forearm_link.3mf`);
- zero pose in the mesh file corresponds to the link frame;
- units of the export are known and recorded (mm is common for 3MF/STL);
- the export actually contains only that link's geometry (open it, or check bounding boxes with a one-line script).

When a description references exported mesh assets, record in its ledger:

- source geometry file;
- exported mesh path;
- mesh unit convention;
- mesh origin convention;
- visual scale;
- collision simplification decision.

## Units and Scale

- URDF and MJCF lengths are meters. Mesh files are frequently millimeters, and STL carries no unit metadata at all.
- Express the conversion explicitly on every mesh reference: in URDF the `scale` attribute, `scale="0.001 0.001 0.001"` for mm sources; in MJCF the asset's `<mesh file="..." scale="0.001 0.001 0.001"/>`. Omit it only when the mesh is genuinely authored in meters.
- STL and 3MF are read as the numbers they hold (a 3MF's `unit` attribute is not applied), so the scale alone converts them: `cad` writes both in millimeters, which take a scale of `0.001 0.001 0.001`.
- A GLB is meters by the glTF specification (`cad` writes GLB in meters), so a GLB link mesh takes no scale; give one only to resize the asset itself.
- One convention per robot: do not mix mm and m assets in the same file without a ledger entry per exception.
- A robot rendering ~1000× too large or too small in the viewer is a scale bug; fix the scale, not the joint origins.

## Reference Forms

In URDF:

- **Local relative paths** (`3MF/forearm_link.3mf`) resolve from the `.urdf` file's directory. Preferred for a robot kept in a project tree — the bundled validator verifies these files exist.
- **`package://name/path` URIs** are for ROS-package consumers. The validator checks syntax only and warns that resolution is consumer-specific (`--packages NAME=PATH` resolves them for the validator alone); confirm the consuming environment resolves the package root as expected. The CAD Viewer and `cad urdf snapshot` take the nearest folder above the `.urdf` named `name`, or holding a `package.xml` that names it, as the package root, so keep the description inside its package folder.
- Remote URIs are accepted with warnings; avoid them for durable fixtures.

In MJCF, a mesh `file` resolves from the `<compiler meshdir>`, itself relative to the model file: keep the meshes in that folder, beside the model ([mjcf-authoring.md](mjcf-authoring.md)).

Keep mesh files under the same model directory tree as the description, so the file and its assets move together.

What the CAD Viewer and the snapshots draw is narrower than what the validators accept: a local STL, 3MF or GLB file, beside the description or in its package (`package://`, above), and the `box`, `cylinder` and `sphere` primitives, which the server meshes itself. A `.dae`, `.obj` or `.ply` mesh, a remote URI, a package no folder above the description is, or a missing file is refused by name before anything renders — convert the mesh, or keep a rendering copy of the robot whose meshes sit beside it. Each format's full list is in [snapshots.md](snapshots.md).

An MJCF's meshes are MuJoCo's to read: STL, OBJ or MSH files, found under the compiler's `meshdir` (or `assetdir`) beside the main file. A 3MF or GLB is no MuJoCo mesh at all: export the link as STL (`cad model export <id> link.stl`). No `cad` view draws an MJCF; `cad mujoco check` says a mesh file MuJoCo cannot find or read. MuJoCo hulls every mesh it collides, so an MJCF's collision mesh is its convex hull whatever its shape ([mjcf-authoring.md](mjcf-authoring.md#visual-and-collision-geoms)).

## Visual vs Collision Assets

- Visual meshes are for display: full detail, colors preserved where the format supports it.
- Collision geometry is for physics/planning: prefer primitives (`box`, `cylinder`, `sphere`) sized from the part's bounding volume, or a coarse closed mesh. Using the visual mesh for collision is a temporary fallback, not a default — concave visual meshes make physics engines slow and unstable. Select collision geometry for stable and fast physics, not visual fidelity.
- Collision origins are expressed in the link frame, independent of the visual origin.

## When Meshes Change

Mesh assets are owned by the CAD workflow. If the CAD source changed shape, re-export the affected link assets with the owning workflow first, then re-check the description: link frames, visual origins, collision approximations, and inertials may all be stale. Regenerate geometry and mesh artifacts before regenerating a description that references them. Re-run the validator and the viewer sweep afterwards.
