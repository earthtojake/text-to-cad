# References

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A ref names a part, an assembly or one element of a document in the engine's own names
(`refs.py`), and it is resolved by name in the document as it is now -- the latest build. Nothing
of an earlier build is kept: an element a later build moved or resized resolves to where it is
now; one it deleted fails, naming it; one whose making changed (a feature started or stopped
touching it, so it is named otherwise) fails too, listing what its atom is named now (`plate.body.6
is now f:plate.body.6`), never picking one.

```
REF      = [FILE "#"] SELECTOR ("," SELECTOR)*     a bare ELEMENT after an owner is that owner's
SELECTOR = OWNER | [OWNER "/"] ELEMENT              no OWNER: the document's root
OWNER    = SEGMENT ("/" SEGMENT)*                   an occurrence's path, or its last segments
SEGMENT  = LABEL | LABEL "." N | "QUOTED" ["." N]   N: the N-th of the siblings so labelled
ELEMENT  = NAME | face N | edge N | vertex N        NAME: f:…, e:…, v:… (Element names)
```

An occurrence is named by the labels on the way to it. A label its siblings share takes its
number among them, in component order: `hand/finger.2` is the second component labelled `finger`
of `hand`, and a repeated part is always addressed by such a path, never by a number across the
document. An owner may start at any level (`palm`, `finger.2/face 7`) where what it names is one
occurrence; a path whose first segment names the root is read from the root. A label that names
several occurrences is refused with their paths (`finger names 3 occurrences in hand.xbf:
hand/finger.1, hand/finger.2, hand/finger.3`). A segment is read as a label first and as `LABEL.N`
only where no sibling bears it whole; a label holding `/`, `,` or a quote, or one that would read
as another sibling's, is JSON-quoted. An element of an assembly resolves from it when one part
below holds it, so a document of one part takes its elements by the document's name
(`plate/face 3`). A part's elements are numbered by their `TopExp.MapShapes` ordinals, the ones
its names, `faceNames` and the XBM2 buffer use. `FILE` (everything before the first `#`,
JSON-quoted where it holds one; a command's or a tool's source, `FILE#REF`, takes the longest part of
itself that is a file, so a path that holds a `#` -- a folder named `project#1` -- is never cut there:
`addresses.parts`) is an absolute CAD file path, the last segments of the document's
path, or a document's id (a model's, which `cad run SCRIPT.py` prints, or a file's), and must be the
document resolved in: the same file, the same path's last segments, or the same id. A script is
never a `FILE`: `<uuid>#face 1` names face 1 of the model whose id it is, read as the engine holds
it. A canonical ref -- what `inspect` answers --
spells the element by its name (its ordinal only where it has none) under its part's label where
that label names one occurrence, else under the occurrence's path from the root; in a document of
one part, under the document's name. It is also what the viewer copies of an `.xbf`'s selection,
the file's path first (`/work/XBF/kit.xbf#kit/hand/finger.2/face 7`), or a model's id first for a
model the engine holds: the viewer's parser and speller
of this grammar (`cadRefs` in the bundled runtime) are held to this module's, case for case, by a
fixture both suites assert.

A ref resolves inside the engine, for `inspect` and the viewer, never in a model:
`cad xbf inspect DOC REF` (`cad.inspect(source, ref)`) answers what it names, placed where its
occurrence stands -- an element's kind, ordinal, name and canonical ref, the kernel's facts of it,
and, of a model's document, `made_by`, the feature and the function, file and line of the call that made it; a part's or
an assembly's volume and mass, and its world `bounds` (each part's measured box placed where it
stands), with a part's `placement`: the origin and the x, y and z axes of its instance's matrix.
Nothing is built or measured again for them. A model that changes what a person picked reads that answer and
edits the code `made_by` names, or selects the element from the live shape with build123d
(`base.faces().sort_by(bd.Axis.Z)[-1]`); a check reads the document with `xbf.read` and walks its
tree by labels.

**A model never reads a file its own build writes**: its own xbf or export, a child's, a
sibling's (`reader.refuse_written`: `xbf.read` and `step.read` ask as they read the file). Read,
the file would be an input the build rewrites -- its key moving on every build, so the model would
never be taken by its key -- or, kept out of the key, a model depending on its own past. A
model takes what it makes from the live shape instead: so its own output never invalidates it.
