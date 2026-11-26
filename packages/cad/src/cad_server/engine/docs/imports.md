# Imports

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`step.read(path)` reads a `.step`/`.stp`, `xbf.read(path)` an engine document; both copy the
file's geometry into the model's document (`reader.py`). The result is a compound tree of the
file's assembly: an assembly a `Compound` of its components, a part a handle of its own on its
product's geometry (a move places that occurrence, never its siblings), every node named as the
file names that occurrence (its own name, else its product's), coloured and given its material
as the file has them; XBF painted faces and material-painted STEP faces come too, and each element keeps
the name its file gives it (**Element names**). An xbf's joints, configurations and motions are
not imported: a part is a part. Linking between models is done by importing code, never by a
file reference. Both are file reads the memo keys by the file's bytes, so a later build's read
of the same bytes is the same objects, and both are the build closure's inputs.

`stl.read(path)` reads an `.stl` as data, never a shape: a `Mesh` of `vertices` (N x 3, the
file's numbers as millimetres; a point the triangles share is one vertex), `triangles` (M x 3
rows of indices into them), `name` (an ASCII STL's solid's, else the file's stem) and
`bounding_box()` (build123d's `BoundBox`), its arrays read-only. A mesh has no B-rep -- no
surface under a face, no curve under an edge -- so no document holds one: a model measures it
and builds B-rep from its numbers. Its read is keyed by the file's bytes as the others' are,
the same object again for the same bytes, and the file is one of the closure's inputs:

```python
@xbf("XBF/enclosure.xbf")
def enclosure():
    pcb = stl.read(HERE / "scans/pcb.stl").bounding_box()   # keyed by the scan's bytes
    return bd.Box(pcb.size.X + 6, pcb.size.Y + 6, pcb.size.Z + 4)
```

A result holding a mesh face -- a triangulation with no surface, as build123d's `import_stl`
makes, or a face a model builds of `stl.read`'s triangles -- is refused by the occurrence's
path before its document is made (`document.mesh_faces`), and the worker builds on: `kit/scan
is a mesh, not B-rep: face 1 is a triangulation with no surface (as build123d's import_stl
makes), and a document holds B-rep alone. Read the mesh as data with stl.read(path) ...`. The
kernel's face modifier, which every part passes through (`document.direct`), crashed the
process on one.

build123d's importers (`import_step`, `import_brep`, `import_stl`) are file reads the memo keys
by the file's bytes too: a body that calls one is kept and replayed while the bytes are the same.
build123d's `Mesher.read` and OCCT's readers driven directly read a file past the engine: a
body that calls one runs on every build (**Body retention**).

**The fast input is an xbf.** Reading one is many times faster than parsing a STEP of the same
geometry (tom-sized: seconds against most of a minute) and keeps the engine's names losslessly.
Convert a vendor STEP once, keep the xbf beside it, and read the xbf:

```
cad step export vendor.step vendor.xbf
```

The conversion is the author's: the engine writes no derived file beside an input of its own.
`xbf.read` of a converted STEP is `step.read` of the STEP: the same geometry, names, colours and
materials.

**A STEP is parsed in a reader process.** OCCT's XCAF reader works in many times the memory of
what it makes (2.3 GB for a 354 MB file) and the allocator keeps most of it, so a worker that
parsed a STEP would hold that for its life. A build starts one reader process on its first STEP
read, reuses it for the build's other reads and closes it when the build ends; the reader
answers with the document described as data (products, names, colours, materials, element
names, components) and one `BinTools` dump of the parts' shapes and the components' locations,
and the worker assembles the tree from them. A shape written and read once is what a saved
document reads back, so the tree is a function of the file. An xbf is read in the worker by the
document's own retrieval driver.

**A STEP is the file it is.** A STEP can name other files as its parts (an external document
reference, `DOCUMENT_FILE`), which the XCAF reader's transfer would open -- beside it, above it or
anywhere by an absolute path -- and add to the document as the STEP's own. Every STEP read
(`step.read`'s reader process, and the read behind the viewer, an export and a snapshot) checks
the parsed file before it transfers it and refuses one that names another file
(`document.refuse_external_files`).
