# Element names

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

Every face, edge and vertex of a part is named as FreeCAD's topological naming names
it: by the feature history that made it, so it keeps its name unless that history
changed (`kernel/trace.py`). A name is its kind and its derivation: the atom it
starts from, the n-th element of its kind a feature made, and a step per feature that
made it out of another (`f:plate.body.3;M:plate.relief`: face 3 of the box, modified
by the relief cut). A long derivation folds to its last feature and a digest
(`f:plate.relief~5d1e0c2f9a3b`); the worker that built it spells it out. Every name is a
reference the viewer's ref grammar parses (`cadRefs` in the bundled `@cad/core` runtime, mirrored as
`refs.py`'s `ELEMENT_NAME`, which the naming in `kernel/trace.py` reads and which loads no kernel): a feature name has at most one dot, every segment
is an identifier, and an atom ends in a number or a digest. A name holds no line or file (law 9): a line is
what the worker serves, now.

A feature is the author's name for its result. A call whose result an assignment
stores is `<function>.<target>` (`relief = body - hole` in `plate` is `plate.relief`;
`self.body = ...` is `body`; each target of `a, b = ...` names its own); the calls the
same statement made on the way are `<function>.<target>_<operation><n>`
(`plate.relief_make_cylinder1`). The first statement in a function to assign a target
names it as it is; a later one -- a reassignment, `plate = plate - hole` -- is identified
by its statement's skeleton, its syntax tree with every literal (number, string)
masked: it is `<target>_<tag>`, the tag six letters of that skeleton
(`plate_cfjpgj`), counted only among the statements of the same skeleton in the
function (`plate_cfjpgj2` for the second, or for a loop's second run). So inserting a
step of another shape renames none of the steps around it, and a dimension edit -- a
literal -- keeps every name. Two statements of one skeleton still count in order:
inserting one before another of its shape renames the later one, and a statement
inserted before a function's first assignment to a target becomes the one named as it
is. A helper that makes a shape in its `return` statement and hands it back unassigned
(`return bd.Pos(x, 0, 0) * bd.Cylinder(r, h)`) makes it for its caller: its calls are
named by the caller's assignment the result flows into, as the calls that statement
made on the way (`plate.plate_cfjpgj_make_cylinder1`), through further helpers that
return it too. A call whose result is assigned nowhere (a return expression of the
model, an expression statement) is `<function>.<operation><count>` (`plate.fuse1`),
counted among the part's unassigned calls. Nothing is counted in an order OCCT picks: calls
given pieces of the same features' results (a loop over a sketch's faces) count by where
their pieces are, a compound's own elements are numbered piece by piece in that order, and
elements still named alike take `;D2`, `;D3` in it -- OCCT hands a boolean's or a text's
pieces back in an order the heap sets, so two cold builds would otherwise name them apart. So inserting a feature renames only what it
touches, and renaming a variable renames that feature's elements and nothing else. An author's `label` on a shape handed to a later construction
names, in what that construction makes, the feature that first made the labelled shape
(back along what each feature was made of, to where the shape stops being one chain):
a cut appended to it after takes nothing over. A shape a model places, copies or fixes past
build123d, with OCCT's `BRepBuilderAPI_Transform`, `_GTransform` or `_Copy`,
`ShapeFix_Shape`, `ShapeUpgrade_UnifySameDomain` or `BRepFilletAPI_MakeFillet`, is a
feature like any other (`kernel/memo.py`, `_MAKER_FEATURES`): its elements are named
from what the maker reports, or, where it reports nothing, from the shape it was given
by ordinal when the two map one-to-one. A placement copies nothing (**Placements**): a
placed part is its prototype and has its prototype's names, whichever placement the
model labelled. A label on one of several shapes a feature made -- one part of a file
read -- names what is made of that shape alone, never what is made of its siblings; and
placements of one shape labelled apart name their occurrences and pin none of those
labels on the shape they share, where one placement's label would rename what is made of
every other.

An element of a shape read from a file (`step.read`, `xbf.read`) is named within its own product,
the part of the file it belongs to, however often the file places it: by the name the
file gives it (`read.stepcaf.subshapes.name`; a STEP this engine wrote names every face,
and those names come back as they were; `NONE`, the schema's empty name, is none),
else by its ordinal in the product
(`f:<feature>.<ordinal>`), never by an ordinal across the file. A placement or a compound
of a shape no name reaches never claims its elements as its own.

A warm build that hands a part back unchanged keeps its names
while the functions they come from assign the same targets; a rename names it again.

A child model or a `@memo` function names what its `return` statement makes in itself
(`stage.cut1`), never by its caller's assignment as a plain helper's return is: the engine
calls it, and a replay cannot follow the caller. So marking a helper that returns a
construction unassigned (`return body - holes`) renames those elements once; marking one
that returns an assigned name (`return body`) renames nothing.
