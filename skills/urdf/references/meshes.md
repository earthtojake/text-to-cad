# URDF Mesh Preparation and References

Bad mesh handling is a top URDF failure mode, and it usually happens *before* any XML is written: source CAD is split into per-link assets incorrectly, exported in the wrong frame, or referenced at the wrong scale. Prepare assets first, then author XML that matches them.

## Splitting Source CAD Into Link Assets

The unit of export is the **link**, not the assembly and not the CAD feature tree:

1. Enumerate the links from the design ledger first. Every link that shows geometry gets exactly one visual asset (or an explicit set of assets); rigidly-joined parts that belong to one link are merged into that link's single export.
2. Never point multiple links at one combined assembly mesh with compensating origins. If two links share a source body, the body must be split at the joint in CAD before export.
3. Export each link's mesh **in that link's own frame** — the frame the ledger defines, coincident with the parent joint frame at zero position. Done right, every `<visual><origin>` is identity (`0 0 0`, `0 0 0`), which is the convention repository fixtures use and the easiest state to audit.
4. If an export cannot be re-framed (vendor mesh, scanned part), a nonzero visual origin is acceptable but must be recorded in the ledger with its source; it is a per-link constant, not a tuning knob.
5. Splitting, re-framing, and exporting STEP/STL/3MF/GLB assets belongs to the owning CAD workflow (`$cad`, `$step-parts` when installed). Do not attempt to fix a wrong split by editing URDF origins.

Checklist after export, before authoring:

- one file per link, named after the link (`3MF/forearm_link.3mf`);
- zero pose in the mesh file corresponds to the link frame;
- units of the export are known and recorded (mm is common for 3MF/STL);
- the export actually contains only that link's geometry (open it, or check bounding boxes with a one-line script).

## Units and Scale

- URDF lengths are meters. Mesh files are frequently millimeters, and STL carries no unit metadata at all.
- Express the conversion explicitly with `scale` on every mesh reference: `scale="0.001 0.001 0.001"` for mm sources. Omit `scale` only when the mesh is genuinely authored in meters.
- One convention per robot: do not mix mm and m assets in the same file without a ledger entry per exception.
- A robot rendering ~1000× too large or too small in the viewer is a scale-attribute bug; fix the scale, not the joint origins.

## Reference Forms

- **Local relative paths** (`3MF/forearm_link.3mf`) resolve from the `.urdf` file's directory. Preferred for repository fixtures — the bundled validator verifies these files exist.
- **`package://name/path` URIs** are for ROS-package consumers. The validator checks syntax only and warns that resolution is consumer-specific; confirm the consuming environment resolves the package root as expected.
- Remote URIs are accepted with warnings; avoid them for durable fixtures.

Keep mesh files under the same model directory tree as the URDF (repository policy: everything under `models/`), so the file and its assets move together.

## Visual vs Collision Assets

- Visual meshes are for display: full detail, colors preserved where the format supports it.
- Collision geometry is for physics/planning: prefer primitives (`box`, `cylinder`, `sphere`) sized from the part's bounding volume, or a coarse closed mesh. Using the visual mesh for collision is a temporary fallback, not a default — concave visual meshes make physics engines slow and unstable.
- Collision origins are expressed in the link frame, independent of the visual origin.

## When Meshes Change

Mesh assets are owned by the CAD workflow. If the CAD source changed shape, re-export the affected link assets with the owning workflow first, then re-check the URDF: link frames, visual origins, collision approximations, and inertials may all be stale. Re-run the validator and the viewer sweep afterwards.
