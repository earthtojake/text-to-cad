# Mesh Preparation and References

Read this for the mesh files a description names: what a generated description writes, and for a hand-written one how source CAD becomes one mesh per link, its units and scale, and how each consumer finds and reads the file. Mesh mistakes are made before any XML is written: a split that follows the CAD and not the links, an export in the wrong frame, a reference at the wrong scale.

## Generated Descriptions

A description generated from a CAD model (`cad model export <id> robot.xml` or `robot.urdf`, or `cad.mujoco.spec`) writes its own meshes, and none of the steps below apply:

- one binary STL per part prototype, in metres and in the part's own frame, written once however many links place it, named `<model>_<part>.stl`; the description places it in its link with an origin, so no `scale` is written;
- beside the file, each named by relative path, so the file and its meshes move as one folder: in `assets/` for an MJCF (its `meshdir`), in `meshes/` for a URDF;
- from `cad.mujoco.spec`, in the engine's cache, or with `assets="dir"` in that folder (relative to the working directory), named by absolute path either way; `cad.mujoco.save` copies every mesh a spec names into `assets/` beside the file it writes ([mujoco-environment.md](mujoco-environment.md#the-mujoco-function));
- meshed at the viewer's tolerance: an export of a description refuses `--tolerance`, and `spec(..., tolerance=)` (millimetres) is what meshes finer;
- each part's own mesh as its collision (which MuJoCo hulls); a MuJoCo function's `decompose()` adds the convex hulls CoACD cuts a part's mesh into, one STL per hull, `<model>_<part>_hull<i>.stl`, beside the part's whole visual.

A vendor arm's folder holds a few hundred files and some MB, and that is expected: most are hulls (a decomposed part writes one per hull, up to its `max_hulls`, 16 by default; `decompose(s, part, max_hulls=8)` halves them), and the visuals come from far fewer part prototypes, each file placed as often as it is used. Do not merge a link's visuals into one mesh: fewer geoms, but more bytes, since every repeated screw and servo part is copied where it was placed.

Fix a wrong mesh in the model and export again; never edit or replace a file in such a folder. The rest of this file is for a description written by hand.

## Splitting Source CAD Into Link Assets

The unit of export is the link, not the assembly and not the CAD feature tree:

1. Every link that shows geometry gets one visual asset, or an explicit set; rigidly joined parts of one link are merged into it.
2. Never point several links at one combined mesh with compensating origins. A body two links share is split at the joint, in CAD.
3. Export each link's mesh in the link's own frame, the one coincident with its parent joint's frame at zero. Every `<visual><origin>` is then identity, the easiest state to audit.
4. A mesh that cannot be re-framed (a vendor's, a scan) takes a nonzero visual origin, recorded in the ledger with its source: a per-link constant, not a tuning knob.
5. With a text-to-cad model, each link is a model of its own returning the link's part in the link's frame, and `cad model export <id> link.stl` writes its mesh.

Before writing the XML, confirm each file holds only its link's geometry (open it, or check its bounding box), and give each mesh its ledger line: source, units, scale, and how its collision was simplified ([urdf-authoring.md](urdf-authoring.md#the-ledger)). When the CAD changes shape, export the affected links again first, then re-check what was derived from the old shape: link frames, visual origins, collision approximations and inertials.

## Units and Scale

- URDF and MJCF lengths are metres. STL and 3MF are read as the numbers they hold (an STL carries no unit, and a 3MF's `unit` attribute is not applied), so the scale alone converts them: `scale="0.001 0.001 0.001"` on a URDF's `<mesh>` or an MJCF's `<mesh file="..."/>` asset for the millimetres `cad` writes both in. Omit it only for a mesh authored in metres.
- A GLB is metres by the glTF specification, as `cad` writes it, and takes no scale.
- One convention per robot, with a ledger line for each exception.

## Reference Forms

In a URDF:

- **A relative path** (`3MF/forearm_link.3mf`) resolves from the `.urdf` file's folder, and `cad urdf validate` checks that the file is there. Prefer it for a robot kept in a project tree.
- **A `package://name/path` URI** is for ROS consumers. The validator checks its syntax and warns that it was not resolved; `--packages NAME=PATH` resolves it for the validator alone. The viewer and `cad urdf snapshot` take the nearest folder above the `.urdf` named `name`, or holding a `package.xml` that names it, as the package root, so keep the description inside its package folder.
- **A remote URI** passes with a warning and is drawn by nothing here.

In an MJCF, a mesh `file` resolves from `<compiler meshdir>`, itself relative to the main file, and is an STL, an OBJ or an MSH. A 3MF or a GLB is no MuJoCo mesh: export the link as STL. `cad mujoco check` says, in MuJoCo's words, a mesh file it cannot find or read.

Keep meshes under the description's own folder tree, so the file and its assets move together. The viewer and the snapshots draw fewer formats than the validators accept ([snapshots.md](snapshots.md#urdf-and-srdf)).

## Visual vs Collision Assets

A visual mesh is for display: full detail, colours where the format carries them. Collision geometry is chosen for stable, fast contact, not fidelity: primitives sized from the part, or a coarse closed mesh. A concave visual mesh used as the collision is slow in most engines, and in MuJoCo collides as its convex hull whatever its shape ([mjcf-authoring.md](mjcf-authoring.md#visual-and-collision-geoms)).
