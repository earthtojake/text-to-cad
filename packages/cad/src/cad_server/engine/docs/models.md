# Models

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A model is a parameterless function that returns a build123d shape, declared
with `@model` (a document with no file) or one or more file decorators (a document with those
files) -- never both: `@model` stacked with a file decorator is refused. The engine runs it in a warm
worker, holds the result as an XCAF document in memory (`@xbf` explicitly writes its BinXCAF file),
and writes the derived files the model declares, each a translation of that document. A drawing is
a model like any other: its body returns 2D geometry (a sketch, a face, wires or edges), and `@dxf`
declares its DXF.

```python
from cad import step, xbf
import build123d as bd

@xbf("XBF/arm.xbf")                      # XBF/arm.xbf beside the script; @xbf(out="path.xbf") to choose
@step("arm.step")         # also @glb, @stl, @threemf, @dxf; stacked or alone; out= is required; name= optionally names the model
def arm():
    return bd.Box(10, 20, 30)


if __name__ == "__main__":
    arm()
```

A call returns the document's handle, never a bare shape: `arm()` builds it through the engine and
returns a `Document` (`api.Document`) -- `.id`, `.url` (its page), `.name`, `.shape` (the built
result, transferred into the caller and the kernel loaded on first access, never before),
`.export(*paths)` and `.snapshot(out, **picture_options)`, which are `export(handle, ...)` and
`snapshot(handle, ...)`; an export the program's own code makes says each file it wrote, a line each,
as `cad <type> export` does. The decorated function stays the function and its id (`arm.id`);
`arm.build(verify=, profile=)` is the debug seam, a `Report`. Inside another model's body a call
builds the child document as before and returns its handle too, whose `.shape` is the result in
that process: a body composes `peg().shape`, and a child called for its files alone stays a bare
`peg()`. Read on either side, `.shape` is one tree: every sub-assembly at the placement its parent
gives it and every part at its own in its assembly, as the body built them -- transferred, each
node's placement in its parent (`export.Source.locals`), never pushed down into the leaves.

```python
@model
def peg():
    return bd.Cylinder(2, 10)

@xbf("XBF/base.xbf")
def base():
    return bd.Compound(children=[bd.Box(20, 20, 3), peg().shape.moved(bd.Pos(5, 0, 6))])

if __name__ == "__main__":
    handle = base()               # built; the id and the page are printed
    handle.export("base.step")    # export(handle, "base.step")
    handle.shape.volume           # the shape, transferred now
```

A program that holds a shape -- a script with no model, a REPL, a notebook -- hands it over with
`model(shape, name="plate")` (**Shapes handed over**): a document made of it, held and served by
the engine, exportable, and returned as a handle whose `.shape` is the shape passed.

`import build123d as bd` binds at once: the library makes the import of `build123d` and `OCP` lazy
(its `cad-lazy-kernel.pth`, run at interpreter start in the environment the library is
installed in, and `import cad` in a checkout), so the kernel loads on the first attribute anything
reads from it -- in the worker, for a build the daemon runs, and never in a run of the script
the engine finds current. `from build123d import Box` reads the name, and loads the kernel at
that line.

A function worth skipping on a later build is marked `@memo` (**Memo functions**): an
assembly's parts, a stage of a long derivation. It writes no file; the model that calls
it does.

```python
from cad import xbf
from cad.build123d import memo

@memo
def wheel(radius, spokes=5):     # replayed, not run, while what it is made of is unchanged
    ...

@xbf("XBF/bike.xbf")
def bike():
    return bd.Compound(children=[wheel(300), wheel(300).moved(bd.Pos(1200, 0, 0))], label="bike")
```

A part's material is native: `part.material = bd_materials.metals.aluminum()`.
`paint(part, faces, material)` gives faces one. Set an assembly's material before reading
its children's inherited properties. Set an explicit `part.color` after `.material`, since
build123d's material setter sets colour. Set materials on finished parts, after the
last operation: an edit of one is then no kernel call. Two limits of OCCT's STEP writer show in a STEP export: it names the density
unit gram³·cm² (the exponents wrong, the number right: the reader gives the density back as
written), and it writes materials sharing a name as one entity, so a STEP gives every such
material the first one's description.

An assembly's mechanism is build123d's joints: `RevoluteJoint`,
`LinearJoint`, `CylindricalJoint`, `BallJoint` and `RigidJoint` on its parts, placed with
`connect_to(..., angle=, position=, angles=)`. The values they are connected at are the
as-built state, the pose every file of the model shows. The functions that say more are named
after the AP242 entities they write, and are the build123d integration's, `cad.build123d` (the root holds none of them):
`mechanism_state(assembly, name, **values)` names another
state (`mechanism_state_representation`), by joint label, and never moves the build;
`gear_pair`, `rack_and_pinion_pair` and `screw_pair(assembly, name, **joints)` constrain joints to
move together by ratio (**Kinematics**); `configuration_sequence(assembly, name, ...)` names a
sequence of states over time (`interpolated_configuration_sequence`, **Configuration
sequences**), and `cad.build123d`'s `animation(assembly, name, duration=)` a GLB's own animation
(**Animations**). Connect parts before putting them in the compound that holds
them; where `connect_to` cannot place them (a nested assembly), give the two joints one label
where the parts stand.

```python
from cad.build123d import mechanism_state
from cad import xbf

@xbf("XBF/hinge.xbf")
def hinge():
    base, arm = bd.Box(100, 60, 20), bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("mount", arm)
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=30)   # as built: elbow 30
    return mechanism_state(bd.Compound(children=[base, arm], label="hinge"), "raised", elbow=90)
```

A posed or partial file is a function: `export` writes the document
as its code built it. `posed(assembly, state)` (`cad.build123d`, beside `mechanism_state`) is a
copy of the assembly, sharing its geometry, with every part where a mechanism state, or
`{joint label or coupling name: value}`, puts it -- each link moved by its placement at those
values over its placement as built, the forward kinematics the viewer and the snapshot pose
by (`mechanism.link_worlds`). The copy keeps the joints, couplings, states and sequences, the
asked values its as-built state, so its viewer Position and motions still work; an unknown
state, joint or coupling, or a value out of range, is refused by name as `--pose` refuses it.
A folded arm's STEP is a model: `@step(out="arm_folded.step") def arm_folded(): return
posed(arm(), "folded")`. `posed` takes the handle a model call returns, as every verb does: in a
body it poses the child's shape; in a plain script, where `.shape` brings the parts out of the
engine without their joints, it poses the document the engine holds (`posed_structure`) and
answers the tree `.shape` would, at that pose. Given such a `.shape`, it says to pass the handle.
