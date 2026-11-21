# Placements

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A part used ten times is one prototype placed ten times, in the worker's memory as in the
document, as FreeCAD's `App::Link` places one. build123d places a shape by deep-copying it
-- `moved`, `located`, `copy.copy`, and the transforms, which deep-copy before they replace
the copy's geometry -- and its deep copy runs `BRepBuilderAPI_Copy` on every node, so each
placement of a vendor assembly was a whole new B-rep. Under the memo a deep copy makes new
objects of the same classes, each with its own label, colour, material, paints, joints and
children, and each a new handle on the SAME `TShape` (`kernel/memo.py`, `_sharing`); so
does `copy.deepcopy(shape)` in a model. A model that wants a B-rep of its own copies it
with `BRepBuilderAPI_Copy`.

A shape can hold one sub-shape's TShape at two places: OCCT makes a prism's two caps of one
face's edges and vertices placed twice (each lateral edge ends on one vertex TShape at both its
ends), and a piece fused beside a moved piece of the same shape keeps the edges both had. OCCT's
unify (`ShapeUpgrade_UnifySameDomain`, which build123d runs on every boolean's result and in
`clean`) chains the edges it merges by their vertices' TShapes, whatever their places: on such a
shape it can chain an edge at one place with one at the other and fail ("Courbes non jointives",
tom2's shortened yoke; build123d then warns "Boolean operation unable to clean" and keeps the faces
unmerged). So a unify -- build123d's or a model's own -- that fails on a shape holding a TShape at
two places is made again, with its settings, on a copy whose every sub-shape stands at one place
(`BRepBuilderAPI_Copy`: the same geometry; `kernel/memo.py`, `_one_place`, counted: the memo's
`copied_apart`); one that succeeds is the kernel's, untouched, so no name or face moves where
nothing failed. cadgen 0.7 handed every child model's result over re-made, each sub-shape at one
place; since 0.8 a child's or a `@memo` stage's result is handed on live, so the remaking is the unify's.

build123d's own operations never change a shape they are given in place. `ShapeFix_Shape`
does (it fixes the sub-shapes it is handed): run by a model on a shape a placement shares,
it is given a copy of that shape first, a `copy` feature of the model's, and the other
placements stay as they were (counted: the memo's `copied_on_write`). A `BRep_Builder` a
model drives itself on a placed shape is not seen: it changes every placement.

A file read again in one build from the same site -- a helper reading a screw for each
place it goes -- is decoded once: the read hands back the first read's tree again, new
objects on the same TShapes. A read from another site is another feature, named apart, and
decoded apart: one B-rep carries one set of names.

The document keys a part by its TShape, orientation, paints and materials
(`document.collect`), then merges parts of one geometry key whose elements are named alike
and which hold the same colour, paints and materials (`document.merge`): a helper building
the same bracket for each place it goes is one prototype too. Placements painted or given
materials apart are prototypes apart, the second its own topology over the same geometry
(`document._apart`: the shape tool holds one label per shape).
