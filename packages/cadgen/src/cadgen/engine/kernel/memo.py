"""The kernel memo: one interception layer at build123d's topology layer, and what
it remembers, in the worker's memory for the worker's life.

Installed in the worker beside ``determinism.install()``, idempotently, the layer
patches every kernel construction build123d's topology modules offer -- primitives,
booleans, fillets and chamfers, sweeps and lofts, faces and wires, copies and moves,
``clean``, ``is_valid``, ``split``, ``project_faces``, the constructors that build a
face from wires, a wire from edges, a shell from faces, a solid from a shell and a
compound from shapes, and the file importers -- so that every call made from a
model's own code inside a run (``run()``) is seen once, at the boundary.
Builder-mode wrappers are not patched: their inner topology calls are the ones seen.
Each call seen is a **feature** for naming (``trace``), whatever the memo does with
it. The OCCT makers a model may run itself past build123d -- a shape fix, a unify, a
fillet, a transform, a copy (``_MAKER_TARGETS``) -- are handed to it as this layer's
subclasses, each run of one an operation (``_maker_class``) and a feature
(``_MAKER_FEATURES``), and a
file the engine reads for a model (``wrap_function``: ``read_step``, ``read_xbf``,
``read_mesh``) is an operation keyed by the file's bytes.

build123d's importers (``import_step``, ``import_brep``, ``import_stl``) are operations keyed by
the file's bytes as the engine's readers are: the body that calls one holds the file to its bytes
(its ``checks``), and is kept and replayed while they are the same.

**Reads past the engine.** The readers a model may drive itself (``_READER_TARGETS``: OCCT's,
patched in place on their classes, and build123d's ``Mesher.read``) read their file in C or C++,
where the audit hook on Python's ``open`` hears nothing, and make what no key names. A body that
calls one is not kept (``_bypassed``): it runs on every build, and the build names the call and
the file (``_Run.bypassed``). The file is one of its inputs all the same, held to its bytes as a
file it opened itself is, so its closure keeps a key: a restart with nothing changed takes its
document, and one after the file changed builds it.

**Keys.** A call is keyed by its operation, every setting it runs with, its
canonical parameters and the keys of the shapes it was given. The settings are what
the parameters do not say: what a boolean's OCC operation object was set to before
the call (its fuzzy value and glue mode by build123d, the non-destructive mode by
this layer, below), the class-wide ``SkipClean``, and the font file a text reads, by
its bytes as an imported file is. A shape's key is where it came from: the memo key
of the operation that made its ``TShape`` (the registry, pointer to key) and its
position among the shapes that call returned, or, for a sub-shape, its ancestor's
key with its kind and its index in the ancestor's ``TopExp`` map; with the shape's
own location and orientation, the attributes an operation may copy from it (label,
colour, ``for_construction``, its material, the face colours and materials a model
painted; a compound's constructor leaves the materials out, which it does not hold)
and the keys of its children; and with the effects (below) every operation so far has had on it. A shape cast
afresh from a compound -- what iterating one hands back, as build123d's intersection
and ``unwrap`` do -- has no ancestor to name it by; when a root holds its TShape
(``_SUBS``) it is keyed as that root's sub-shape, by its kind and its ordinal among the
root's sub-shapes of that kind (``_held``). A shape no operation of this process made
has no key, and a call given one runs uncached. An empty shape (``bd.Sketch()``, what
build123d's ``+`` sums onto) holds no geometry: it is keyed by its class, and is no input. The n-th call with one key in a
model's body is its own entry (``scope``), so two identical constructions in one body
are two objects, as in plain Python; and the body's ordinals are its own, the same
whether it runs as a build's root or as a child and whatever the build ran before it
-- another model reading the same file or making the same box. The model's name is
part of the entry's key, so two bodies never share an object.

**Hits.** A hit requires the key and, for every shape input, the very ``TShape``
the entry was computed with, and returns the SAME Python objects the first run made,
restored to a snapshot taken when the operation returned: ``label``, ``_color``,
``topo_parent``, ``joints``, anytree parent and children, every other object field,
and ``wrapped``'s TShape, location and orientation. Nothing is reconstructed and
nothing is copied: pointer identity holds along every chain of hits, and every miss
makes its downstream miss, since a fresh result is a new TShape. A constructor cannot
return another object, so its hit hands the first run's ``TopoDS`` to the kernel
helper the constructor calls, and the object the model just made wraps that TShape.

**Effects.** The kernel modifies its INPUTS: an extrusion clears its profile's
``Free`` flag and appends curve representations to the profile's edges. A boolean
does not: the layer sets every boolean it sees non-destructive (``BOPAlgo_Options``),
so the kernel copies the sub-shapes it would change and shares the rest, and what it
left alone keeps its identity in the result. A destructive boolean writes into the
edges it leaves on a plane their curve on that plane (a p-curve); a non-destructive
one writes none, so every later query (a fillet makes thousands) would project it
again: each boolean writes it into the edges it made, and no other
(``_store_pcurves``), as it returns. What an operation does is captured as each
sub-shape's state -- kind, tolerance, the seven flags, how many representations it
holds, an edge's parametric flags -- read after the operation and compared with the
state before it. A compound's constructor changes nothing of an input but its own
``Free`` flag: its capture reads each input's own state alone (``_capture``'s
``top``), and its hit, as any hit, costs the rows later operations left on what it
made (``_reset``), so an assembly's compound costs its children's count, not their
sub-shapes'. A change is a sparse delta per sub-shape,
noted in a ledger, and the ledger indexes each row at the roots whose reset may undo
it (``_rowed``): a hit replays the delta on the input as it was given, and a hit of a
shape's maker undoes every delta applied to it since it returned, reading that index,
so a hit costs the rows later operations left on its result, not the result's size --
a moved copy of an imported assembly is handed back without walking its sub-shapes. A
change no delta expresses makes the input's maker forget its entry.

**Placements.** build123d's deep copy -- behind ``moved``, ``located``, ``copy.copy`` and
every transform -- is this layer's (``_sharing``): new objects of the same classes, each a
new handle on the SAME TShape, never ``BRepBuilderAPI_Copy``. So a placement registers
nothing of its own, its key is its source's with its location, and a part placed ten times
is one B-rep. A maker that changes what it is given in place (``_IN_PLACE``) is handed a
copy of a placed shape (``_unshared``, ``copied_on_write``). A file read again in one build
from the same site shares the first read's decode (``_read_again``, ``shared_reads``).

**Registration.** A result's shapes are registered under the entry that made them, and
every sub-shape below a root names the first root registered holding it (``_SUBS``):
what a foreign wrapper embeds, and where a ledger row is indexed. The walk stops at a
shape a root already holds, so registering a container of registered parts costs its
direct children, not the parts' sub-shapes.

**Queries.** A bounding box is no operation and no feature -- it makes no shape -- but a
model asks for one of the same unchanged shapes on every build, and the precise box
build123d takes by default costs milliseconds a shape. build123d measures the bare
geometry (it clears any mesh first and takes no tolerance), so a box is a function of the
TShape, its placement and the arguments: one of a TShape this process made is kept by
those, with the effects applied to it so far, and answered again (``_bounding_box``).

**Bodies.** A model's body is one coarse entry above its calls (``body``): keyed by the
bytes it is made of -- the source its caller names, the files it read, by their bytes -- it
is not called when they are what they were in its last run in this process. Its run is
replayed instead (``_replay``): every entry it hit or made reset and bound to this run as a
hit binds it, every feature it recorded recorded again in the same order with what it was
given and returned then, every body it called replayed in turn, and its result handed back
as it returned it -- the same live objects. The trace is the one a run of the body would
leave, so the names of what a caller makes of it compose as if it had run, and a skipped
body makes no call, so its caller's ordinals are what they would be. A body that ran a call
plain, or whose entries are gone, runs.

**Motions.** A function motion's function is sampled after its body returned (``listened``):
the files it opens are heard as a body's are, held to their bytes, and are the model's inputs
(``MotionReads``), so a document is not taken while one of them changed.

**History.** While a call from the model's code runs, the OCCT makers it runs record
what they were given and what they made (``history``), and right after it the call's
history is composed from them. The feature carries it, and so does the entry: a hit
hands the feature the miss's history too, and runs no maker; the names the trace
gives are the same either way.

The memo lives in this process's memory for the life of the process and holds what
the last ``RUNS_KEPT`` builds used (``_sweep``): a build is a scan of every call the
model makes, so a bound by count would evict, on a model larger than the bound, each
entry just before the next build asks for it. A build is one program's pass over the
models it builds (``_mark``): a script building more models than ``RUNS_KEPT`` (a robot
and its links) is one build, so each model's next run finds what this one used, and a
program building a model again in one pass begins another. Nothing of it is ever written anywhere,
and a new process computes everything. ``CADGEN_ENGINE_MEMO=0`` turns hits off and nothing else.
"""

from __future__ import annotations

import array
import contextlib
import enum
import functools
import hashlib
import importlib
import inspect
import itertools
import numbers
import os
import struct
import threading
import weakref
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterator

from OCP.BRep import BRep_TEdge, BRep_TFace, BRep_TVertex
from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape

from cadgen.engine.kernel import history as kernel_history
from cadgen.engine.kernel.trace import Trace

__all__ = ["CAPACITY", "RUNS_KEPT", "clear", "enabled", "install", "listened", "motion_reads", "run", "stats",
           "uninstall", "wrap_function"]

# What a build keeps: every entry and key the last RUNS_KEPT outermost runs used, so an
# edit, its revert and a second edit in between all find the first run's steps. The
# counts below are a safety far past any model's size, never the working bound.
RUNS_KEPT = 4
CAPACITY = 1 << 21
_SUB_MAPS = 1024
_KEYS = 1 << 24

_LOCK = threading.RLock()
_LOCAL = threading.local()
_MEMO: "OrderedDict[tuple[int, int], _Entry]" = OrderedDict()
_REGISTRY: dict[Any, "_Made"] = {}
_LEDGER: dict[Any, list["_Row"]] = {}
_KEY_IDS: "OrderedDict[tuple, int]" = OrderedDict()
_KEY_IDS_NEXT = itertools.count(1)
# The outermost runs so far; each leaves a marker in the LRU order of the memo and of the
# key table, behind which everything it touched is moved (``_sweep``).
_GENERATIONS = itertools.count(1)
_MARKS: list[int] = []
# The pass the last marker began: its program's run and the models it has built so far.
_PASS: dict[str, Any] = {"program": None, "models": set()}
_MAPS: "OrderedDict[tuple[int, int], tuple[Any, Any]]" = OrderedDict()
# A root's sub-shapes of one kind, TShape to its first ordinal (``_held``), for the roots a
# model keeps casting shapes out of.
_ORDINALS: "OrderedDict[tuple[Any, int], dict]" = OrderedDict()
_STATS = {"hits": 0, "misses": 0, "unkeyable": 0, "unreplayable": 0, "errors": 0, "tainted": 0,
          "bodies_run": 0, "bodies_skipped": 0, "copied_on_write": 0, "shared_reads": 0}
_RUN_IDS = itertools.count(1)
_EFFECT_IDS = itertools.count(1)
# Every row applied takes the next stamp: a maker's reset undoes the rows applied
# after it returned (its ``born`` stamp) by runs before this one.
_SEQUENCE = itertools.count(1)
_installed = False
_EDGE, _VERTEX, _FACE, _COMPOUND = int(TopAbs_EDGE), int(TopAbs_VERTEX), int(TopAbs_FACE), int(TopAbs_COMPOUND)
# The attribute a model's painted face colours live in (``cadgen.engine.paint``).
FACE_COLORS = "xbf_face_colors"
FACE_MATERIALS = "xbf_face_materials"
CONFIGURATIONS = "xbf_configurations"  # an assembly's mechanism states by name (``mechanism.mechanism_state``)
COUPLINGS = "xbf_couplings"  # and its couplings by name (``mechanism.gear_pair`` and its two siblings)
ANIMATIONS = "xbf_animations"  # and its animations by name (``animations.animation``): plain values


class _Unkeyable(Exception):
    """This call cannot be keyed or its result cannot be kept: it runs plain."""


def enabled() -> bool:
    return os.environ.get("CADGEN_ENGINE_MEMO", "1").strip() != "0"


# --- what is patched ----------------------------------------------------------------------
#
# (class, attribute, op label), enumerated from build123d 0.11.1's topology modules.
# A classmethod's label is prefixed with the class it is called on; ``_bool_op``'s
# label is the boolean it runs (cut, fuse, common, section, split), as is that of
# ``_bool_op_list``, the boolean an intersection runs, which hands back its pieces; a
# constructor's is its class.

_INSTANCE_TARGETS = (
    ("Shape", "_bool_op", "bool_op"),
    ("Shape", "_bool_op_list", "bool_op_list"),
    ("Shape", "clean", "clean"),
    ("Shape", "located", "located"),
    ("Shape", "moved", "moved"),
    ("Shape", "mirror", "mirror"),
    ("Shape", "rotate", "rotate"),
    ("Shape", "scale", "scale"),
    ("Shape", "translate", "translate"),
    ("Shape", "transform_shape", "transform_shape"),
    ("Shape", "transform_geometry", "transform_geometry"),
    ("Shape", "transformed", "transformed"),
    ("Shape", "project_faces", "project_faces"),
    ("Shape", "split", "split"),
    ("Shape", "__copy__", "copy"),
    ("Shape", "__deepcopy__", "deepcopy"),
    ("Mixin3D", "chamfer", "chamfer"),
    ("Mixin3D", "fillet", "fillet"),
    ("Mixin3D", "hollow", "hollow"),
    ("Mixin3D", "offset_3d", "offset_3d"),
    ("Mixin3D", "dprism", "dprism"),
    ("Mixin3D", "max_fillet", "max_fillet"),
    ("Solid", "draft", "draft"),
    ("Mixin2D", "offset", "offset"),
    ("Mixin2D", "split_by_perimeter", "split_by_perimeter"),
    ("Face", "chamfer_2d", "chamfer_2d"),
    ("Face", "fillet_2d", "fillet_2d"),
    ("Face", "make_holes", "make_holes"),
    ("Face", "project_to_shape", "project_to_shape"),
    ("Face", "to_arcs", "to_arcs"),
    ("Face", "without_holes", "without_holes"),
    ("Mixin1D", "offset_2d", "offset_2d"),
    ("Mixin1D", "perpendicular_line", "perpendicular_line"),
    ("Mixin1D", "project", "project"),
    ("Wire", "chamfer_2d", "chamfer_2d"),
    ("Wire", "fillet_2d", "fillet_2d"),
    ("Wire", "fix_degenerate_edges", "fix_degenerate_edges"),
    ("Wire", "project_to_shape", "project_to_shape"),
    ("Wire", "stitch", "stitch"),
    ("Wire", "trim", "trim"),
    ("Edge", "trim", "trim"),
    ("Edge", "trim_to_length", "trim_to_length"),
    ("Edge", "project_to_shape", "project_to_shape"),
    ("Edge", "reversed", "reversed"),
    ("Edge", "close", "close"),
)
_PROPERTY_TARGETS = (("Shape", "is_valid", "is_valid"),)
_CLASSMETHOD_TARGETS = tuple(
    (cls, name, name)
    for cls, names in (
        ("Solid", ("extrude", "extrude_linear_with_rotation", "extrude_taper", "extrude_until",
                   "from_bounding_box", "make_box", "make_cone", "make_cylinder", "make_loft",
                   "make_sphere", "make_torus", "make_wedge", "revolve", "sweep", "sweep_multi", "thicken")),
        ("Face", ("extrude", "make_bezier_surface", "make_gordon_surface", "make_plane", "make_rect",
                  "make_surface", "make_surface_from_array_of_points", "make_surface_from_curves",
                  "make_surface_patch", "revolve", "sweep")),
        ("Shell", ("extrude", "make_loft", "revolve", "sweep")),
        ("Wire", ("combine", "extrude", "make_circle", "make_convex_hull", "make_ellipse", "make_polygon", "make_rect")),
        ("Edge", ("extrude", "make_bezier", "make_circle", "make_ellipse", "make_helix", "make_hyperbola",
                  "make_line", "make_mid_way", "make_parabola", "make_spline", "make_bspline",
                  "make_spline_approx", "make_tangent_arc", "make_three_point_arc")),
        ("Compound", ("extrude", "make_text", "make_triad")),
    )
    for name in names
)
# A constructor and the kernel helper it calls for the shape it builds: on a
# hit the helper hands back the first run's TopoDS instead of building one.
# ``Compound`` builds its container on every attachment of children, so its hit
# lets the constructor run and then takes the first run's container; so does a
# ``Vertex`` made from coordinates, which calls no helper -- keyed, so what a model
# makes of a point (a placed vertex) is keyed too.
_CONSTRUCTOR_TARGETS = (("Face", "face"), ("Wire", "wire"), ("Shell", "shell"), ("Solid", "solid"), ("Compound", None),
                        ("Vertex", None))
_HELPER_TARGETS = (
    ("two_d", "_make_topods_face_from_wires", "face"),
    ("two_d", "_sew_topods_faces", "shell"),
)
_HELPER_CLASSMETHODS = (("Wire", "_make_wire", "wire"), ("Solid", "_make_solid", "solid"))
_IMPORTER_TARGETS = ("import_step", "import_brep", "import_stl")
# Operations whose first argument is a file, keyed by the file's bytes: the importers,
# and the engine's own readers (``wrap_function``: ``read_step``, ``read_xbf``, ``read_mesh``).
_FILE_OPS = {"import_step", "import_brep", "import_stl", "read_step", "read_xbf", "read_mesh"}
# Readers past the engine's (see the module), patched in place on their classes: (module,
# class, method, whether it is static). XSControl_Reader's is IGES's readers' too, and
# RWMesh_CafReader's glTF's and OBJ's; ``Mesher.read`` is build123d's 3MF and STL reader (lib3mf).
_READER_TARGETS = (
    ("OCP.STEPControl", "STEPControl_Reader", "ReadFile", False),
    ("OCP.STEPCAFControl", "STEPCAFControl_Reader", "ReadFile", False),
    ("OCP.STEPCAFControl", "STEPCAFControl_Reader", "Perform", False),
    ("OCP.XSControl", "XSControl_Reader", "ReadFile", False),
    ("OCP.IGESCAFControl", "IGESCAFControl_Reader", "Perform", False),
    ("OCP.RWStl", "RWStl", "ReadFile_s", True),
    ("OCP.RWStl", "RWStl", "ReadAscii_s", True),
    ("OCP.RWStl", "RWStl", "ReadBinary_s", True),
    ("OCP.StlAPI", "StlAPI", "Read_s", True),
    ("OCP.StlAPI", "StlAPI_Reader", "Read", False),
    ("OCP.BRepTools", "BRepTools", "Read_s", True),
    ("OCP.BinTools", "BinTools", "Read_s", True),
    ("OCP.RWMesh", "RWMesh_CafReader", "Perform", False),
    ("build123d.mesher", "Mesher", "read", False),
)
_BOOLEAN_LABELS = ("bool_op", "bool_op_list")
_BOOLEANS = {"BRepAlgoAPI_Cut": "cut", "BRepAlgoAPI_Fuse": "fuse", "BRepAlgoAPI_Common": "common",
             "BRepAlgoAPI_Section": "section", "BRepAlgoAPI_Splitter": "split"}
# OCCT makers a model may run itself, past build123d (``_maker_class``): (module, class,
# the method that runs it -- None where its constructor does --, the constructor
# arguments that make one that has not run, by position, where its constructor runs it,
# whether ``Shape()`` runs it when it has not run, and the setters whose arguments its
# key names).
_MAKER_TARGETS = (
    ("OCP.ShapeFix", "ShapeFix_Shape", "Perform", (), False, ("SetPrecision", "SetMinTolerance", "SetMaxTolerance")),
    ("OCP.ShapeUpgrade", "ShapeUpgrade_UnifySameDomain", "Build", (), False,
     ("SetLinearTolerance", "SetAngularTolerance", "AllowInternalEdges", "SetSafeInputMode", "KeepShape")),
    ("OCP.BRepFilletAPI", "BRepFilletAPI_MakeFillet", "Build", (), True, ("Add", "SetParams", "SetContinuity")),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_Transform", None, (1,), True, ()),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_GTransform", None, (1,), True, ()),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_Copy", None, (), True, ()),
)
# Every one of them is a feature when the model runs it, as a build123d call is, by the operation
# its name spells: a shape placed, copied, fixed, unified or filleted past build123d is named.
_MAKER_FEATURES = {"BRepBuilderAPI_Transform": "transform", "BRepBuilderAPI_GTransform": "gtransform",
                   "BRepBuilderAPI_Copy": "copy", "ShapeFix_Shape": "fix", "ShapeUpgrade_UnifySameDomain": "unify",
                   "BRepFilletAPI_MakeFillet": "fillet"}


def install() -> bool:
    """Patch the topology layer, once per process. Returns installed-now. A
    target build123d no longer has is an error: the table is this version's."""
    global _installed
    with _LOCK:
        if _installed:
            return False
        import build123d
        from build123d import importers, topology
        from build123d.topology import two_d

        for cls_name, attr, label in _INSTANCE_TARGETS:
            _patch(getattr(topology, cls_name), attr, label, "instance")
        for cls_name, attr, label in _PROPERTY_TARGETS:
            _patch(getattr(topology, cls_name), attr, label, "property")
        for cls_name, attr, label in _CLASSMETHOD_TARGETS:
            _patch(getattr(topology, cls_name), attr, label, "classmethod")
        for cls_name, _slot in _CONSTRUCTOR_TARGETS:
            _patch(getattr(topology, cls_name), "__init__", cls_name, "constructor")
        for module_name, attr, slot in _HELPER_TARGETS:
            module = {"two_d": two_d}[module_name]
            function = getattr(module, attr)
            if not getattr(function, "__kernel_memo__", False):
                setattr(module, attr, _helper(slot, function))
        for cls_name, attr, slot in _HELPER_CLASSMETHODS:
            cls = getattr(topology, cls_name)
            static = inspect.getattr_static(cls, attr)
            if not getattr(static.__func__, "__kernel_memo__", False):
                setattr(cls, attr, classmethod(_helper(slot, static.__func__)))
        for name in _IMPORTER_TARGETS:
            original = getattr(importers, name)
            if getattr(original, "__kernel_memo__", False):
                continue
            wrapped = _wrap(name, original, "function")
            setattr(importers, name, wrapped)
            if getattr(build123d, name, None) is original:
                setattr(build123d, name, wrapped)
        topology.Shape.bounding_box = _bounding_box(topology.Shape.bounding_box)
        kernel_history.install()
        # After the history's patches, which read these modules' classes: build123d keeps
        # the classes it imported, and a model importing one now is handed its subclass.
        for module_name, class_name, perform, idle, builds, setters in _MAKER_TARGETS:
            module = importlib.import_module(module_name)
            original = getattr(module, class_name)
            if not getattr(original, "__kernel_memo__", False):
                setattr(module, class_name, _maker_class(original, perform, idle, builds, setters))
        for module_name, class_name, method, static in _READER_TARGETS:
            cls = getattr(importlib.import_module(module_name), class_name)
            if method not in cls.__dict__:
                raise TypeError(f"{class_name}.{method} is not {class_name}'s own")
            found = inspect.getattr_static(cls, method)
            original = found.__func__ if static else found
            if not getattr(original, "__kernel_memo__", False):
                owner = "OCCT's" if module_name.startswith("OCP.") else "build123d's"
                hooked = _reader(f"{owner} {class_name}.{method}", original, static)
                setattr(cls, method, staticmethod(hooked) if static else hooked)
        _audit_reads()
        _installed = True
        return True


# --- files a body opens itself --------------------------------------------------------------

_AUDITING = False


def _audit_reads() -> None:
    """Hear every file a model body opens, once per process (an audit hook stays)."""
    global _AUDITING
    if not _AUDITING:
        import sys

        sys.addaudithook(_audited)
        _AUDITING = True


def _audited(event: str, args: tuple) -> None:
    """An ``open`` for reading while a body runs, of a file none of the engine's readers
    keys -- not one a patched call reads (those run deeper than the body), not Python's own
    (a ``.py`` or ``.pyc``, a file of the standard library or an installed package): the
    body read it itself, so the file is one of its inputs. A regular file is noted with its
    stat as it was opened, or as missing (a body may try a file and go on without it), and
    is held to its bytes when the body returns (``_ReadInput``); anything else -- a pipe, a
    socket, a device -- has no bytes to hold, and the body is no longer retained: it always
    runs, and the build reports why (``unread``). An open for writing is an output: not
    heard."""
    if event != "open":
        return
    # A motion's function being sampled (``listened``) reads for its samples, whatever runs.
    log = getattr(_LOCAL, "sampling", None)
    state = getattr(_LOCAL, "run", None)
    if log is None and (state is None or state.depth or not state.bodies):
        return
    try:
        path, mode = args[0], args[1]
        if isinstance(path, int):
            return
        if mode is None:
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if flags & os.O_ACCMODE == os.O_WRONLY:
                return
        elif "r" not in mode and "+" not in mode:
            return
        name = os.fsdecode(path)
        if name.endswith((".py", ".pyc")) or _library_file(name):
            return
    except Exception:  # noqa: BLE001 - an audit hook never fails the open it hears
        return
    import stat as stat_module

    path = os.path.abspath(name)
    if log is None:
        log = state.bodies[-1]
    if path in log.reads:
        return
    try:
        found = os.stat(path)
    except FileNotFoundError:
        log.reads[path] = None
        return
    except OSError:
        found = None
    if found is None or not stat_module.S_ISREG(found.st_mode):
        log.retainable = log.keyed = False
        log.unread.append(path)
        return
    log.reads[path] = (found.st_size, found.st_mtime_ns)


class _ReadInput:
    """A file a body read itself (``_audited``), held to its bytes: the stat and blake2b
    digest it had when the body returned, or ``None`` for a file the body found missing.
    Called on the next build (``_replayable``) it answers the file's digest now: the stat
    first -- the same size and mtime are the same bytes, no read -- else the bytes hashed
    again, and a same digest under a new stat keeps the new stat."""

    __slots__ = ("path", "size", "mtime_ns", "digest")

    def __init__(self, path: str, size: int | None, mtime_ns: int | None, digest: str | None) -> None:
        self.path, self.size, self.mtime_ns, self.digest = path, size, mtime_ns, digest

    def __call__(self) -> str | None:
        import stat as stat_module

        try:
            found = os.stat(self.path)
        except FileNotFoundError:
            return None
        if not stat_module.S_ISREG(found.st_mode):
            raise _Unkeyable(f"{self.path} is no longer a regular file")
        if (found.st_size, found.st_mtime_ns) == (self.size, self.mtime_ns):
            return self.digest
        digest = _read_digest(self.path)
        if digest == self.digest:
            self.size, self.mtime_ns = found.st_size, found.st_mtime_ns
        return digest


def _read_digest(path: str) -> str:
    hasher = hashlib.blake2b(digest_size=32)
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                hasher.update(chunk)
    except OSError as exc:
        raise _Unkeyable(str(exc)) from exc
    return hasher.hexdigest()


def _hold_reads(log: "_BodyLog", state: "_Run") -> None:
    """When a body returns: each regular file it read held to its bytes (``_ReadInput``),
    one of its checks. A file whose stat moved while the body ran may have been read in two
    states: the body is not retained. The engine's own reads here are not the body's (a
    sampling's ``state`` is None: its log is no longer listening)."""
    if state is not None:
        state.depth += 1
    try:
        for path, opened in log.reads.items():
            if opened is None:
                if os.path.exists(path):
                    log.retainable = log.keyed = False  # appeared while the body ran
                    continue
                held = _ReadInput(path, None, None, None)
            else:
                try:
                    found = os.stat(path)
                except OSError:
                    log.retainable = log.keyed = False
                    continue
                if (found.st_size, found.st_mtime_ns) != opened:
                    log.retainable = log.keyed = False
                    continue
                try:
                    held = _ReadInput(path, found.st_size, found.st_mtime_ns, _read_digest(path))
                except _Unkeyable:
                    log.retainable = log.keyed = False
                    continue
            log.checks.append((held, held.digest))
    finally:
        if state is not None:
            state.depth -= 1


def _library_file(name: str) -> bool:
    from cadgen.engine.kernel.trace import _library_roots

    try:
        path = Path(name).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return any(root in path.parents for root in _library_roots())


# --- files read past the engine ---------------------------------------------------------------


def _bypassed(state: "_Run", call: str, path: str | None) -> None:
    """The running body read ``path`` through ``call``, a reader past the engine's (see the
    module): it is not kept, so it runs on every build, and the build names the call and the
    file. A regular file it read is one of its inputs as a file it opened itself is
    (``_audited``): held to its bytes when it returns, so its closure keeps a key and a restart
    with nothing changed takes its document; a file read again after it changed builds again.
    A read of what is no regular file leaves the body with no key (``keyed`` false)."""
    if not state.bodies:
        return
    import stat as stat_module

    log = state.bodies[-1]
    log.retainable = False
    try:
        found = os.stat(path) if path is not None else None
    except OSError:
        found = None
    if found is not None and stat_module.S_ISREG(found.st_mode):
        log.reads.setdefault(os.path.abspath(path), (found.st_size, found.st_mtime_ns))
    else:
        log.keyed = False
    if (call, path) not in log.bypassed:
        log.bypassed.append((call, path))


def _path_argument(values: tuple, kwargs: dict) -> str | None:
    """The file a reader is handed, absolute: its first argument that names one (a ``str``, a
    path, OCCT's ``TCollection_AsciiString`` or ``OSD_Path``); None for a read of a stream."""
    for value in (*values, *kwargs.values()):
        if isinstance(value, (str, bytes, os.PathLike)):
            return os.path.abspath(os.fsdecode(value))
        kind = type(value).__name__
        if kind == "TCollection_AsciiString":
            return os.path.abspath(value.ToCString())
        if kind == "OSD_Path":
            from OCP.TCollection import TCollection_AsciiString

            text = TCollection_AsciiString()
            value.SystemName(text)
            return os.path.abspath(text.ToCString())
    return None


def _reader(call: str, original: Any, static: bool) -> Any:
    """``original``, a reader past the engine's (``_READER_TARGETS``), as a model meets it: a
    file it reads from a model's body -- the body's own call, not the engine's, nor one inside
    another patched call -- marks the body (``_bypassed``); a read of a stream is the stream's
    reader's, and is not marked."""
    @functools.wraps(original)
    def hooked(*args: Any, **kwargs: Any) -> Any:
        sampling = getattr(_LOCAL, "sampling", None)
        if sampling is not None:
            # A motion's function reads past the engine's readers: its samples are not kept.
            sampling.bypassed.append((call, _path_argument(args if static else args[1:], kwargs)))
            return original(*args, **kwargs)
        state = getattr(_LOCAL, "run", None)
        if state is not None and not state.depth and state.bodies:
            path = _path_argument(args if static else args[1:], kwargs)
            if path is not None and state.trace.called_by_model():
                _bypassed(state, call, path)
        return original(*args, **kwargs)

    hooked.__kernel_memo__ = True
    return hooked


def uninstall() -> bool:
    """Restore every attribute ``install`` replaced. Returns uninstalled-now;
    the memo's entries stay (``clear`` drops them)."""
    global _installed
    with _LOCK:
        if not _installed:
            return False
        import build123d
        from build123d import importers, topology
        from build123d.topology import two_d

        targets = (_INSTANCE_TARGETS + _PROPERTY_TARGETS + _CLASSMETHOD_TARGETS
                   + tuple((cls_name, "__init__", cls_name) for cls_name, _slot in _CONSTRUCTOR_TARGETS)
                   + tuple((cls_name, attr, slot) for cls_name, attr, slot in _HELPER_CLASSMETHODS))
        for cls_name, attr, _label in targets:
            cls = getattr(topology, cls_name)
            static = inspect.getattr_static(cls, attr)
            if isinstance(static, classmethod):
                if getattr(static.__func__, "__kernel_memo__", False):
                    setattr(cls, attr, classmethod(static.__func__.__wrapped__))
            elif isinstance(static, property):
                if getattr(static.fget, "__kernel_memo__", False):
                    setattr(cls, attr, property(static.fget.__wrapped__, static.fset, static.fdel))
            elif getattr(static, "__kernel_memo__", False):
                setattr(cls, attr, _original(static.__wrapped__))
        for module_name, attr, _slot in _HELPER_TARGETS:
            module = {"two_d": two_d}[module_name]
            function = getattr(module, attr)
            if getattr(function, "__kernel_memo__", False):
                setattr(module, attr, function.__wrapped__)
        for name in _IMPORTER_TARGETS:
            wrapped = getattr(importers, name)
            if getattr(wrapped, "__kernel_memo__", False):
                setattr(importers, name, wrapped.__wrapped__)
                if getattr(build123d, name, None) is wrapped:
                    setattr(build123d, name, wrapped.__wrapped__)
        for module_name, class_name, *_spec in _MAKER_TARGETS:
            module = importlib.import_module(module_name)
            maker = getattr(module, class_name)
            if getattr(maker, "__kernel_memo__", False):
                setattr(module, class_name, maker.__kernel_memo_class__)
        for module_name, class_name, method, static in _READER_TARGETS:
            cls = getattr(importlib.import_module(module_name), class_name)
            found = inspect.getattr_static(cls, method)
            hooked = found.__func__ if static else found
            if getattr(hooked, "__kernel_memo__", False):
                setattr(cls, method, staticmethod(hooked.__wrapped__) if static else hooked.__wrapped__)
        if getattr(topology.Shape.bounding_box, "__kernel_memo__", False):
            topology.Shape.bounding_box = topology.Shape.bounding_box.__wrapped__
        kernel_history.uninstall()
        _installed = False
        return True


# Bounding boxes asked of shapes this process made: (TShape, placement, orientation,
# arguments, effects applied) to the box's corners, the least recently asked dropped.
_BOXES: "OrderedDict[tuple, tuple]" = OrderedDict()
_BOXES_HELD = 1 << 16


def _bounding_box(function: Any) -> Any:
    """``Shape.bounding_box`` answered from ``_BOXES`` for a shape the memo made (see
    **Queries**); any other shape, or a box asked outside a run, is measured."""
    @functools.wraps(function)
    def bounding_box(self: Any, tolerance: float | None = None, optimal: bool = True) -> Any:
        state = getattr(_LOCAL, "run", None)
        wrapped = self.__dict__.get("_wrapped")
        if state is None or wrapped is None:
            return function(self, tolerance, optimal)
        tshape = wrapped.TShape()
        made = _made_of(tshape, state)
        if made is None or not made.persistent():
            return function(self, tolerance, optimal)
        key = (tshape, _location_key(wrapped), int(wrapped.Orientation()), tolerance, bool(optimal),
               tuple(effect.id for effect in made.effects))
        with _LOCK:
            corners = _BOXES.get(key)
            if corners is not None:
                _BOXES.move_to_end(key)
        if corners is None:
            box = function(self, tolerance, optimal)
            corners = None if box.wrapped is None else box.wrapped.Get()
            with _LOCK:
                _BOXES[key] = corners if corners is not None else ()
                while len(_BOXES) > _BOXES_HELD:
                    _BOXES.popitem(last=False)
            return box
        from build123d.geometry import BoundBox
        from OCP.Bnd import Bnd_Box

        bnd = Bnd_Box()
        if corners:
            bnd.Update(*corners)
        return BoundBox(bnd)

    bounding_box.__kernel_memo__ = True
    return bounding_box


def _patch(cls: type, attr: str, label: str, kind: str) -> None:
    static = inspect.getattr_static(cls, attr)
    if kind == "classmethod":
        if not isinstance(static, classmethod):
            raise TypeError(f"{cls.__name__}.{attr} is not a classmethod")
        function = static.__func__
        if not getattr(function, "__kernel_memo__", False):
            setattr(cls, attr, classmethod(_wrap(label, function, kind)))
    elif kind == "property":
        if not isinstance(static, property):
            raise TypeError(f"{cls.__name__}.{attr} is not a property")
        if not getattr(static.fget, "__kernel_memo__", False):
            setattr(cls, attr, property(_wrap(label, static.fget, kind), static.fset, static.fdel))
    else:
        if not inspect.isfunction(static):
            raise TypeError(f"{cls.__name__}.{attr} is not a plain method")
        if not getattr(static, "__kernel_memo__", False):
            function = {"bool_op": _with_pcurves, "deepcopy": _sharing}.get(label, lambda found: found)(static)
            setattr(cls, attr, _wrap(label, function, kind))


def _wrap(label: str, function: Any, kind: str) -> Any:
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if label in _BOOLEAN_LABELS:
            _non_destructive(args, kwargs)
        state = getattr(_LOCAL, "run", None)
        if state is None or state.depth:
            return function(*args, **kwargs)
        return _call(state, label, kind, function, args, kwargs)

    wrapper.__kernel_memo__ = True
    return wrapper


def _with_pcurves(function: Any) -> Any:
    """build123d's boolean, and then the p-curves it left unwritten (``_store_pcurves``):
    what runs on a miss, an uncached call and a boolean nested in another call, and never
    on a hit, which hands back what the miss wrote."""
    @functools.wraps(function)
    def _bool_op(self: Any, args: Any, tools: Any, operation: Any) -> Any:
        args, tools = list(args), list(tools)
        result = function(self, args, tools, operation)
        _store_pcurves(result, (self, *args, *tools))
        return result

    _bool_op.__kernel_original__ = function
    return _bool_op


def _original(function: Any) -> Any:
    """What ``install`` found, under the step ``_with_pcurves`` adds to a boolean or
    ``_sharing`` puts in place of a deep copy."""
    return getattr(function, "__kernel_original__", function)


def _sharing(function: Any) -> Any:
    """build123d's ``Shape.__deepcopy__`` as a placement: a new object of the same class
    for every node, with its own copies of the node's fields -- its label, colour,
    materials, joints, children and parent, as build123d copies them -- and its own
    ``TopoDS`` handle on the SAME ``TShape``, at the same location and orientation
    (``TopoDS_Shape.Located``), where build123d runs ``BRepBuilderAPI_Copy`` on it. Every
    build123d placement is a deep copy and a location: ``moved``, ``located`` and
    ``copy.copy`` place the copy; the transforms, ``fix``, ``offset`` and a face's ``-``
    replace its ``wrapped`` at once with what they made. So a part placed ten times is
    one B-rep and ten handles, as FreeCAD's ``App::Link`` places it, and the document
    places one prototype ten times. The kernel's own operations never change a shape they
    are given in place; a maker a model runs itself is given a copy of a placed shape
    first (``_unshared``). The TShape is noted as placed (``_note_placed``)."""
    @functools.wraps(function)
    def __deepcopy__(self: Any, memo: dict) -> Any:
        import copy

        from build123d.topology.shape_core import downcast

        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        wrapped = self.__dict__.get("_wrapped")
        if wrapped is not None:
            memo[id(wrapped)] = downcast(wrapped.Located(wrapped.Location()))
            _note_placed(wrapped.TShape())
        for key, value in self.__dict__.items():
            if key == "topo_parent":
                result.topo_parent = value
            else:
                setattr(result, key, copy.deepcopy(value, memo))
            if key == "joints":
                for joint in result.joints.values():
                    joint.parent = result
        return result

    __deepcopy__.__kernel_original__ = function
    return __deepcopy__


def _note_placed(tshape: Any) -> None:
    """``tshape`` has a second handle now (``_sharing``): a maker that changes what it is
    given in place is given a copy of it (``_unshared``). Noted on the shape's record, or,
    for a shape no operation made, for the run."""
    state = getattr(_LOCAL, "run", None)
    made = _made_of(tshape, state)
    if made is not None:
        made.placed = True
    elif state is not None:
        state.placed.add(tshape)


def _is_placed(handle: Any, state: "_Run") -> bool:
    """Whether a placement shares ``handle``'s TShape, or the TShape of the shape holding it."""
    tshape = handle.TShape()
    if tshape in state.placed:
        return True
    made = _made_of(tshape, state)
    while made is not None:
        if made.placed:
            return True
        made = made.parent
    root = _SUBS.get(tshape)
    return root is not None and (root.placed or root.tshape in state.placed)


def _store_pcurves(result: Any, given: tuple) -> None:
    """A destructive boolean writes, into each edge it leaves on a plane, the edge's curve
    on that plane (its p-curve); a non-destructive one (``_non_destructive``) may write into
    no edge it was given, and leaves the edges it makes without one too, so every later
    query of one -- a fillet asks thousands -- projects it again. So, as the boolean
    returns, each edge of its result that is in none of its inputs -- an edge it made --
    has its p-curve on each plane of the result written once (``BRepLib``, which writes one
    only where the face is a plane and none is stored): the result's own edges, never an
    input's, so the boolean still leaves its inputs as it was given them."""
    from OCP.BRepLib import BRepLib
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    wrapped = _wrapped(result)
    if wrapped is None:
        return
    inputs: set = set()
    for shape in given:
        handle = _wrapped(shape)
        if handle is not None:
            edges = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(handle, TopAbs_EDGE, edges)
            find = edges.FindKey
            inputs.update(find(ordinal).TShape() for ordinal in range(1, edges.Extent() + 1))
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(wrapped, TopAbs_FACE, faces)
    for ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face_s(faces.FindKey(ordinal))
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge_s(explorer.Current())
            if edge.TShape() not in inputs:
                try:
                    BRepLib.BuildPCurveForEdgeOnPlane_s(edge, face)
                except Exception:  # noqa: BLE001 - an unwritten p-curve is projected when asked, as before
                    pass
            explorer.Next()


def _non_destructive(args: tuple, kwargs: dict) -> None:
    """Every boolean the layer sees runs non-destructive (``BOPAlgo_Options``):
    the kernel copies the sub-shapes it would change and shares the rest, so a
    boolean leaves its inputs as they were given, and what it leaves alone keeps
    its identity in the result (``kernel_trace``). Set before the call is keyed,
    so its key says what ran."""
    operation = args[3] if len(args) > 3 else kwargs.get("operation")
    if operation is not None:
        operation.SetNonDestructive(True)


def _helper(slot: str, function: Any) -> Any:
    """A constructor's kernel helper: hands back the TopoDS a constructor hit
    adopted, once, and otherwise builds as it always did."""
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        adopt = getattr(_LOCAL, "adopt", None)
        if adopt is not None and adopt[0] == slot:
            _LOCAL.adopt = None
            return adopt[1]
        return function(*args, **kwargs)

    wrapper.__kernel_memo__ = True
    return wrapper


# --- the run ------------------------------------------------------------------------------


class _Run:
    """One model run: its trace, call counts, native registrations and maker
    bindings, transient results, foreign inputs and nesting depth, and how its
    features went: hits, misses and calls that ran uncached (``tally``, what the
    build's time line reports)."""

    def __init__(self, script_path: Path | None) -> None:
        self.id = next(_RUN_IDS)
        self.trace = Trace(Path(script_path).resolve().parent if script_path is not None else None)
        self.counts: dict[int, int] = {}
        self.tally = {"hits": 0, "misses": 0, "uncached": 0, "bodies_run": 0, "bodies_skipped": 0}
        self.depth = 0
        self.transient: dict[Any, _Made] = {}
        # Foreign inputs walked once and found to embed no persistent root, by
        # TShape, with how many children each held then (``_capture``).
        self.foreign: dict[Any, int] = {}
        # Entry reuse and eviction belong to the shared memo. The registrations
        # and feature indices already observed by this run remain its own.
        self.registered: dict[Any, _Made] = {}
        self.owners: dict[_Made, int] = {}
        self.previous: _Run | None = getattr(_LOCAL, "run", None)
        # The model whose body is running (``scope``): its calls are counted, and keyed,
        # as its own.
        self.scope: str | None = None
        # The logs of the model bodies running, innermost last (``body``), and the bodies
        # this run has run or replayed: each is in the trace once.
        self.bodies: list[_BodyLog] = []
        self.done: set[str] = set()
        # Per body, the files it read itself (``_audited``): its inputs by their bytes, and
        # those that are no regular file, which keep it running.
        self.reads: dict[str, list[str]] = {}
        self.unread: dict[str, list[str]] = {}
        # Per body, each file it read past the engine's readers, by the call that read it
        # (``_bypassed``): what keeps it running.
        self.bypassed: dict[str, list[tuple[str, str | None]]] = {}
        # Per body, each call it ran uncached and how many times (``_ran_uncached``): what keeps
        # it from being retained.
        self.uncached: dict[str, dict[str, int]] = {}
        # Per body this run ran or replayed: what it is made of -- its source, its checks
        # (each file it read, held to its bytes), whether those say all it read, and the
        # bodies it called -- its key in a document (``build``); and how it went, ``run``
        # or ``replayed``.
        self.keys: dict[str, tuple[str, list, bool, list[str]]] = {}
        self.statuses: dict[str, str] = {}
        # Per body this run replayed, or ran and kept: its record, whose snapshot is the result
        # as the body returned it (``placement``).
        self.records: dict[str, _Body] = {}
        # The TShapes no operation made that a placement shares (``_note_placed``).
        self.placed: set = set()
        # Per file key and site, the read of this build that decoded it (``_read_again``).
        self.decoded: dict[tuple, _Entry] = {}
        # A verifying build (``body``): every body the memo would replay runs, and its fresh
        # result is compared with the logged one; per body, how that went.
        self.verify = False
        self.verified: dict[str, str] = {}
        self.marked: list[str] = []

    def scoped(self, key_id: int) -> int:
        """A call's key as the running model's own: two bodies making the same call are
        two entries, each counted in its body."""
        return key_id if self.scope is None else _intern(("scope", self.scope, key_id))

    def count(self, key_id: int) -> int:
        n = self.counts.get(key_id, 0) + 1
        self.counts[key_id] = n
        return n

    def made_by(self, tshape: Any) -> int | None:
        """The feature of this run that made ``tshape``, or None."""
        made = _made_of(tshape, self)
        if made is None:
            return None
        return self.owners.get(made.root())

    def feature_of(self, shape: Any) -> int | None:
        """The feature that made ``shape``: the one that returned the object, else
        the maker of its TShape, else that of the shape it was extracted from."""
        index = self.trace.feature_of(shape)
        if index is not None:
            return index
        wrapped = _wrapped(shape)
        if wrapped is not None:
            index = self.made_by(wrapped.TShape())
            if index is not None:
                return index
        parent = shape.__dict__.get("topo_parent") if hasattr(shape, "__dict__") else None
        return self.feature_of(parent) if parent is not None and parent is not shape else None

    def account(self, handle: Any) -> tuple[dict[str, Any] | None, dict[str, int]]:
        """The lineage of one part this run made (``trace.Trace.account``): its element
        names by ordinal, None when no feature of the run made it, and the feature of the
        run, by index, each feature name of the lineage stands for. ``handle`` is the
        part's ``TopoDS_Shape``; its location is not part of it."""
        from OCP.TopLoc import TopLoc_Location

        return self.trace.account(handle.Located(TopLoc_Location()), self.made_by, self.holder)

    def placement(self, name: str) -> Any:
        """A new placement of what body ``name`` returned in this run, as it returned it (its
        record's snapshot, ``_ShapeState.fresh``), leaving the objects it returned as the run
        holds them now; None for a body this run neither replayed nor ran and kept."""
        record = self.records.get(name)
        return None if record is None else record.snapshot.fresh()

    def holder(self, shape: Any) -> int | None:
        """The feature of this run whose result holds ``shape`` as a sub-shape (``_SUBS``,
        by its own TShape or its first face's): a part an assembly's copy holds, which no
        call returned itself."""
        from OCP.TopExp import TopExp_Explorer

        root = _SUBS.get(shape.TShape())
        if root is None:
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            if explorer.More():
                root = _SUBS.get(explorer.Current().TShape())
        return None if root is None or root.tainted else self.owners.get(root)


@contextlib.contextmanager
def scope(name: str) -> Iterator[None]:
    """Inside it, the calls of this thread's run are the model ``name``'s own: counted
    from its first, and keyed with its name. A child's body opens its own scope and the
    parent's resumes after it, so neither shifts the other's ordinals."""
    state = getattr(_LOCAL, "run", None)
    if state is None:
        yield
        return
    previous, saved = state.scope, state.counts
    state.scope, state.counts = name, {}
    try:
        yield
    finally:
        state.scope, state.counts = previous, saved


@contextlib.contextmanager
def run(script_path: Path | None = None, *, program: str | None = None, model: Any = None) -> Iterator[_Run]:
    """A model run on this thread: inside it every patched call from the
    model's code is a feature, and a hit when the memo has one. ``script_path``
    is the model's script, whose folder feature paths are relative to. The run's
    ``tally`` says how its calls went: hits, misses, calls that ran uncached.
    ``program`` names the calling program's run and ``model`` what this run builds: runs of
    one program building models it has not built in its pass count as one (``_mark``)."""
    install()
    state = _Run(script_path)
    previous = getattr(_LOCAL, "run", None)
    outermost = previous is None
    if outermost:
        _mark(program, model)
    _LOCAL.run = state
    try:
        yield state
    finally:
        _LOCAL.run = previous
        state.trace.release()
        if outermost:
            _sweep()


def _mark(program: str | None = None, model: Any = None) -> None:
    """A run begins: a marker at the end of both LRU orders. What the run hits, makes or
    keys moves behind it. A run of the program whose pass the last marker began, building a
    model that pass has not built, joins the pass: the marker stands, and what the run
    touches moves behind it, so the pass is one of the ``RUNS_KEPT`` however many models it
    builds."""
    with _LOCK:
        if program is not None and program == _PASS["program"] and model not in _PASS["models"] and _MARKS:
            _PASS["models"].add(model)
            return
        _PASS["program"], _PASS["models"] = program, {model}
    generation = next(_GENERATIONS)
    with _LOCK:
        _MEMO[(-generation, 0)] = None  # type: ignore[assignment]
        _KEY_IDS[("run", -generation)] = -generation
        _MARKS.append(generation)


def _sweep() -> None:
    """A run ended: forget every entry and key no run of the last ``RUNS_KEPT`` touched --
    all that lies in front of the oldest kept run's marker, the earlier markers with it."""
    with _LOCK:
        if len(_MARKS) <= RUNS_KEPT:
            return
        oldest = _MARKS[-RUNS_KEPT]
        del _MARKS[:-RUNS_KEPT]
        stop = (-oldest, 0)
        while _MEMO:
            key, entry = next(iter(_MEMO.items()))
            if key == stop:
                break
            _MEMO.popitem(last=False)
            if entry is not None:
                _drop(entry)
        for name in [name for name, body in _BODIES.items() if body.generation < oldest]:
            del _BODIES[name]
        stop_key = ("run", -oldest)
        while _KEY_IDS:
            key = next(iter(_KEY_IDS))
            if key == stop_key:
                break
            _KEY_IDS.popitem(last=False)


def stats() -> dict[str, int]:
    with _LOCK:
        return dict(_STATS, entries=len(_MEMO), registry=len(_REGISTRY))


def clear() -> None:
    """Forget every entry, so the next run computes everything."""
    with _LOCK:
        _MEMO.clear()
        _MARKS.clear()
        _PASS["program"], _PASS["models"] = None, set()
        _BODIES.clear()
        _ALWAYS.clear()
        _REGISTRY.clear()
        _LEDGER.clear()
        _KEY_IDS.clear()
        _MAPS.clear()
        _ORDINALS.clear()
        _BOXES.clear()
        _STATE.clear()
        _SUBS.clear()


# --- bodies -------------------------------------------------------------------------------


class _BodyLog:
    """What one run of a model body did, kept to replay it (**Bodies**): its events in
    order -- ``("call", entry, op, frame, inputs, results, labels, *objects, *handles,
    *results, *returned)`` for a call it hit or made (one flat tuple: a log holds tens of
    thousands, and the collector walks every container), ``("maker", entry, frame, op, *objects)`` for a maker
    it ran, ``("body", record)`` for a body it called -- the checks its bytes are held to (a
    callable and what it answered), the keys it interned and, apart, their ids, and whether
    it can be replayed."""

    __slots__ = ("events", "checks", "keys", "ids", "retainable", "reads", "unread", "keyed", "children", "bypassed",
                 "uncached")

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.checks: list[tuple[Callable[[], Any], Any]] = []
        self.keys: list[tuple] = []
        self.ids = array.array("q")
        self.retainable = True
        # Whether the body's key -- its source and its checks -- says all it read: false for
        # a body that read what has no bytes to hold (a pipe, a file that moved under it, a
        # file read past the engine's readers), or that called such a body. A body run plain
        # is still keyed: it is not kept to replay, but what it makes is a function of its
        # key (``Run.keys``).
        self.keyed = True
        # The bodies it called, run, replayed or placed again, in order.
        self.children: list[str] = []
        # The files the body read itself (``_audited``): each regular one with its stat when
        # opened (``None``: missing), and those that are no regular file.
        self.reads: dict[str, tuple | None] = {}
        self.unread: list[str] = []
        # The files it read past the engine's readers, each with the call (``_bypassed``).
        self.bypassed: list[tuple[str, str | None]] = []
        # The calls it ran uncached, each with how many times (``_ran_uncached``).
        self.uncached: dict[str, int] = {}


class _Body:
    """A model body's last run in this process: what its caller said it is made of, its
    log, its result as it returned it, and the last outermost run that used it; the
    TShapes of the shapes it was given (``inputs``, a ``@memo`` call's), and whether a call
    of it may be replayed (``direct``: false for a ``@memo`` function that returned no
    geometry, whose log is kept only for the bodies that called it)."""

    __slots__ = ("name", "source", "log", "snapshot", "generation", "inputs", "direct", "serial", "harvest")

    def __init__(self, name: str, source: str, log: _BodyLog, snapshot: Any, generation: int,
                 inputs: tuple = ()) -> None:
        self.name, self.source, self.log, self.snapshot, self.generation = name, source, log, snapshot, generation
        self.inputs, self.direct = inputs, True
        # Which run of the body this is, process-wide: a replay keeps it, a run makes another
        # (``adopt``: what the shapes its run made past the engine are keyed by).
        self.serial = next(_SERIALS)
        # A model body's harvest (``harvest_of``): what the build made of its result's joints,
        # sequences and animations, with the tree it was made of and the files the sequences'
        # functions read. A run of the body makes a record without one.
        self.harvest: tuple | None = None


# Per model body, by its caller's name for it: the body's last run, kept while one of the
# last ``RUNS_KEPT`` outermost runs used it (``_sweep``).
_BODIES: dict[str, _Body] = {}
_SERIALS = itertools.count(1)
# Per function a verifying build found impure (``body``'s ``family``): it runs on every
# call for the worker's life, and so do the bodies that call it. With why.
_ALWAYS: dict[str, str] = {}


def body(name: str, source: Callable[[], str], function: Callable[[], Any], *, inputs: tuple = (),
         family: str | None = None) -> Any:
    """Run a model body, or replay its last run (**Bodies**). ``name`` is the body's
    identity, ``source()`` a digest of the code it is made of (asked only when bodies are
    kept); the files it reads through the memo are held to their bytes here. Outside a
    run, or with hits off, it is called. ``inputs`` are the TShapes of the shapes a
    ``@memo`` call was given: a replay needs the very ones the logged run had. ``family``
    is the function's identity apart from its arguments: what a verification that finds
    it impure marks to run always (``_ALWAYS``).

    A verifying run (``_Run.verify``) runs a body it would replay and compares the fresh
    result's geometry with the logged one (``_geometry``): a body whose result differs is
    named in ``_Run.verified`` and its function marked."""
    state = getattr(_LOCAL, "run", None)
    if state is None or not enabled():
        return function()
    if os.environ.get("CADGEN_ENGINE_BODIES", "1").strip() == "0":
        # Bodies off: every body runs, its calls hit one by one, nothing is logged.
        try:
            return function()
        finally:
            _STATS["bodies_run"] += 1
            state.tally["bodies_run"] += 1
    source = source()
    family = name if family is None else family
    record = _BODIES.get(name)
    logged = None
    if (record is not None and record.source == source and record.direct and record.inputs == inputs
            and family not in _ALWAYS and _replayable(record)):
        if not state.verify:
            state.done.discard(name)
            result = _replay(record, state)
            if state.bodies:
                parent = state.bodies[-1]
                parent.events.append(("body", record))
                parent.checks.extend(record.log.checks)
                parent.children.append(name)
            return result
        logged = _logged_geometry(record.snapshot)
    marked = len(state.marked)
    log = _BodyLog()
    state.done.add(name)
    state.bodies.append(log)
    uncached, errors = state.tally["uncached"], _STATS["errors"]
    try:
        result = function()
    except BaseException:
        if len(state.bodies) > 1:
            state.bodies[-2].retainable = state.bodies[-2].keyed = False
        raise
    finally:
        state.bodies.pop()
    if log.reads:
        _hold_reads(log, state)
        state.reads[name] = list(log.reads)
    state.keys[name] = (source, list(log.checks), log.keyed, list(log.children))
    state.statuses[name] = "run"
    if log.unread:
        state.unread[name] = list(dict.fromkeys(log.unread))
    if log.bypassed:
        state.bypassed[name] = list(log.bypassed)
    if log.uncached:
        state.uncached[name] = dict(log.uncached)
    _STATS["bodies_run"] += 1
    state.tally["bodies_run"] += 1
    if logged is not None:
        differs = _differs(logged, _geometry(result))
        if not differs:
            state.verified[name] = "same"
        elif len(state.marked) > marked:
            # A body it called differed: that one is marked, and this one runs with it.
            state.verified[name] = "follows " + ", ".join(
                os.path.basename(script) + "::" + function
                for script, _, function in (found.rpartition("::") for found in state.marked[marked:]))
        else:
            state.verified[name] = "differs: " + differs
            _ALWAYS[family] = differs
            state.marked.append(family)
    snapshot = None
    if (log.retainable and state.tally["uncached"] == uncached and _STATS["errors"] == errors
            and family not in _ALWAYS):
        try:
            snapshot = _snapshot(result)
        except _Unkeyable:
            snapshot = None
    with _LOCK:
        if snapshot is None:
            _BODIES.pop(name, None)
            state.records.pop(name, None)
        else:
            _BODIES[name] = state.records[name] = _Body(name, source, log, snapshot, _MARKS[-1] if _MARKS else 0,
                                                        inputs)
    if state.bodies:
        parent = state.bodies[-1]
        # Its checks are the caller's too, kept or not: the caller's key says all it read.
        parent.checks.extend(log.checks)
        parent.children.append(name)
        if not log.keyed:
            parent.keyed = False
        if snapshot is None:
            parent.retainable = False
        else:
            parent.events.append(("body", _BODIES[name]))
    return result


def direct(name: str) -> None:
    """The body just run returned what a call of it cannot be replayed to (a ``@memo``
    function's result that is no geometry): its log stays, for the bodies that called it,
    but a call of it runs."""
    record = _BODIES.get(name)
    if record is not None:
        record.direct = False


def adopt(name: str, result: Any) -> Any:
    """A kept ``@memo`` call's result whose shapes its run made past the engine -- OCCT's own
    makers, which no key names -- as one operation of the caller's: keyed by the call (its
    name, which holds its arguments' digest) and by which run of it made them (``_Body.serial``),
    and registered, so what the caller makes of them is keyed and kept too. A replay of the call
    hands back those very shapes, and the operation is a hit; a run of it makes others, and a
    miss. A result any shape of which the memo made already, a call not kept, or none running:
    ``result`` as it is."""
    state = getattr(_LOCAL, "run", None)
    if state is None or state.depth or not enabled() or os.environ.get("CADGEN_ENGINE_BODIES", "1").strip() == "0":
        return result
    record = _BODIES.get(name)
    if record is None or not record.direct:
        return result
    Shape = _build123d().Shape
    shapes = list(result.values()) if isinstance(result, dict) else list(result) if isinstance(result, (list, tuple)) else [result]
    for shape in shapes:
        wrapped = _wrapped(shape) if isinstance(shape, Shape) else None
        if wrapped is None or _made_of(wrapped.TShape(), state) is not None or wrapped.TShape() in _SUBS:
            return result
    if isinstance(result, dict):
        names = list(result)
        made = _call(state, "memo", "function", lambda _name, _serial: [result[key] for key in names],
                     (name, record.serial), {})
        return dict(zip(names, made))
    return _call(state, "memo", "function", lambda _name, _serial: result, (name, record.serial), {})


def always() -> dict[str, str]:
    """The functions a verification found impure, each with why: they run on every call."""
    return dict(_ALWAYS)


# --- a model body's harvest -----------------------------------------------------------------


def harvest_of(state: _Run, name: str, tree: Any) -> tuple[Any, list] | None:
    """What the build made of model body ``name``'s result the last time (``keep_harvest``):
    the harvest and the checks of the files its sequences' functions read. Only when this run
    replayed the very run the harvest was made from (``_Body.serial``: a run makes another
    record), ``tree`` (the result's structure, as ``document.collect`` keys it) is the one it
    was made of, and every file those functions read has its bytes still. Else None: a run,
    a verifying run, a run with retention off, a file changed. ``state`` is the build's run,
    asked as its files are written, after it."""
    if (state.verify or not enabled() or state.statuses.get(name) != "replayed"
            or os.environ.get("CADGEN_ENGINE_BODIES", "1").strip() == "0"):
        return None
    record = _BODIES.get(name)
    if record is None or record.harvest is None or state.records.get(name) is not record:
        return None
    held_tree, harvest, checks = record.harvest
    if held_tree != tree:
        return None
    state.depth += 1
    try:
        for check, expected in checks:
            try:
                if check() != expected:
                    return None
            except _Unkeyable:
                return None
    finally:
        state.depth -= 1
    return harvest, checks


def keep_harvest(state: _Run, name: str, tree: Any, harvest: Any, checks: list, keyed: bool) -> None:
    """Keep the harvest of body ``name``'s result beside the body's run in this process
    (``harvest_of``), in memory only: gone with the record. Not kept where the sampled
    functions read what cannot be held to its bytes (``keyed``), or where this run's record of
    the body is not the one in the memo (a body not retained)."""
    if state.verify or not keyed or not enabled():
        return
    record = _BODIES.get(name)
    if record is None or state.records.get(name) is not record:
        return
    record.harvest = (tree, harvest, list(checks))


# --- the files a motion's function reads ---------------------------------------------------


class MotionReads:
    """The files the function motions of one model's document opened while they were sampled
    (``listened``), each held to its bytes as a body's reads are (``checks``), and whether they
    say all the functions read (``keyed``: false for a read of what is no regular file, past the
    engine's readers, or of a file that moved while it was read): inputs of the model's closure."""

    def __init__(self) -> None:
        self.checks: list[tuple[Callable[[], Any], Any]] = []
        self.keyed = True


@contextlib.contextmanager
def motion_reads() -> Iterator[MotionReads]:
    """Inside it, what this thread's harvest samples (``listened``) is heard into the one
    ``MotionReads`` it yields."""
    found = MotionReads()
    previous = getattr(_LOCAL, "motions", None)
    _LOCAL.motions = found
    try:
        yield found
    finally:
        _LOCAL.motions = previous


def listened(sample: Callable[[], list]) -> list:
    """A function motion's samples (``sample()``), the files its function opens heard while it
    is sampled (``_audited``) and held to their bytes in the ``motion_reads`` around it; outside
    one, or with retention off, just sampled."""
    held_by = getattr(_LOCAL, "motions", None)
    if held_by is None or not enabled() or os.environ.get("CADGEN_ENGINE_BODIES", "1").strip() == "0":
        return sample()
    log = _BodyLog()
    previous = getattr(_LOCAL, "sampling", None)
    _LOCAL.sampling = log
    try:
        keys = sample()
    finally:
        _LOCAL.sampling = previous
    if log.reads:
        _hold_reads(log, None)
    held_by.checks.extend(log.checks)
    if log.unread or log.bypassed or not log.retainable:
        held_by.keyed = False
    return keys


# --- a ``@memo`` call's arguments ------------------------------------------------------------

Unkeyable = _Unkeyable
# The most values a ``@memo`` call's arguments may hold, counted through its containers:
# past it the call is not keyed, and runs.
ARGUMENT_VALUES = 10_000
# build123d's value types, keyed by value (``_normalize``).
_VALUE_TYPES = frozenset({"Location", "Vector", "Axis", "Plane", "Color", "Rotation", "Pos", "Rot", "Matrix"})


def call_key(args: tuple, kwargs: dict) -> tuple[str, tuple]:
    """A ``@memo`` call's arguments as a digest, snapshotted now, and the TShapes of the
    shapes among them (what a replay must be given again). Plain values -- None, bools,
    numbers, strings, and tuples, lists and dicts of them -- by value, in order; an enum,
    a ``Path``; build123d's value types (``Location``, ``Vector``, ``Axis``, ``Plane``,
    ``Color``...) and a ``Material`` by value; a shape this process's operations made by
    its key (``_shape_key``). Anything else -- a callable, an arbitrary object, a shape
    made outside the memo, more than ``ARGUMENT_VALUES`` values -- raises ``Unkeyable``
    with why: the call runs."""
    state = getattr(_LOCAL, "run", None)
    if state is None:
        raise _Unkeyable("no build is running")
    budget = [ARGUMENT_VALUES]
    tshapes: list = []
    key = (tuple(_argument(value, state, budget, tshapes) for value in args),
           tuple((name, _argument(value, state, budget, tshapes)) for name, value in sorted(kwargs.items())))
    return hashlib.blake2b(repr(key).encode(), digest_size=10).hexdigest(), tuple(tshapes)


def _argument(value: Any, state: _Run, budget: list[int], tshapes: list) -> Any:
    budget[0] -= 1
    if budget[0] < 0:
        raise _Unkeyable(f"its arguments hold more than {ARGUMENT_VALUES} values")
    kind = type(value)
    if value is None or kind in (bool, int, float, str, bytes):
        return (kind.__name__, _normalize(value, state))
    if kind is tuple or kind is list:
        return (kind.__name__, tuple(_argument(item, state, budget, tshapes) for item in value))
    if kind is dict:
        return ("dict", tuple((_argument(name, state, budget, tshapes), _argument(item, state, budget, tshapes))
                              for name, item in value.items()))
    if isinstance(value, (enum.Enum, Path)):
        return _normalize(value, state)
    if isinstance(value, _build123d().Shape):
        try:
            found = _normalize(value, state)
        except _Unkeyable as error:
            raise _Unkeyable(f"a shape argument the memo cannot key ({error})") from None
        tshapes.extend(_wrapped(shape).TShape() for shape in _result_shapes(value) if _wrapped(shape) is not None)
        return found
    module = kind.__module__ or ""
    if (module.startswith("build123d") and kind.__name__ in _VALUE_TYPES) or (
            module == "cadgen.engine.materials" and kind.__name__ == "Material"):
        return _normalize(value, state)
    what = "a callable" if callable(value) else "an object"
    raise _Unkeyable(f"{what} argument ({module}.{kind.__qualname__}): not a value the memo keys")


def geometric(value: Any) -> bool:
    """Whether a result is geometry: a shape, or a tuple, list or dict whose leaves are."""
    if isinstance(value, _build123d().Shape):
        return True
    if isinstance(value, (list, tuple)):
        return all(geometric(item) for item in value)
    if isinstance(value, dict):
        return all(geometric(item) for item in value.values())
    return False


def _geometry(value: Any) -> Any:
    """What a verification compares of a result: per shape its class, label, colour, paints,
    material, placement and orientation, and its children or, for a leaf, its shape."""
    Shape = _build123d().Shape
    if isinstance(value, Shape):
        attrs = value.__dict__
        return _shape_geometry(type(value).__name__, attrs, attrs.get("_wrapped"),
                               [_geometry(child) for child in attrs.get("_NodeMixin__children") or ()])
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_geometry(item) for item in value))
    if isinstance(value, dict):
        return ("dict", tuple((repr(name), _geometry(item)) for name, item in value.items()))
    return ("value", repr(value))


def _logged_geometry(snapshot: Any) -> Any:
    """``_geometry`` of a body's logged result, read off its snapshot: restoring it would
    change live objects the fresh run is about to be handed (a child's result the body
    relabelled, moved or regrouped)."""
    if isinstance(snapshot, _ShapeState):
        return _shape_geometry(type(snapshot.obj).__name__, snapshot.attrs, snapshot.wrapped,
                               [_logged_geometry(child) for child in snapshot.children or ()])
    if isinstance(snapshot, _Sequence):
        return (snapshot.container.__name__, tuple(_logged_geometry(item) for item in snapshot.items))
    if isinstance(snapshot, _Mapping):
        return ("dict", tuple((repr(name), _logged_geometry(item)) for name, item in snapshot.items))
    return ("value", repr(snapshot.value))


def _shape_geometry(kind: str, attrs: dict, wrapped: Any, children: list) -> tuple:
    color = attrs.get("_color")
    head = (kind, attrs.get("label"), None if color is None else tuple(color),
            repr(sorted((attrs.get(FACE_COLORS) or {}).items())), repr(attrs.get("material")),
            repr(sorted(dict(attrs.get(FACE_MATERIALS) or {}).items())),
            None if wrapped is None else (_location_key(wrapped), int(wrapped.Orientation())))
    if children:
        return ("shape", head, tuple(children))
    from OCP.TopLoc import TopLoc_Location

    return ("shape", head, None if wrapped is None else _Leaf(wrapped.Located(TopLoc_Location())))


class _Leaf:
    """A leaf shape a verification compares: the same TShape is the same geometry; another
    the same binary BRep (``_brep``), else the same geometry in another order
    of the BRep's entries (``_measured``): OCCT's parallel booleans and a replayed body can
    write one shape's sub-shapes in another order, the faces, edges and vertices alike."""

    __slots__ = ("shape",)

    def __init__(self, shape: Any) -> None:
        self.shape = shape

    def same(self, other: "_Leaf") -> bool:
        if self.shape.TShape() == other.shape.TShape():
            return True
        return _brep(self.shape) == _brep(other.shape) or _measured(self.shape) == _measured(other.shape)


def _brep(shape: Any) -> bytes:
    """A shape's binary BRep as a document writes it (``document.unchecked``): one shape's
    bytes, compared with another's in this process, never a key."""
    import io

    from OCP.BinTools import BinTools, BinTools_FormatVersion_VERSION_4

    from cadgen.engine.document import unchecked

    stream = io.BytesIO()
    with unchecked([shape]):
        BinTools.Write_s(shape, stream, False, False, BinTools_FormatVersion_VERSION_4)
    return stream.getvalue()


def _measured(shape: Any) -> tuple:
    """A shape's geometry with no order: its solids, shells, faces, edges and vertices
    counted, and per face its area and centre, per edge its length and centre, per vertex its
    point, each rounded to 1e-6 and sorted. Two shapes alike but for the order of their BRep's
    entries measure alike; a value one unit in its last place apart may round apart, which
    reads as other geometry (the safe side)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    def each(kind: Any) -> list:
        found = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, kind, found)
        return [found.FindKey(index) for index in range(1, found.Size() + 1)]

    def rounded(*values: float) -> tuple:
        return tuple(round(value, 6) + 0.0 for value in values)

    def props(sub: Any, surface: bool) -> tuple:
        found = GProp_GProps()
        (BRepGProp.SurfaceProperties_s if surface else BRepGProp.LinearProperties_s)(sub, found)
        centre = found.CentreOfMass()
        return rounded(found.Mass(), centre.X(), centre.Y(), centre.Z())

    counts = tuple(len(each(kind)) for kind in (TopAbs_SOLID, TopAbs_SHELL))
    faces = sorted(props(face, True) for face in each(TopAbs_FACE))
    edges = sorted(props(edge, False) for edge in each(TopAbs_EDGE))
    points = sorted(rounded(*BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertex)).Coord()) for vertex in each(TopAbs_VERTEX))
    return counts, tuple(faces), tuple(edges), tuple(points)


def _differs(logged: Any, fresh: Any, where: str = "the result") -> str | None:
    """Where a fresh result's geometry (``_geometry``) is not the logged one's, or None."""
    if type(logged) is not type(fresh):
        return f"{where} is another kind of value"
    if isinstance(logged, _Leaf):
        return None if logged.same(fresh) else f"{where} has other geometry"
    if not isinstance(logged, tuple):
        return None if logged == fresh else f"{where} differs"
    if len(logged) != len(fresh):
        return f"{where} holds another number of items"
    if len(logged) == 3 and logged[0] == "shape":
        name = logged[1][1] or logged[1][0]
        if logged[1] != fresh[1]:
            return f"{where} ({name}) has another label, colour, material or placement"
        return _differs(logged[2], fresh[2], f"{where} > {name}")
    for a, b in zip(logged, fresh):
        found = _differs(a, b, where)
        if found:
            return found
    return None


def used(name: str) -> None:
    """A body is handed a result another body made earlier in this run (a child model
    called again): replaying it needs that body's run too, and its bytes count."""
    state = getattr(_LOCAL, "run", None)
    if state is None or not state.bodies:
        return
    record = _BODIES.get(name)
    parent = state.bodies[-1]
    parent.children.append(name)
    if record is None:
        parent.retainable = False
        known = state.keys.get(name)
        if known is None or not known[2]:
            parent.keyed = False
        else:
            parent.checks.extend(known[1])
    else:
        parent.events.append(("body", record))
        parent.checks.extend(record.log.checks)
        if record.log.reads:
            state.reads[name] = list(record.log.reads)


def replayable(name: str, source: str) -> bool:
    """Whether ``body(name, ...)``, its source ``source``, would replay the body's last run
    in this process rather than run it."""
    if not enabled() or os.environ.get("CADGEN_ENGINE_BODIES", "1").strip() == "0":
        return False
    record = _BODIES.get(name)
    return record is not None and record.source == source and _replayable(record)


def recipe(check: Callable[[], Any]) -> tuple | None:
    """What one of a body's checks reads, as a document can name it: ``("file", path)`` for
    a file read through the engine (``read_step``, the importers), ``("read", path)`` for
    one the body opened itself, ``("font", font, path, style)`` for a text's font; None
    for a check no document can name (bytes handed to an importer)."""
    if isinstance(check, _ReadInput):
        return ("read", check.path)
    if isinstance(check, functools.partial) and not check.keywords:
        if check.func is _file_key and len(check.args) == 1 and not isinstance(check.args[0], (bytes, bytearray)):
            return ("file", os.path.abspath(os.fspath(check.args[0])))
        if check.func is _font_key and len(check.args) == 3:
            font, path, style = check.args
            if font is not None and not isinstance(font, str):
                return None
            return ("font", font, None if path is None else os.path.abspath(os.fspath(path)),
                    None if style is None else style.name)
    return None


def recheck(found: tuple) -> Any:
    """What the check a recipe names (``recipe``) answers now -- a file's digest, or
    ``None`` for one gone (a body's own read) -- raising for one that cannot be read."""
    kind = found[0]
    if kind == "file":
        return _file_key(found[1])
    if kind == "read":
        return _ReadInput(found[1], None, None, None)()
    if kind == "font":
        style = None
        if found[3] is not None:
            from build123d import FontStyle

            style = FontStyle[found[3]]
        return _font_key(found[1], found[2], style)
    raise ValueError(f"no check reads {kind!r}")


def _replayable(record: _Body) -> bool:
    """Whether every entry the body's run hit or made is still the memo's, and every file
    it read still has the bytes it read."""
    pending = [record]
    with _LOCK:
        while pending:
            log = pending.pop().log
            for event in log.events:
                if event[0] == "body":
                    pending.append(event[1])
                elif _MEMO.get(event[1].key) is not event[1]:
                    return False
    # A check reads a file the body read through the engine, when its stat changed: the
    # engine's own read, never one of the running body's (``_audited``).
    state = getattr(_LOCAL, "run", None)
    if state is not None:
        state.depth += 1
    try:
        for check, expected in record.log.checks:
            try:
                if check() != expected:
                    return False
            except _Unkeyable:
                return False
    finally:
        if state is not None:
            state.depth -= 1
    return True


def keep(name: str) -> None:
    """Body ``name`` and every body it called count as used by this run, as a replay counts
    them, and are not replayed: their entries and keys move behind this run's marker and
    their records take its generation. A build that takes its model's document from memory
    (``build._previous``) so leaves the memo holding what an edit after it replays."""
    record = _BODIES.get(name)
    if record is None:
        return
    generation = _MARKS[-1] if _MARKS else 0
    pending, seen = [record], set()
    with _LOCK:
        while pending:
            current = pending.pop()
            if current.name in seen:
                continue
            seen.add(current.name)
            for event in current.log.events:
                if event[0] == "body":
                    pending.append(event[1])
                elif _MEMO.get(event[1].key) is event[1]:
                    _MEMO.move_to_end(event[1].key)
            for key, found in zip(current.log.keys, current.log.ids):
                _KEY_IDS[key] = found
                _KEY_IDS.move_to_end(key)
            if _BODIES.get(current.name) is current:
                current.generation = generation


def _replay(record: _Body, state: _Run) -> Any:
    """The body's last run, again, without its code: each entry bound to this run as a hit
    binds it and each feature recorded as it was; the result restored as it returned."""
    generation = _MARKS[-1] if _MARKS else 0
    for event in record.log.events:
        kind = event[0]
        if kind == "call":
            _, entry, op, frame, n_in, n_out, labels = event[:7]
            objects, handles = event[7:7 + n_in], event[7 + n_in:7 + n_in + n_out]
            results, returned = event[7 + n_in + n_out:7 + n_in + 2 * n_out], event[7 + n_in + 2 * n_out:]
            inputs = state.trace.given(objects, state.feature_of)
            _rebind(entry, state)
            inputs = [(shape, index, kept) for (shape, index, _handle), kept in zip(inputs, entry.handles)]
            feature = state.trace.record(op, frame, inputs, results, returned, labels=labels, result_handles=handles)
            feature.history = entry.history
            copied = _copy_origins(feature, state)
            entry.refresh(feature.index, state, copied)
            _decoded(state, entry)
        elif kind == "maker":
            entry, frame, op = event[1:4]
            inputs = state.trace.given(event[4:], state.feature_of) if op is not None else None
            _rebind(entry, state)
            feature = None
            if op is not None:
                inputs = [(shape, index, kept) for (shape, index, _handle), kept in zip(inputs, entry.handles)]
                feature = state.trace.record(op, frame, inputs, [], result_handles=[entry.snapshot.restore()])
                feature.history = entry.history
                _copy_origins(feature, state)
            entry.refresh(None if feature is None else feature.index, state, {})
        elif event[1].name not in state.done:
            _replay(event[1], state)
    with _LOCK:
        for key, found in zip(record.log.keys, record.log.ids):
            _KEY_IDS[key] = found
            _KEY_IDS.move_to_end(key)
    record.generation = generation
    state.records[record.name] = record
    state.done.add(record.name)
    state.keys[record.name] = (record.source, list(record.log.checks), record.log.keyed, list(record.log.children))
    state.statuses[record.name] = "replayed"
    if record.log.reads:
        state.reads[record.name] = list(record.log.reads)
    _STATS["bodies_skipped"] += 1
    state.tally["bodies_skipped"] += 1
    return record.snapshot.restore()


def _rebind(entry: "_Entry", state: _Run) -> None:
    """What a hit does to an entry's shapes: its makers back to the state its operation
    returned, its effects on its inputs applied again, its place in the memo's order."""
    _reset(entry.made, state.id)
    for index, effect in entry.effects:
        made = _made_of(entry.inputs[index], state)
        effect.apply(state.id, None if made is None else made.root())
        if made is not None:
            made.effects.append(effect)
    for made in entry.made:
        made.born = next(_SEQUENCE)
    with _LOCK:
        _MEMO.move_to_end(entry.key)


def _log_call(state: _Run, entry: "_Entry", op: str, frame: tuple, inputs: list, feature: Any,
              results: list, returned: list) -> None:
    objects = [shape for shape, _index, _handle in inputs]
    labels = [getattr(shape, "__dict__", {}).get("label") for shape in objects]
    state.bodies[-1].events.append(("call", entry, op, frame, len(objects), len(feature.results), tuple(labels),
                                    *objects, *feature.results, *results, *returned))


# --- the call -----------------------------------------------------------------------------


def _call(state: _Run, label: str, kind: str, function: Any, args: tuple, kwargs: dict) -> Any:
    if kind == "constructor" and not _constructs(label, args, kwargs):
        return function(*args, **kwargs)
    frame = state.trace.frame()
    if frame is None:
        return function(*args, **kwargs)
    state.depth += 1
    try:
        op = _op_name(label, kind, args, kwargs)
        shapes = _shape_args(_key_args(label, kind, args), kwargs)
        # The memo is an optimization and never the reason a build fails: a key,
        # a capture or a snapshot that cannot be taken makes the call run plain,
        # counted under errors, and the call is still a feature. With the memo
        # off a call is keyed as ever and never hits: identity is the same either way.
        key_id = None
        try:
            key_id = _intern(_build_key(label, kind, function, args, kwargs, state))
        except _Unkeyable:
            _STATS["unkeyable"] += 1
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
        if key_id is None:
            return _plain(state, op, frame, kind, shapes, function, args, kwargs, capture=True)
        inputs = state.trace.given(shapes, state.feature_of)
        raw, key_id = key_id, state.scoped(key_id)
        n = state.count(key_id)
        entry = None
        if enabled():
            with _LOCK:
                entry = _MEMO.get((key_id, n))
                if entry is not None and entry.matches(shapes) and not _orphaned(entry, label, state):
                    _MEMO.move_to_end((key_id, n))
                else:
                    entry = None
        # A file read: decoded once a build per statement that reads it (``_read_again``).
        read = (raw, _site(frame)) if label in _FILE_OPS else None
        if read is not None:
            if entry is None:
                function = _read_again(state, read, function)
            else:
                _decoded(state, entry)
        if entry is not None:
            result = _hit(state, entry, kind, function, args, kwargs, shapes)
            # The hit's feature is the miss's: its results are the objects the miss made,
            # so its inputs are the handles the miss was given -- the same TShapes at the
            # same placements (the key says so), holding the locations those results were
            # built from. A handle taken now would hold a location the model made again
            # this run, equal in value and another object, which the kernel's ``IsSame``
            # (a location is its datum) would not find among the results' elements.
            inputs = [(shape, index, kept) for (shape, index, _handle), kept in zip(inputs, entry.handles)]
            results, returned = _result_shapes(result), _returned_shapes(result)
            feature = state.trace.record(op, frame, inputs, results, returned)
            # The very shapes the miss made, so the history it captured is theirs: no maker runs.
            feature.history = entry.history
            copied = _copy_origins(feature, state)
            entry.refresh(feature.index, state, copied)
            _STATS["hits"] += 1
            state.tally["hits"] += 1
            if state.bodies:
                _log_call(state, entry, op, frame, inputs, feature, results, returned)
            return None if kind == "constructor" else result
        try:
            captured = _capture(shapes, top=_composes(label, kind))
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            return _plain(state, op, frame, kind, shapes, function, args, kwargs, capture=False)
        # The inputs as given, before the call: an in-place operation (clean)
        # leaves its input wrapping the result's TShape.
        given = [_wrapped(shape).TShape() for shape in shapes]
        with kernel_history.recording() as makers:
            function_result = function(*args, **kwargs)
        result = args[0] if kind == "constructor" else function_result
        _STATS["misses"] += 1
        state.tally["misses"] += 1
        results, returned = _result_shapes(result), _returned_shapes(result)
        feature = state.trace.record(op, frame, inputs, results, returned)
        feature.history = _history(feature, makers)
        copied = _copy_origins(feature, state)
        del makers
        snapshot = None
        try:
            effects, sound = _effects(captured, state)
            if not sound or any(effect.geometric() for _index, effect in effects):
                # A source changed within this outer call. Its pre-call state
                # cannot certify whether a nested copy preceded that change.
                copied = _reject_copies(feature, copied, state)
            if sound:
                if kind == "constructor":
                    snapshot = _Adopt(_wrapped(result), dict(_CONSTRUCTOR_TARGETS)[label])
                else:
                    snapshot = _snapshot(result)
        except _Unkeyable:
            snapshot = None
            copied = _reject_copies(feature, copied, state)
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            snapshot = None
            copied = _reject_copies(feature, copied, state)
            for item in captured:
                _taint(_made_of(item.handle.TShape(), state), state)
        if snapshot is None:
            _register(result, None, feature.index, state, None, copied)
            if state.bodies:
                state.bodies[-1].retainable = False  # nothing kept to replay
            return function_result
        for index, effect in effects:
            effect.origin = (key_id, n, index)
        entry = _Entry(key=(key_id, n), inputs=given, snapshot=snapshot, effects=effects,
                       history=feature.history, in_place=kind != "constructor" and bool(args) and result is args[0],
                       handles=feature.handles)
        _replace(entry.key)
        entry.made = _register(result, entry.key, feature.index, state, entry, copied)
        entry.read = read
        _keep(entry)
        _decoded(state, entry)
        if state.bodies:
            _log_call(state, entry, op, frame, inputs, feature, results, returned)
        return function_result
    finally:
        state.depth -= 1


def _site(frame: tuple) -> tuple:
    """What names a call's feature, of the frame it is made from (``Trace.frame``): its
    statement (file, line, function), the targets it assigns -- not which execution -- and
    the caller whose assignment names it. Two calls from one site are named alike."""
    assignment = frame[3] if len(frame) > 3 else None
    return (*frame[:3], None if assignment is None else tuple(assignment[1]), frame[4] if len(frame) > 4 else None)


def _decoded(state: _Run, entry: "_Entry") -> None:
    """A read this build decoded, or hit, or replayed: what a later read of the same
    file from the same site shares (``_read_again``)."""
    if entry.read is not None and entry.made:
        state.decoded.setdefault(entry.read, entry)


def _read_again(state: _Run, read: tuple, function: Any) -> Any:
    """A file read again in one build -- the same bytes (its key is their digest), with
    the same arguments, from the same site (``_site``), by any model body: a helper
    reading one screw for each place it goes -- as ``function`` would read it, but
    decoded once: that first read's result again, as new objects on the same TShapes
    (``_ShapeState.fresh``), so the reads are one B-rep placed again and again, and
    their elements are named alike, as their prototype's. A read from another site is
    another feature, named apart (**names are the durable tie to code**), so it is
    decoded apart: one B-rep cannot carry two names. ``function`` itself where no read of
    the build from that site kept anything to share."""
    first = state.decoded.get(read)
    with _LOCK:
        if first is None or _MEMO.get(first.key) is not first or not first.made:
            return function

    def again(*_args: Any, **_kwargs: Any) -> Any:
        _STATS["shared_reads"] += 1
        return first.snapshot.fresh()

    return again


def _orphaned(entry: "_Entry", label: str, state: _Run) -> bool:
    """Whether an entry of a read that shared another's B-rep (``_read_again``) lost it: the
    read that decoded it is gone from the memo, and with it the registration that keys
    what is made of it. It reads again."""
    if label not in _FILE_OPS or entry.made:
        return False
    snapshot = entry.snapshot
    while isinstance(snapshot, _Sequence):
        if not snapshot.items:
            return False
        snapshot = snapshot.items[0]
    return isinstance(snapshot, _ShapeState) and _made_of(snapshot.wrapped.TShape(), state) is None


def _replace(key: tuple[int, int]) -> None:
    """Drop the key's earlier entry: it was made from inputs this run no longer has
    (or with hits off, by an earlier run)."""
    with _LOCK:
        replaced = _MEMO.pop(key, None)
        if replaced is not None:
            _drop(replaced)


def _keep(entry: "_Entry") -> None:
    """Into the memo as its newest entry, the oldest past ``CAPACITY`` dropped."""
    with _LOCK:
        _MEMO[entry.key] = entry
        _MEMO.move_to_end(entry.key)
        while len(_MEMO) > CAPACITY:
            _old_key, old = _MEMO.popitem(last=False)
            if old is not None:
                _drop(old)


def _ran_uncached(state: _Run, call: str) -> None:
    """A call ran with no key (``_plain``, a maker no key names): counted, and named in the
    running body's log, so its build says what keeps the body from being retained."""
    state.tally["uncached"] += 1
    if state.bodies:
        found = state.bodies[-1].uncached
        found[call] = found.get(call, 0) + 1


def _plain(state: _Run, op: str, frame: tuple, kind: str, shapes: list, function: Any, args: tuple,
           kwargs: dict, *, capture: bool) -> Any:
    """Run the call as plain build123d. It is still a feature, its results are
    this run's (so a later feature can name them as inputs), and what it does
    to a memoized shape is still accounted for."""
    _ran_uncached(state, f"build123d's {getattr(function, '__qualname__', None) or op}")
    if state.bodies:
        state.bodies[-1].retainable = False
    inputs = state.trace.given(shapes, state.feature_of)
    verified = capture
    try:
        top = _composes(op, kind)
        captured = _capture(shapes, embedded=True, top=top) if capture else []
    except Exception:  # noqa: BLE001
        _STATS["errors"] += 1
        captured = []
        verified = False
    with kernel_history.recording() as makers:
        function_result = function(*args, **kwargs)
    result = args[0] if kind == "constructor" else function_result
    feature = state.trace.record(op, frame, inputs, _result_shapes(result), _returned_shapes(result))
    feature.history = _history(feature, makers)
    copied = _copy_origins(feature, state)
    if not verified:
        copied = _reject_copies(feature, copied, state)
    del makers
    if captured:
        try:
            effects, sound = _effects(captured, state)
            if not sound or any(effect.geometric() for _index, effect in effects):
                copied = _reject_copies(feature, copied, state)
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            copied = _reject_copies(feature, copied, state)
    _register(result, None, feature.index, state, None, copied)
    return function_result


def _history(feature: Any, makers: list) -> "kernel_history.History | None":
    """What the makers the call ran report of its results (``kernel_history``), or None
    where it cannot be composed: the feature is then named without it, never failed."""
    try:
        history = kernel_history.compose(feature.handles, feature.results, makers)
    except Exception:  # noqa: BLE001
        kernel_history._STATS["errors"] += 1
        return None
    return history


def _copy_origins(feature: Any, state: _Run) -> dict[int, Any]:
    """Bind certified whole-body copies to their source's naming context before another
    operation can change it (``trace.Trace.preserve_copies``): by position, ``_COPIED``
    for a copy whose source this process made, None for one it did not. A copied
    descendant of an uncached assembly placement stays transient and can never make
    that operation a memo hit."""
    copies = feature.history.copies if feature.history is not None else {}
    if not copies:
        return {}
    try:
        state.trace.preserve_copies(feature, copies, state.made_by)
    except Exception:  # noqa: BLE001 - naming cannot make geometry fail
        _STATS["errors"] += 1
        return _reject_copies(feature, {position: None for position in copies}, state)
    return {position: None if _made_of(copy.source.TShape(), state) is None else _COPIED
            for position, copy in copies.items()}






def _reject_copies(feature: Any, copied: dict[int, Any], state: _Run) -> dict[int, None]:
    """Withdraw both kinds of inheritance, including what a later hit could use."""
    if not copied:
        return {}
    state.trace.reject_copies(feature)
    return {position: None for position in copied}


def _hit(state: _Run, entry: "_Entry", kind: str, function: Any, args: tuple, kwargs: dict, shapes: list) -> Any:
    if kind == "constructor":
        from build123d.topology.shape_core import downcast

        adopted = entry.snapshot.restore()
        _LOCAL.adopt = (entry.snapshot.slot, adopted)
        try:
            function(*args, **kwargs)
        finally:
            _LOCAL.adopt = None
        result = args[0]
        result.__dict__["_wrapped"] = downcast(adopted.Located(adopted.Location()))
    elif entry.in_place and shapes[0] is not entry.snapshot.obj:
        from build123d.topology.shape_core import downcast

        result = shapes[0]
        wrapped = entry.snapshot.wrapped
        result.__dict__["_wrapped"] = downcast(wrapped.Located(wrapped.Location()))
    else:
        result = entry.snapshot.restore()
    _reset(entry.made, state.id)
    for index, effect in entry.effects:
        # On the input as given, where the miss noted it: an in-place operation's hit has
        # just made the input object wrap the result.
        made = _made_of(entry.inputs[index], state)
        effect.apply(state.id, None if made is None else made.root())
        if made is not None:
            made.effects.append(effect)
    for made in entry.made:
        made.born = next(_SEQUENCE)
    return result














def _decoding(decode: Callable[[], Any], state: _Run) -> Any:
    """``decode()``, its own kernel calls cadgen's: none is a feature or an entry."""
    state.depth += 1
    try:
        return decode()
    finally:
        state.depth -= 1






def _composes(label: str, kind: str) -> bool:
    """Whether a call makes a container of the shapes it is given and changes nothing of
    one but its own ``Free`` flag: a compound's constructor."""
    return kind == "constructor" and label == "Compound"


def wrap_function(label: str, function: Callable[..., Any]) -> Callable[..., Any]:
    """``function`` as one operation of the memo: inside a model's run, a call from the
    model's code is a feature, keyed by its arguments -- a file argument of a ``_FILE_OPS``
    label by the file's bytes -- and a hit hands back the objects the first call made.
    Outside a run it only calls."""
    install()
    return _wrap(label, function, "function")


# --- makers a model runs itself ----------------------------------------------------------------
#
# A model that reaches past build123d for an OCCT maker (``_MAKER_TARGETS``) is handed this
# layer's subclass of it once the layer is installed (build123d keeps the classes it
# imported). One constructed from a model's code inside a run is one operation, as a
# build123d call is: keyed by its class, its constructor's arguments and the setters called
# on it before it runs, in order -- a shape it is given by the key of the operation that
# made its TShape, an edge or a face by its kind and index in the maker's own shape -- and
# what it made is registered as that operation's result, so what the model makes of it is
# keyed too. A hit runs nothing: ``Shape()`` hands back the TShape the earlier run's maker
# made, the effects that run had on its input are replayed, and every other method answers
# from that earlier maker, which made it. A call its key cannot name -- another method
# before it runs, an argument no key names, a shape no operation made -- makes it run plain,
# as does a run that is not the model's; once it ran, a setter is OCCT's own on it, and
# running it again runs OCCT's own, forgetting what its own run kept. A maker's run is one
# of the model's calls: its hit, its miss or its plain run is counted as a build123d call's
# is (``stats``, ``_Run.tally``). It is a feature too (``_MAKER_FEATURES``), so a
# shape a model places, copies or fixes past build123d keeps its names: given
# the shapes it was handed, named from what it reports (``Modified``), its hit's from what
# its miss reported, and where it reported nothing, from the shape it was given by
# ordinal when the two map one-to-one (``kernel_history.by_ordinal``).


# The makers that change the shape they are given in place: ``ShapeFix_Shape`` fixes the
# sub-shapes it is handed (their tolerances, p-curves, flags). Given a shape a placement
# shares (``_sharing``), it is given a copy of it instead (``_unshared``), so it never
# changes the shape's other placements. The others build what they make anew: a transform,
# a copy, a fillet, and a unify in its safe input mode, on unless a model turns it off.
_IN_PLACE = frozenset({"ShapeFix_Shape"})


def _unshared(args: tuple) -> tuple:
    """A maker's arguments with each shape a placement shares (``_is_placed``) replaced by
    a copy of it -- the layer's own ``BRepBuilderAPI_Copy``, so the copy is a feature of
    the model's run, keyed and named as the shape it copies -- outside a model's run, or
    for a shape no placement shares, the arguments as given. Counted (``copied_on_write``)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopoDS import TopoDS_Shape

    state = getattr(_LOCAL, "run", None)
    if state is None or state.depth or not any(isinstance(value, TopoDS_Shape) for value in args):
        return args
    given = []
    for value in args:
        if isinstance(value, TopoDS_Shape) and not value.IsNull() and _is_placed(value, state):
            value = BRepBuilderAPI_Copy(value).Shape()
            _STATS["copied_on_write"] += 1
        given.append(value)
    return tuple(given)


def _maker_class(cls: type, perform: str | None, idle: tuple[int, ...], builds: bool,
                 setters: tuple[str, ...]) -> type:
    """``cls`` as a model's code meets it: a subclass whose instances are ``cls``'s own
    outside a model's run, and one operation inside it (``_Maker``)."""
    own = frozenset((*setters, perform, "Shape"))

    def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
        if cls.__name__ in _IN_PLACE:
            args = _unshared(args)
        maker = _Maker.open(cls, args, kwargs)
        self.__dict__["_kernel_maker"] = maker
        if maker is not None and perform is None:
            maker.run(self, lambda: cls.__init__(self, *args),
                      idle=lambda: cls.__init__(self, *(args[i] for i in idle)))
        else:
            cls.__init__(self, *args, **kwargs)

    def running(self: Any, *args: Any, **kwargs: Any) -> Any:
        maker = self.__dict__.get("_kernel_maker")
        if maker is None:
            return getattr(cls, perform)(self, *args, **kwargs)
        if args or kwargs:
            maker.refuse()
        return maker.run(self, lambda: getattr(cls, perform)(self, *args, **kwargs))

    def Shape(self: Any) -> Any:  # noqa: N802 - OCCT's name
        maker = self.__dict__.get("_kernel_maker")
        if maker is not None:
            if maker.pending and builds and perform is not None:
                getattr(self, perform)()
            if maker.served is not None:
                return maker.served.restore()
        return cls.Shape(self)

    def setter(name: str) -> Any:
        def call(self: Any, *args: Any, **kwargs: Any) -> Any:
            maker = self.__dict__.get("_kernel_maker")
            if maker is not None:
                maker.note(name, args, kwargs)
            return getattr(cls, name)(self, *args, **kwargs)

        call.__name__ = name
        return call

    def __getattribute__(self: Any, name: str) -> Any:
        if name not in own and not name.startswith("_"):
            maker = object.__getattribute__(self, "__dict__").get("_kernel_maker")
            if maker is not None:
                if maker.served is not None:
                    return getattr(maker.served.maker, name)
                maker.refuse()
        return object.__getattribute__(self, name)

    namespace: dict[str, Any] = {name: setter(name) for name in setters if hasattr(cls, name)}
    namespace.update(__init__=__init__, Shape=Shape, __getattribute__=__getattribute__, __kernel_memo__=True,
                     __kernel_memo_class__=cls, __doc__=cls.__doc__, __module__=cls.__module__,
                     __qualname__=cls.__qualname__)
    if perform is not None:
        namespace[perform] = running
    return type(cls.__name__, (cls,), namespace)


class _Maker:
    """One maker a model's code constructed inside a run: its class, its constructor's
    arguments and the setters called on it while it has not run; once it ran, the entry
    its run is (a miss's or a hit's) and, on a hit, the earlier run that serves it."""

    __slots__ = ("cls", "args", "calls", "state", "pending", "plain", "served", "entry", "frame", "op")

    def __init__(self, cls: type, args: tuple, state: "_Run | None", frame: tuple | None = None) -> None:
        self.cls = cls
        self.args = args
        self.calls: list[tuple[str, tuple]] = []
        self.state = state
        self.pending = True
        self.plain = False
        self.served: _MakerRun | None = None
        self.entry: _Entry | None = None
        # Where the model constructed it, and the operation it is as a feature (None for a
        # maker whose run is no feature).
        self.frame = frame
        self.op = _MAKER_FEATURES.get(cls.__name__)

    @staticmethod
    def open(cls: type, args: tuple, kwargs: dict) -> "_Maker | None":
        """A maker to key, or None: not a model's run, or constructed by name."""
        state = getattr(_LOCAL, "run", None)
        if state is None or state.depth or kwargs:
            return None
        frame = state.trace.frame()
        if frame is None:
            return None
        return _Maker(cls, args, state, frame)

    def refuse(self) -> None:
        """A call no key names before the maker ran: it runs plain."""
        self.plain = self.plain or self.pending

    def note(self, name: str, args: tuple, kwargs: dict) -> None:
        """A setter called: named by the key while the maker has not run; once it ran, OCCT's
        own on this maker, as its next run is."""
        if self.pending:
            self.plain = self.plain or bool(kwargs)
            self.calls.append((name, args))

    def forget(self) -> None:
        """It runs again, on itself: what served it serves no more, and an entry its own run
        kept holds a maker no longer as that run left it."""
        entry, served = self.entry, self.served
        self.entry = self.served = None
        if entry is not None and served is None:
            with _LOCK:
                if _MEMO.get(entry.key) is entry:
                    _MEMO.pop(entry.key)
                    _drop(entry)

    def run(self, instance: Any, real: Callable[[], Any], idle: Callable[[], Any] | None = None) -> Any:
        """The maker's run: a hit, or ``real()`` keyed and kept; ``idle()`` constructs one
        that has not run, for a hit where the constructor runs it."""
        if not self.pending:
            self.forget()
            return real()
        state = self.state
        key_id = None
        own = getattr(_LOCAL, "run", None) is state and not state.depth
        if not self.plain and own:
            try:
                key_id, inputs = self.key()
            except _Unkeyable:
                pass
            except Exception:  # noqa: BLE001
                _STATS["errors"] += 1
        from OCP.TopoDS import TopoDS_Shape

        shapes = [_Given(value) for value in self.args if isinstance(value, TopoDS_Shape)] if own else []
        # Run once: a maker an entry keeps holds no run, argument or call of its own.
        self.pending, self.state, self.args, self.calls = False, None, (), []
        # A feature's inputs as it is given them, taken before it runs (``Trace.given``).
        given = state.trace.given(shapes, state.feature_of) if own and self.op is not None else None
        if key_id is None:
            if not own:
                return real()
            _ran_uncached(state, f"OCCT's {self.cls.__name__}")
            if given is None:
                return real()
            # It runs plain, and is still a feature: what it made is this run's, named.
            with kernel_history.recording() as makers:
                answer = _decoding(real, state)
                result = self._result(instance)
            if result is not None:
                feature = self._feature(state, given, result, makers=makers)
                tshape = result.TShape()
                if _made_of(tshape, state) is None:
                    made = _Made(tshape, key=None, entry=None)
                    with _LOCK:
                        state.transient[tshape] = made
                        state.owners[made] = feature.index
            if state.bodies:
                state.bodies[-1].retainable = False
            return answer
        key_id = state.scoped(key_id)
        n = state.count(key_id)
        entry = None
        if enabled():
            with _LOCK:
                entry = _MEMO.get((key_id, n))
                if entry is not None and type(entry.snapshot) is _MakerRun and entry.matches(inputs):
                    _MEMO.move_to_end((key_id, n))
                else:
                    entry = None
        if entry is not None:
            if idle is not None:
                idle()
            _reset(entry.made, state.id)
            for index, effect in entry.effects:
                made = _made_of(_wrapped(inputs[index]).TShape(), state)
                effect.apply(state.id, None if made is None else made.root())
                if made is not None:
                    made.effects.append(effect)
            for made in entry.made:
                made.born = next(_SEQUENCE)
            feature = None
            if given is not None:
                # The miss's feature again: its inputs the handles the miss was given.
                given = [(shape, index, kept) for (shape, index, _handle), kept in zip(given, entry.handles)]
                feature = self._feature(state, given, entry.snapshot.wrapped, history=entry.history)
            entry.refresh(None if feature is None else feature.index, state, {})
            self.served, self.entry = entry.snapshot, entry
            _STATS["hits"] += 1
            state.tally["hits"] += 1
            if state.bodies:
                state.bodies[-1].events.append(("maker", entry, self.frame, self.op,
                                                *(shape for shape, _index, _handle in given or ())))
            return entry.snapshot.answer
        _STATS["misses"] += 1
        state.tally["misses"] += 1
        try:
            captured = _capture(inputs)
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            if state.bodies:
                state.bodies[-1].retainable = False
            return real()
        tshapes = [_wrapped(item).TShape() for item in inputs]
        with kernel_history.recording() as makers:
            answer = _decoding(real, state)
            result = self._result(instance)
        feature = None
        if given is not None and result is not None:
            feature = self._feature(state, given, result, makers=makers)
        del makers
        try:
            effects, sound = _effects(captured, state)
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            for item in captured:
                _taint(_made_of(item.handle.TShape(), state), state)
            if state.bodies:
                state.bodies[-1].retainable = False
            return answer
        if not sound or result is None:
            if state.bodies:
                state.bodies[-1].retainable = False
            return answer
        for index, effect in effects:
            effect.origin = (key_id, n, index)
        entry = _Entry(key=(key_id, n), inputs=tshapes, snapshot=_MakerRun(result, answer, instance), effects=effects,
                       history=None if feature is None else feature.history,
                       handles=() if feature is None else feature.handles)
        _replace(entry.key)
        entry.made = _register_handle(result, entry.key, state, entry)
        if feature is not None:
            for made in entry.made:
                state.owners[made] = feature.index
        _keep(entry)
        self.entry = entry
        if state.bodies:
            state.bodies[-1].events.append(("maker", entry, self.frame, self.op,
                                            *(shape for shape, _index, _handle in given or ())))
        return answer

    def _result(self, instance: Any) -> Any:
        """What the maker made, as it hands it back (``Shape``), or None for nothing."""
        try:
            result = self.cls.Shape(instance)
        except Exception:  # noqa: BLE001 - it made nothing: nothing to keep
            return None
        return None if result is None or result.IsNull() else result

    def _feature(self, state: _Run, given: list, result: Any, *, makers: list | None = None,
                 history: Any = None) -> Any:
        """The maker's run as a feature of the run: the shapes it was given and what it
        made, named from what it reports (``makers``, composed) or reported (``history``,
        a hit's), as a build123d call's is."""
        feature = state.trace.record(self.op, self.frame, given, [], result_handles=[result.Located(result.Location())])
        if makers is not None:
            history = _history(feature, makers)
            if (history is None or not history.origins) and len(feature.handles) == 1 and feature.handles[0] is not None:
                # It reported nothing: what maps one-to-one onto what it was given is that.
                try:
                    history = kernel_history.by_ordinal(feature.handles[0], feature.results[0],
                                                        "I" if self.op == "copy" else "M") or history
                except Exception:  # noqa: BLE001 - naming cannot make geometry fail
                    _STATS["errors"] += 1
        feature.history = history
        _copy_origins(feature, state)
        return feature

    def key(self) -> tuple[int, list]:
        """The maker's key, as an operation's: its class, the constructor's arguments and
        the setters called, in order; and the shapes it was given, as inputs."""
        from OCP.TopoDS import TopoDS_Shape

        state = self.state
        base = next((value for value in self.args if isinstance(value, TopoDS_Shape)), None)
        inputs = [_Given(value) for value in self.args if isinstance(value, TopoDS_Shape)]
        parts = tuple(_maker_value(value, state, None) for value in self.args)
        calls = tuple((name, tuple(_maker_value(value, state, base) for value in args)) for name, args in self.calls)
        return _intern((self.cls.__name__, (parts, calls), (), ())), inputs


class _Given:
    """A ``TopoDS_Shape`` a maker was given, read as a shape input is: by ``_wrapped``."""

    def __init__(self, handle: Any) -> None:
        self.__dict__["_wrapped"] = handle


class _MakerRun:
    """A maker's run as its entry keeps it: what it made, what running it answered, and the
    maker, which answers whatever else a later run asks of the one it serves."""

    __slots__ = ("wrapped", "answer", "maker")

    def __init__(self, wrapped: Any, answer: Any, maker: Any) -> None:
        self.wrapped = wrapped.Located(wrapped.Location())
        self.answer = answer
        self.maker = maker

    def restore(self) -> Any:
        return self.wrapped.Located(self.wrapped.Location())


def _maker_value(value: Any, state: _Run, base: Any) -> Any:
    """One argument a maker was given, as a key part: a shape by :func:`_raw_key`, a
    transformation by its matrix, an OCCT enumeration by its value."""
    from OCP.TopoDS import TopoDS_Shape
    from OCP.gp import gp_GTrsf, gp_Trsf

    if isinstance(value, TopoDS_Shape):
        return ("shape", _raw_key(value, state, base))
    if isinstance(value, (gp_Trsf, gp_GTrsf)):
        return ("trsf" if isinstance(value, gp_Trsf) else "gtrsf",
                tuple(("n", _DOUBLE.pack(value.Value(row, column))) for row in (1, 2, 3) for column in (1, 2, 3, 4)))
    if value is None or isinstance(value, (bool, str, numbers.Real)):
        return _normalize(value, state)
    if hasattr(type(value), "__members__") and (type(value).__module__ or "").startswith("OCP"):
        return ("enum", type(value).__name__, int(value))
    raise _Unkeyable(f"unkeyable maker argument: {type(value).__name__}")


def _raw_key(handle: Any, state: _Run, base: Any) -> int:
    """The interned key of a ``TopoDS_Shape`` a maker was given, as a shape input's
    (:func:`_shape_key`) with no attributes: a TShape a memoized operation made, by that
    operation's key, or else a sub-shape of the maker's own shape ``base``, by its kind and
    index there; with its location and orientation."""
    if handle.IsNull():
        raise _Unkeyable("an empty shape")
    made = _made_of(handle.TShape(), state)
    if made is None and _SUBS.get(handle.TShape()) is not None and (base is None or handle is base):
        made = _held(handle.TShape(), int(handle.ShapeType()), state)
    if made is not None and (made.parent is None or made.held):
        head = made.base(None, state)
    elif base is not None and handle is not base:
        kind = int(handle.ShapeType())
        index = _sub_map(base, kind).FindIndex(handle)
        if index == 0:
            raise _Unkeyable("not a sub-shape of the maker's shape")
        head = ("sub", _raw_placed(base, state), kind, index, ())
    else:
        raise _Unkeyable("a shape no operation of this process made")
    return _intern((("shape", head, _location_key(handle), int(handle.Orientation())), ("raw",), ()))


def _raw_placed(handle: Any, state: _Run) -> tuple:
    made = _made_of(handle.TShape(), state)
    if made is None:
        made = _held(handle.TShape(), int(handle.ShapeType()), state)
    if made.parent is not None and not made.held:
        raise _Unkeyable("a shape no operation of this process made")
    return ("shape", made.base(None, state), _location_key(handle), int(handle.Orientation()))


def _register_handle(handle: Any, key: tuple[int, int], state: _Run, entry: "_Entry") -> list["_Made"]:
    """Register a maker's result under the entry that made it, as :func:`_register` does a
    result's shapes; one already registered (the maker handed back its input) keeps its
    first maker."""
    tshape = handle.TShape()
    if _made_of(tshape, state) is not None:
        return []
    made = _Made(tshape, key=key, entry=entry)
    with _LOCK:
        _REGISTRY[tshape] = made
        state.registered[tshape] = made
        _map_subs(handle, made, state)
    return [made]


def _constructs(label: str, args: tuple, kwargs: dict) -> bool:
    """Whether a constructor call builds a shape, rather than wrapping a
    ``TopoDS`` the kernel already holds or making an empty one."""
    from OCP.TopoDS import TopoDS_Shape

    given = [value for value in args[1:]] + [value for name, value in kwargs.items()
                                              if name in ("obj", "outer_wire", "edges", "edge", "wire", "curve", "children")]
    if not given:
        return False
    first = given[0]
    if first is None or isinstance(first, TopoDS_Shape):
        return label == "Compound" and bool(kwargs.get("children"))
    return True


def _op_name(label: str, kind: str, args: tuple, kwargs: dict) -> str:
    if label in _BOOLEAN_LABELS:
        operation = args[3] if len(args) > 3 else kwargs.get("operation")
        name = type(operation).__name__
        return _BOOLEANS.get(name, name.removeprefix("BRepAlgoAPI_").lower())
    if kind == "classmethod":
        return f"{args[0].__name__}.{label}"
    return label


def _key_args(label: str, kind: str, args: tuple) -> tuple:
    if label == "deepcopy":
        return args[:1]  # the memo dict is not a parameter
    return args[1:] if kind in ("classmethod", "constructor") else args


def _wrapped(shape: Any) -> Any:
    """The shape's ``TopoDS_Shape`` from its own state, or None for an empty shape."""
    state = getattr(shape, "__dict__", None)
    return None if state is None else state.get("_wrapped")


# --- keys -----------------------------------------------------------------------------------


def _intern(key: tuple) -> int:
    """A small id for a key tuple, so nested keys stay small. Ids are never
    reused: an entry whose key id left the table can only miss, never collide."""
    with _LOCK:
        found = _KEY_IDS.get(key)
        if found is None:
            found = _KEY_IDS[key] = next(_KEY_IDS_NEXT)
            while len(_KEY_IDS) > _KEYS:
                _KEY_IDS.popitem(last=False)
        else:
            _KEY_IDS.move_to_end(key)
    state = getattr(_LOCAL, "run", None)
    if state is not None and state.bodies:
        log = state.bodies[-1]
        log.keys.append(key)
        log.ids.append(found)
    return found


def _build_key(label: str, kind: str, function: Any, args: tuple, kwargs: dict, state: _Run) -> tuple:
    if label in _FILE_OPS:
        source = args[0] if args else kwargs.get("file_name", kwargs.get("filename", kwargs.get("path")))
        rest = args[1:]
        kw = {name: value for name, value in kwargs.items() if name not in ("file_name", "filename", "path")}
        file_key = _file_key(source)
        parts: tuple = (file_key, *(_normalize(value, state) for value in rest))
        if state.bodies:
            state.bodies[-1].checks.append((functools.partial(_file_key, source), file_key))
    elif label == "make_text":
        # A text reads a font file: its bytes are the parameter, wherever the file is.
        bound = inspect.signature(function).bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = dict(bound.arguments)
        arguments.pop("cls", None)
        font_args = (arguments.get("font"), arguments.pop("font_path", None), arguments.get("font_style"))
        font = _font_key(*font_args)
        if state.bodies:
            state.bodies[-1].checks.append((functools.partial(_font_key, *font_args), font))
        parts = (("cls", args[0].__module__, args[0].__qualname__), font)
        kw = arguments
    else:
        # A compound made again around the same geometry is the same TopoDS, whatever
        # materials its children and it hold: a hit runs the constructor on them as given.
        bare = _LOCAL.bare = label == "Compound" and kind == "constructor"
        try:
            parts = tuple(_normalize(value, state) for value in _key_args(label, kind, args))
            kw = {name: value for name, value in kwargs.items() if not (bare and name == "material")}
            keywords = tuple(sorted((name, _normalize(value, state)) for name, value in kw.items()))
        finally:
            _LOCAL.bare = False
        if kind == "classmethod":
            parts = (("cls", args[0].__module__, args[0].__qualname__), *parts)
        elif kind == "constructor":
            parts = (("cls", type(args[0]).__module__, type(args[0]).__qualname__), *parts)
        return (label, parts, keywords, _settings())
    keywords = tuple(sorted((name, _normalize(value, state)) for name, value in kw.items()))
    return (label, parts, keywords, _settings())


def _settings() -> tuple:
    """What every operation runs under besides its arguments: build123d's
    class-wide ``SkipClean``, which a boolean and a sweep read to decide whether
    to unify what they made."""
    return ("clean", bool(_build123d().SkipClean.clean))


def _font_key(font: Any, font_path: Any, style: Any) -> tuple:
    """The font file a text construction reads, by its bytes: resolved as
    ``Compound.make_text`` resolves it -- a font file build123d can read is
    registered over the face it names, else the system font of that name and
    style is found -- and, like the call, leaving that registration behind."""
    from build123d.text import FONT_ASPECT, FontManager

    manager = FontManager()
    path = os.fspath(font_path) if font_path is not None else None
    if path and manager.check_font(path):
        faces = manager.register_font(path, True, False)
        font = font if font in faces else faces[0]
    try:
        found = manager.find_font(str(font), style)
        located = found.FontPath(FONT_ASPECT[style]).ToCString() if found is not None else ""
    except Exception as exc:  # noqa: BLE001 - a font the kernel cannot resolve is no key
        raise _Unkeyable(f"a font that cannot be resolved: {exc}") from exc
    if not located:
        raise _Unkeyable("a font with no file")
    return ("font", str(found.FontName().ToCString()), _file_key(located))


# A file's digest by what its stat says, so a warm run reads no file it read before:
# (device, inode, size, mtime) -> digest. In memory, as everything the memo holds.
_DIGESTS: "OrderedDict[tuple, str]" = OrderedDict()


def _file_key(source: Any) -> tuple:
    """An imported file is its bytes: hashed once per version of the file, the version
    told by its stat (device, inode, size, modification time)."""
    if isinstance(source, (bytes, bytearray)):
        return ("bytes", hashlib.sha256(bytes(source)).hexdigest())
    try:
        path = Path(os.fspath(source))
        stat = path.stat()
    except (TypeError, OSError) as exc:
        raise _Unkeyable(str(exc)) from exc
    version = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    with _LOCK:
        digest = _DIGESTS.get(version)
    if digest is None:
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 22), b""):
                    hasher.update(chunk)
        except OSError as exc:
            raise _Unkeyable(str(exc)) from exc
        digest = hasher.hexdigest()
        with _LOCK:
            _DIGESTS[version] = digest
            while len(_DIGESTS) > _SUB_MAPS:
                _DIGESTS.popitem(last=False)
    return ("file", digest)


_DOUBLE = struct.Struct("<d")


_JOINT_FIELDS = ("relative_location", "relative_axis", "angle_reference", "angular_range", "linear_range",
                 "_angle", "angle", "position")


def _normalize(value: Any, state: _Run) -> Any:
    """One parameter as a hashable, deterministic key part. The kinds nearly every
    parameter is -- a float, an int, a string, a tuple or list of them -- are told by
    their exact type first; anything else, a subclass of one included, as below."""
    kind = type(value)
    if kind is float:
        return ("n", _DOUBLE.pack(value))
    if kind is tuple or kind is list:
        return ("seq", tuple([_normalize(item, state) for item in value]))
    if kind is int:
        return ("n", _DOUBLE.pack(float(value)))
    if kind is str or value is None or kind is bool:
        return value
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, numbers.Real):
        # By value, as Python compares them: a radius of 3 and one of 3.0 are
        # one parameter, and the kernel takes a double either way.
        return ("n", _DOUBLE.pack(float(value)))
    if isinstance(value, enum.Enum):
        return ("enum", type(value).__name__, value.name)
    if isinstance(value, Path):
        return ("path", str(value))
    if isinstance(value, (list, tuple)):
        return ("seq", tuple(_normalize(item, state) for item in value))
    if isinstance(value, dict):
        return ("map", tuple(sorted((str(key), _normalize(item, state)) for key, item in value.items())))
    if isinstance(value, _build123d().Shape):
        if _wrapped(value) is None:
            # An empty shape -- ``bd.Sketch()``, ``bd.Part()``, what ``+`` starts from -- holds no
            # geometry: it is keyed by its class, and is no input of the call (``_shape_args``).
            return ("empty", type(value).__module__, type(value).__qualname__)
        return ("shape", _shape_key(value, state))
    type_name = type(value).__name__
    if type_name.startswith("BRepAlgoAPI"):
        return ("occ_op", type_name, _operation_settings(value))
    module = type(value).__module__ or ""
    if module.startswith("build123d"):
        if type_name.endswith("Joint"):
            # A joint by what places a part on it: its kind, label, frame or axis, reference, ranges,
            # the values it was connected at, and the kind and label of the joint it is connected to.
            other = getattr(value, "connected_to", None)
            return ("Joint", type_name, value.label, tuple(
                (name, _normalize(getattr(value, name), state)) for name in _JOINT_FIELDS if hasattr(value, name)),
                None if other is None else (type(other).__name__, other.label))
        if type_name == "Axis":
            return ("Axis", _normalize(tuple(value.position), state), _normalize(tuple(value.direction), state))
        if type_name == "Plane":
            return ("Plane", _normalize(tuple(value.origin), state), _normalize(tuple(value.x_dir), state),
                    _normalize(tuple(value.z_dir), state))
        if type_name == "Matrix":
            transform = value.wrapped
            return ("Matrix", tuple(("n", _DOUBLE.pack(transform.Value(row, column)))
                                    for row in (1, 2, 3) for column in (1, 2, 3, 4)))
        if type_name == "BoundBox":
            return ("BoundBox", _normalize(tuple(value.min), state), _normalize(tuple(value.max), state))
        # Vector, Location, Rotation, Color: their components, in order.
        if hasattr(value, "__iter__"):
            return (type_name, _normalize(tuple(value), state))
    if module == "cadgen.engine.materials" and type_name == "Material":
        return ("Material", repr(value))  # a frozen value of strings and floats
    raise _Unkeyable(f"unkeyable argument type: {module}.{type_name}")


def _operation_settings(operation: Any) -> tuple:
    """Every setting an OCC boolean or splitter reports, as its caller left it before
    the call (build123d sets the fuzzy value and the glue mode of a fuse): a hit that
    ignored one would hand back another operation's result. Arguments and tools are
    not settings: ``_bool_op`` sets them from the shapes the key already names."""
    found = []
    for name in ("Operation", "FuzzyValue", "Glue", "NonDestructive", "CheckInverted"):
        getter = getattr(operation, name, None)
        if getter is None:
            continue
        value = getter()
        if isinstance(value, bool):
            found.append((name, value))
        elif isinstance(value, numbers.Real):
            found.append((name, _DOUBLE.pack(float(value))))
        else:
            found.append((name, type(value).__name__, int(value)))
    return tuple(found)


@functools.cache
def _build123d() -> Any:
    """The build123d names every call reads, imported once, on first use: importing this
    module imports no build123d."""
    import types

    from build123d.topology import Shape
    from build123d.topology.shape_core import SkipClean, downcast

    return types.SimpleNamespace(Shape=Shape, SkipClean=SkipClean, downcast=downcast)


def _shape_args(args: tuple, kwargs: dict) -> list:
    """The shapes a call was given, in call order, lists and tuples opened; an empty shape
    holds no geometry and is none of them (``_normalize`` keys it by its class)."""
    shape = _build123d().Shape
    found: list = []
    pending = [value for _name, value in sorted(kwargs.items(), reverse=True)] if kwargs else []
    pending.extend(reversed(args))
    while pending:
        value = pending.pop()
        if isinstance(value, shape):
            if _wrapped(value) is not None:
                found.append(value)
        elif isinstance(value, (list, tuple)):
            pending.extend(reversed(value))
    return found


_TRANSFORM = struct.Struct("<12d")


def _location_key(wrapped: Any) -> bytes:
    """A location's transformation, its twelve values packed in row order; most shapes
    are where their maker put them, at the identity, whose packing is computed once."""
    location = wrapped.Location()
    if location.IsIdentity():
        return _IDENTITY_KEY
    value = location.Transformation().Value
    return _TRANSFORM.pack(value(1, 1), value(1, 2), value(1, 3), value(1, 4), value(2, 1), value(2, 2),
                           value(2, 3), value(2, 4), value(3, 1), value(3, 2), value(3, 3), value(3, 4))


def _identity_key() -> bytes:
    from OCP.TopLoc import TopLoc_Location

    value = TopLoc_Location().Transformation().Value
    return _TRANSFORM.pack(*(value(row, column) for row in (1, 2, 3) for column in (1, 2, 3, 4)))


_IDENTITY_KEY = _identity_key()


def _shape_key(shape: Any, state: _Run) -> int:
    """The interned key of a shape input: its placed geometry, its attributes,
    its children."""
    placed = _placed_key(shape, state)
    state_dict = shape.__dict__
    label = state_dict.get("label")
    if not isinstance(label, str):
        raise _Unkeyable("a label that is not a string")
    color = state_dict.get("_color")
    color_key = None if color is None else _normalize(tuple(color), state)
    face_colors = state_dict.get(FACE_COLORS) or {}
    # A compound's constructor holds its children's geometry, not their materials (``_build_key``).
    material = None if getattr(_LOCAL, "bare", False) else state_dict.get("material")
    face_materials = () if getattr(_LOCAL, "bare", False) else state_dict.get(FACE_MATERIALS) or ()
    attrs = (
        "attrs", label, color_key, bool(state_dict.get("for_construction")),
        material if material is None or isinstance(material, str) else _normalize(material, state),
        tuple(sorted((int(ordinal), _normalize(tuple(rgba), state)) for ordinal, rgba in face_colors.items())),
        tuple(sorted((int(ordinal), _normalize(value, state)) for ordinal, value in dict(face_materials).items())),
        _normalize(state_dict.get("joints") or {}, state),  # a hit hands back the joints the first run held
        # and the mechanism states an assembly was given (``mechanism.mechanism_state``): a hit of an
        # operation on it hands back what the first run held, so a state is its input, and a
        # coupling (``mechanism.gear_pair`` and its two siblings) too, and an animation (``animations.animation``).
        _normalize(state_dict.get(CONFIGURATIONS) or {}, state),
        _normalize(state_dict.get(COUPLINGS) or {}, state),
        _normalize(state_dict.get(ANIMATIONS) or {}, state),
    )
    children = tuple(_shape_key(child, state) for child in state_dict.get("_NodeMixin__children") or ())
    return _intern((placed, attrs, children))


def _placed_key(shape: Any, state: _Run) -> tuple:
    """Where a shape's geometry came from, with its location and orientation."""
    wrapped = _wrapped(shape)
    if wrapped is None:
        raise _Unkeyable("an empty shape")
    tshape = wrapped.TShape()
    made = _made_of(tshape, state)
    if made is None:
        made = _register_sub(shape, wrapped, tshape, state)
    return ("shape", made.base(shape, state), _location_key(wrapped), int(wrapped.Orientation()))


def _made_of(tshape: Any, state: _Run | None) -> "_Made | None":
    if state is not None:
        found = state.registered.get(tshape)
        if found is not None and not found.tainted:
            return found
        found = state.transient.get(tshape)
        if found is not None and not found.tainted:
            return found
    found = _REGISTRY.get(tshape)
    if found is not None and not found.tainted:
        return found
    # A nested run can receive an outer run's live input after its entry was
    # evicted. Share that registration so a native mutation retires both views,
    # without borrowing the ancestor's feature index for this run's trace.
    ancestor = state.previous if state is not None else None
    while ancestor is not None:
        found = ancestor.registered.get(tshape)
        if found is not None and not found.tainted:
            return found
        found = ancestor.transient.get(tshape)
        if found is not None and not found.tainted:
            return found
        ancestor = ancestor.previous
    return None


def _register_sub(shape: Any, wrapped: Any, tshape: Any, state: _Run) -> "_Made":
    """Key a sub-shape by its ancestor: ``topo_parent``, the shape it was
    extracted from, and its index in that shape's map of its kind."""
    from build123d.topology import Shape

    parent = shape.__dict__.get("topo_parent")
    if not isinstance(parent, Shape) or parent is shape:
        return _held(tshape, int(wrapped.ShapeType()), state)
    parent_wrapped = _wrapped(parent)
    if parent_wrapped is None:
        raise _Unkeyable("a sub-shape of an empty shape")
    parent_made = _made_of(parent_wrapped.TShape(), state)
    if parent_made is None:
        parent_made = _register_sub(parent, parent_wrapped, parent_wrapped.TShape(), state)
    kind = int(wrapped.ShapeType())
    index = _sub_map(parent_wrapped, kind).FindIndex(wrapped)
    if index == 0:
        # Its topo_parent does not hold it where it is -- a copy, a shape re-placed below
        # its parent: the root holding its TShape names it.
        return _held(tshape, kind, state)
    made = _Made(tshape, key=None, entry=None, parent=parent_made, kind=kind, index=index)
    parent_made.subs.append(made)
    with _LOCK:
        if parent_made.persistent():
            _REGISTRY[tshape] = made
            state.registered[tshape] = made
        else:
            state.transient[tshape] = made
    return made


def _held(tshape: Any, kind: int, state: _Run) -> "_Made":
    """Key a shape with no ancestor to name it by -- one cast afresh out of a compound,
    or one its ``topo_parent`` does not hold where it is -- by the persistent root
    holding its TShape (``_SUBS``): its kind and its first ordinal among the root's
    sub-shapes of that kind, by TShape. The root is the same object on a hit, so the
    ordinal is too; its location is the shape's own, keyed beside it (``_placed_key``)."""
    root, index = _holder(tshape, kind)
    made = _Made(tshape, key=None, entry=None, parent=root, kind=kind, index=index)
    made.held = True
    with _LOCK:
        root.subs.append(made)
        _REGISTRY[tshape] = made
        state.registered[tshape] = made
    return made


def _held_head(tshape: Any, kind: int) -> tuple:
    """What names a sub-shape by the root holding its TShape: the root's key, the kind
    and the ordinal (``_held``)."""
    root, index = _holder(tshape, kind)
    return root.base(None, None), kind, index


def _holder(tshape: Any, kind: int) -> tuple["_Made", int]:
    """The persistent root holding ``tshape`` (``_SUBS``) and the TShape's first ordinal
    among the root's sub-shapes of ``kind``."""
    from OCP.TopAbs import TopAbs_ShapeEnum

    root = _SUBS.get(tshape)
    if root is None or root.tainted or root.parent is not None or not root.persistent():
        raise _Unkeyable("a shape no operation of this process made")
    with _LOCK:
        ordinals = _ORDINALS.get((root.tshape, kind))
        if ordinals is None:
            mapped = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(_handle_of(root.tshape), TopAbs_ShapeEnum(kind), mapped)
            ordinals = {}
            for ordinal in range(1, mapped.Extent() + 1):
                ordinals.setdefault(mapped.FindKey(ordinal).TShape(), ordinal)
            _ORDINALS[(root.tshape, kind)] = ordinals
            while len(_ORDINALS) > _SUB_MAPS:
                _ORDINALS.popitem(last=False)
        else:
            _ORDINALS.move_to_end((root.tshape, kind))
    index = ordinals.get(tshape)
    if index is None:
        raise _Unkeyable("a shape no operation of this process made")
    return root, index


def _sub_map(parent_wrapped: Any, kind: int) -> Any:
    """``TopExp.MapShapes`` of a located shape for one kind, kept for the shapes
    a model keeps extracting from."""
    from OCP.TopAbs import TopAbs_ShapeEnum

    key = (hash(parent_wrapped), kind)
    with _LOCK:
        found = _MAPS.get(key)
        if found is not None and found[0].IsSame(parent_wrapped):
            _MAPS.move_to_end(key)
            return found[1]
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(parent_wrapped, TopAbs_ShapeEnum(kind), mapped)
    with _LOCK:
        _MAPS[key] = (parent_wrapped.Located(parent_wrapped.Location()), mapped)
        while len(_MAPS) > _SUB_MAPS:
            _MAPS.popitem(last=False)
    return mapped


# --- construction keys ----------------------------------------------------------------------










_NO_COPY = object()
_COPIED = object()
















# --- the registry ---------------------------------------------------------------------------


class _Made:
    """What the memo knows about one ``TShape``: the entry that made it and the
    position of the shape among that call's results (or the sub-shape relation
    that names it), the effects operations have had on it since, and its own
    registered sub-shapes. Runs bind their own features to this shared record."""

    __slots__ = ("tshape", "key", "position", "entry", "parent", "kind", "index", "effects",
                 "subs", "born", "origin", "tainted", "rowed", "held", "placed")

    def __init__(self, tshape: Any, *, key: tuple[int, int] | None,
                 entry: "_Entry | None", parent: "_Made | None" = None, kind: int | None = None,
                 index: int | None = None, position: int = 0, origin: Any = _NO_COPY) -> None:
        self.tshape = tshape
        self.key = key
        self.position = position
        self.entry = entry
        self.parent = parent
        self.kind = kind
        self.index = index
        self.effects: list[_Effect] = []
        self.subs: list[_Made] = []
        self.born = next(_SEQUENCE)
        # Whether this TShape is a certified whole-body copy (``_copy_origins``):
        # _COPIED of a source this process made, None of one it did not, _NO_COPY no copy.
        self.origin = origin
        # Unlike eviction, an unreplayable native mutation invalidates every
        # run still holding this very registration and its sub-shape records.
        self.tainted = False
        # The sub-shapes of this root the ledger holds rows for (``_rowed``): what a
        # reset of it reads, instead of every sub-shape it holds.
        self.rowed: set | None = None
        # Keyed by the root holding its TShape, not by an ancestor it was taken from
        # (``_held``).
        self.held = False
        # A placement shares this TShape (``_sharing``): a maker that changes what it is
        # given in place is given a copy of it (``_unshared``).
        self.placed = False

    def root(self) -> "_Made":
        made = self
        while made.parent is not None:
            made = made.parent
        return made

    def persistent(self) -> bool:
        return self.root().key is not None

    def base(self, shape: Any, state: _Run) -> tuple:
        """The key of this TShape as an input: the entry that made it, or the
        sub-shape relation, and the effects applied to it so far."""
        applied = tuple(effect.id for effect in self.effects)
        if self.parent is None:
            if self.key is None:
                raise _Unkeyable("a shape no memoized operation made")
            return ("made", self.key[0], self.key[1], self.position, applied)
        if self.held:
            return ("held", self.parent.base(None, state), self.kind, self.index, applied)
        parent = shape.__dict__.get("topo_parent")
        if parent is None:
            # It was handed another shape's attributes, ``topo_parent`` None among them --
            # build123d's fuse copies a sketch's onto the first face it fuses, a face of a
            # text's compound -- so no ancestor names it now: the root holding its TShape
            # does, as it names a shape cast afresh out of a compound (``_held``).
            return ("held", *_held_head(self.tshape, self.kind), applied)
        index = self.index
        parent_wrapped = _wrapped(parent)
        if parent_wrapped is not None and parent_wrapped.TShape() != self.parent.tshape:
            # Extracted now from another shape that holds this TShape -- a boolean's result
            # shares what it left alone with its input, and with an earlier result of other
            # inputs, whose extraction registered it first: its place is in THIS parent's map,
            # as a run that extracted it from this parent alone would register it.
            index = _sub_map(parent_wrapped, self.kind).FindIndex(_wrapped(shape))
            if index == 0:
                return ("held", *_held_head(self.tshape, self.kind), applied)
        return ("sub", _placed_key(parent, state), self.kind, index, applied)

    def handle(self) -> Any:
        return _handle_of(self.tshape)


def _reset(makers: list[_Made], run_id: int) -> None:
    """Each of an entry's makers back to the state its operation returned: every
    row noted in the ledger on any sub-shape of its TShape by an earlier run, after
    it was made, undone, latest first. Rows this run applied are its own
    operations' and stay. The rows are found by the index the ledger keeps as it
    is written (``_rowed``, ``_Made.rowed``), never by walking the maker's
    sub-shapes: a hit costs the rows later operations left on its result, not the
    result's size. A row on a sub-shape the maker shares with an earlier root --
    the one that made the sub-shape, an input-ancestor of the maker's, which a hit
    handed back before it -- is the earlier root's, undone when it was reset; a row
    on a sub-shape of the maker's own, or on one it changed as an input, is the
    maker's. A row on a sub-shape a container holds is the first root's registered
    holding it: a part's, reset by its own maker, or the container's own."""
    for maker in makers:
        rowed = maker.rowed
        if _LEDGER:
            if rowed is None:
                candidates: Any = (maker.tshape,)
            else:
                candidates = rowed if maker.tshape in rowed else [maker.tshape, *rowed]
            for tshape in list(candidates):
                rows = _LEDGER.get(tshape)
                if not rows:
                    if rowed is not None:
                        rowed.discard(tshape)
                    continue
                kept = [row for row in rows if row.run == run_id or row.seq <= maker.born]
                for row in reversed(rows):
                    if row.run != run_id and row.seq > maker.born:
                        row.set(row.before)
                if kept:
                    _LEDGER[tshape] = kept
                else:
                    del _LEDGER[tshape]
                    if rowed is not None:
                        rowed.discard(tshape)
        elif rowed:
            rowed.clear()
        pending: list[_Made] = [maker]
        while pending:
            made = pending.pop()
            made.effects.clear()
            pending.extend(made.subs)


def _rowed(tshape: Any, holder: "_Made | None") -> None:
    """Index a ledger row on ``tshape`` at the roots whose reset may undo it
    (``_reset``): the root that holds the sub-shape most closely (``_SUBS``) and
    the root of the input it was changed on, ``holder``, when another."""
    first = _SUBS.get(tshape)
    for made in (first, holder):
        if made is None or made.tainted:
            continue
        if made.rowed is None:
            made.rowed = set()
        made.rowed.add(tshape)
        if holder is first:
            break


def _handle_of(tshape: Any) -> Any:
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    shape.TShape(tshape)
    return shape


def _register(result: Any, key: tuple[int, int] | None, feature: int | None, state: _Run,
              entry: "_Entry | None", copied: dict[int, Any] | None = None) -> list[_Made]:
    """Register every shape of a result under the entry that made it, each at its
    position among the result's shapes, and bound to the run's ``feature`` that made
    it. A TShape already registered (a move shares its input's) keeps its first maker.
    Every sub-shape below a persistent root names the first root registered holding it
    (``_SUBS``, ``_map_subs``): a result made from an input shares the input's."""
    created: list[_Made] = []
    for position, shape in enumerate(_result_shapes(result)):
        wrapped = _wrapped(shape)
        if wrapped is None:
            continue
        tshape = wrapped.TShape()
        if _made_of(tshape, state) is not None:
            continue
        origin = copied.get(position, _NO_COPY) if copied else _NO_COPY
        made = _Made(tshape, key=key, entry=entry, position=position, origin=origin)
        with _LOCK:
            if key is None:
                state.transient[tshape] = made
            else:
                _REGISTRY[tshape] = made
                state.registered[tshape] = made
                created.append(made)
                _map_subs(wrapped, made, state)
            if feature is not None:
                state.owners[made] = feature
    return created


def _map_subs(wrapped: Any, made: _Made, state: _Run) -> None:
    """Every sub-shape below a persistent root names the root (``_SUBS``), the first
    to hold it kept: what a foreign or transient wrapper that holds one of them
    embeds (``_embedded``), and where a ledger row on one is indexed (``_rowed``).
    The walk stops at a shape a persistent root already holds -- a part a compound
    is made of, registered when it was made -- whose sub-shapes are mapped already,
    under the first root to hold them: registering a container of parts
    costs its direct children, not the parts' sub-shapes. A compound no root holds
    is entered, a shape of any other kind mapped whole."""
    from OCP.TopoDS import TopoDS_Iterator

    if _SUBS.setdefault(wrapped.TShape(), made) is not made:
        return  # a root registered before holds it, and walked below it
    pending = [wrapped]
    entered: set = set()
    while pending:
        iterator = TopoDS_Iterator(pending.pop())
        while iterator.More():
            child = iterator.Value()
            iterator.Next()
            tshape = child.TShape()
            held = _made_of(tshape, state)
            if held is not None and held.persistent():
                continue
            if int(child.ShapeType()) == _COMPOUND:
                if tshape not in entered:
                    entered.add(tshape)
                    _SUBS.setdefault(tshape, made)
                    pending.append(child)
                continue
            for sub in _mapped(child)[1]:
                _SUBS.setdefault(sub, made)


def _drop(entry: "_Entry") -> None:
    """Forget an entry's registrations and the ledger rows its effects, and the
    effects on its results, hold (the entry itself is already out of the memo)."""
    for _index, effect in entry.effects:
        effect.forget()
    pending = list(entry.made)
    while pending:
        made = pending.pop()
        if _REGISTRY.get(made.tshape) is made:
            _REGISTRY.pop(made.tshape)
        for effect in made.effects:
            effect.forget()
        if made.parent is None:
            _forget_states(made)
        pending.extend(made.subs)
    entry.made = []


def _taint(made: _Made | None, state: _Run) -> None:
    """An input changed in a way no hit can replay: its maker forgets it, so
    the next run rebuilds it and runs this operation on the fresh shape. Counted
    (``tainted``)."""
    if made is None:
        return
    root = made.root()
    with _LOCK:
        _STATS["tainted"] += 1
        pending = [root]
        while pending:
            item = pending.pop()
            item.tainted = True
            pending.extend(item.subs)
        if root.entry is not None:
            if _MEMO.get(root.entry.key) is root.entry:
                _MEMO.pop(root.entry.key)
            _drop(root.entry)
        else:
            pending = [root]
            while pending:
                item = pending.pop()
                if state.transient.get(item.tshape) is item:
                    state.transient.pop(item.tshape)
                if _REGISTRY.get(item.tshape) is item:
                    _REGISTRY.pop(item.tshape)
                pending.extend(item.subs)


def _returned_shapes(result: Any) -> list:
    """The shape objects a call returned itself: the result, or the members of a list or
    tuple it returned -- not the children they hold."""
    Shape = _build123d().Shape
    found: list = []
    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, Shape):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            pending.extend(reversed(value))
    return found


def _result_shapes(result: Any) -> list:
    """Every shape object a result holds: itself, the members of a list or
    tuple, and anytree children, read off the node state."""
    Shape = _build123d().Shape
    found: list = []
    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, Shape):
            found.append(value)
            pending.extend(reversed(value.__dict__.get("_NodeMixin__children") or ()))
        elif isinstance(value, (list, tuple)):
            pending.extend(reversed(value))
    return found


# --- snapshots ----------------------------------------------------------------------------


class _Entry:
    __slots__ = ("key", "inputs", "snapshot", "effects", "history", "made", "in_place", "handles", "read")

    def __init__(self, *, key: tuple[int, int], inputs: list, snapshot: Any, effects: list,
                 history: Any = None, in_place: bool = False, handles: list = ()) -> None:
        self.key = key
        self.inputs = inputs
        # The inputs as the miss's feature was given them (``kernel_trace.Feature.handles``):
        # what a hit's feature is given too, since its results are the miss's objects.
        self.handles = list(handles)
        self.snapshot = snapshot
        self.effects = effects
        # What the makers reported of the results (``kernel_history.History``), captured on
        # the miss and kept, like the effects, as long as the entry: a hit names from it.
        self.history = history
        self.made: list[_Made] = []
        # The operation changed ``self`` and returned it (``clean``): a hit asked
        # by another object wrapping the same TShape changes THAT object, as the
        # operation would, and returns it.
        self.in_place = in_place
        # A file read's file key and site (``_read_again``), else None.
        self.read: tuple | None = None

    def matches(self, shapes: list) -> bool:
        if len(shapes) != len(self.inputs):
            return False
        for shape, tshape in zip(shapes, self.inputs):
            wrapped = _wrapped(shape)
            if wrapped is None or wrapped.TShape() != tshape:
                return False
        return True

    def refresh(self, feature: int | None, state: _Run, copied: dict[int, tuple | None]) -> None:
        """Bind the entry's shapes to this run, and to the feature of it that hit
        (none for a child's decode)."""
        for made in self.made:
            if feature is not None:
                state.owners[made] = feature
            pending = [made]
            while pending:
                item = pending.pop()
                state.registered[item.tshape] = item
                pending.extend(item.subs)
            if made.position in copied:
                made.origin = copied[made.position]


def _owned(attrs: dict) -> dict:
    """``attrs`` with every dict and list it holds copied: what the object holds of
    its own -- its joints, a decoded child's face colours and finish -- is the
    object's, and the model may change it in place without changing the snapshot."""
    return {name: dict(value) if type(value) is dict else list(value) if type(value) is list else value
            for name, value in attrs.items()}


class _ShapeState:
    """One live result object as the operation returned it."""

    __slots__ = ("obj", "attrs", "wrapped", "children")

    def __init__(self, obj: Any) -> None:
        Shape = _build123d().Shape
        attrs = dict(obj.__dict__)
        wrapped = attrs.pop("_wrapped", None)
        if wrapped is None:
            raise _Unkeyable("an empty result")
        self.obj = obj
        self.wrapped = wrapped.Located(wrapped.Location())
        children = attrs.get("_NodeMixin__children")
        self.children = None
        if children is not None:
            if not all(isinstance(child, Shape) for child in children):
                raise _Unkeyable("a child that is not a shape")
            self.children = [_ShapeState(child) for child in children]
            attrs["_NodeMixin__children"] = None
        self.attrs = _owned(attrs)

    def restore(self) -> Any:
        attrs = _owned(self.attrs)
        if self.children is not None:
            attrs["_NodeMixin__children"] = [state.obj for state in self.children]
        obj = self.obj
        obj.__dict__.clear()
        obj.__dict__["_wrapped"] = _build123d().downcast(self.wrapped.Located(self.wrapped.Location()))
        obj.__dict__.update(attrs)
        if self.children is not None:
            for state in self.children:
                state.restore()
        return obj

    def fresh(self, memo: dict | None = None) -> Any:
        """New objects as the operation returned these, each a handle on the same TShape
        (``_sharing``): another placement of the result, the objects it returned left as
        the model holds them now."""
        import copy

        memo = {} if memo is None else memo
        cls = type(self.obj)
        obj = cls.__new__(cls)
        memo[id(self.obj)] = obj
        obj.__dict__["_wrapped"] = _build123d().downcast(self.wrapped.Located(self.wrapped.Location()))
        _note_placed(self.wrapped.TShape())
        for name, value in self.attrs.items():
            if name != "_NodeMixin__children":
                obj.__dict__[name] = value if name == "topo_parent" else copy.deepcopy(value, memo)
        if self.children is not None:
            obj.__dict__["_NodeMixin__children"] = [state.fresh(memo) for state in self.children]
        for joint in (obj.__dict__.get("joints") or {}).values():
            joint.parent = obj
        return obj


class _Sequence:
    __slots__ = ("container", "items")

    def __init__(self, container: type, items: list) -> None:
        self.container = container
        self.items = items

    def restore(self) -> Any:
        return self.container(item.restore() for item in self.items)

    def fresh(self, memo: dict | None = None) -> Any:
        memo = {} if memo is None else memo
        return self.container(item.fresh(memo) for item in self.items)


class _Mapping:
    __slots__ = ("items",)

    def __init__(self, items: list) -> None:
        self.items = items

    def restore(self) -> Any:
        return {name: item.restore() for name, item in self.items}

    def fresh(self, memo: dict | None = None) -> Any:
        memo = {} if memo is None else memo
        return {name: item.fresh(memo) for name, item in self.items}


class _Literal:
    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def restore(self) -> Any:
        return self.value

    def fresh(self, memo: dict | None = None) -> Any:
        return self.value


class _Adopt:
    """A constructor's result: the TopoDS it built, for the next construction
    of the same thing to wrap."""

    __slots__ = ("wrapped", "slot")

    def __init__(self, wrapped: Any, slot: str | None) -> None:
        if wrapped is None:
            raise _Unkeyable("an empty construction")
        self.wrapped = wrapped.Located(wrapped.Location())
        self.slot = slot

    def restore(self) -> Any:
        return self.wrapped.Located(self.wrapped.Location())


def _snapshot(value: Any) -> Any:
    if isinstance(value, _build123d().Shape):
        return _ShapeState(value)
    if isinstance(value, (list, tuple)):
        return _Sequence(type(value), [_snapshot(item) for item in value])
    if type(value) is dict:
        return _Mapping([(name, _snapshot(item)) for name, item in value.items()])
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return _Literal(value)
    if getattr(type(value), "__kernel_value__", False):
        return _Literal(value)  # a read-only value (``reader.Mesh``): a hit hands back the same object
    raise _Unkeyable(f"a result that cannot be kept: {type(value).__name__}")


# --- effects on inputs ----------------------------------------------------------------------
#
# What an operation does to its inputs is read as each sub-shape's state
# (``_state``) after the operation and compared with the state before it. The
# memo keeps the state it last read of every sub-shape of a memoized shape
# (``_STATE``): written when a capture reads it and when a ledger row sets it,
# forgotten with the entry whose result holds the sub-shape. So an input is
# walked once per operation, after it, and the state before is what the memo
# already holds.

_STATE: dict[Any, tuple] = {}
# Every sub-shape of every persistent root, by TShape, to the first root registered
# holding it (``_register``): what a foreign or transient wrapper embeds when it holds
# one of them (``_embedded``). Forgotten with the root (``_forget_states``).
_SUBS: dict[Any, "_Made"] = {}


class _Captured:
    """One input before the operation: its full map, the TShape of each of its
    sub-shapes by ordinal and each one's state -- or, for a compound's
    constructor (``top``), its own TShape and state alone. A transient-only input
    keeps no scalar states: its topology alone guards its lineage registration."""

    __slots__ = ("index", "handle", "mapped", "tshapes", "rows", "embedded", "known", "top", "_held")

    def __init__(self, index: int, handle: Any, embedded: list[_Made], known: bool, *,
                 topology: tuple[Any, list] | None = None, structural_only: bool = False,
                 top: bool = False) -> None:
        self.index = index
        self.handle = handle
        self.embedded = embedded
        self.top = top
        if top:
            topology = (None, [handle.TShape()])
        # A directly memoized shape's sub-shapes have states the memo keeps.
        # Roots reached through uncontrolled wrappers are read fresh and kept nowhere.
        self.known = known
        self.mapped, self.tshapes = _mapped(handle) if topology is None else topology
        self._held = None
        if structural_only:
            self.rows = None
        elif known:
            rows = []
            kept = _STATE.get
            for tshape in self.tshapes:
                state = kept(tshape)
                if state is None:
                    state = _STATE[tshape] = _state(tshape)
                rows.append(state)
            self.rows = rows
        else:
            self.rows = [_state(tshape) for tshape in self.tshapes]

    def held(self) -> set:
        """The TShapes of its sub-shapes, as a set (``_covered``)."""
        if self._held is None:
            self._held = set(self.tshapes)
        return self._held


def _capture(shapes: list, *, embedded: bool = False, top: bool = False) -> list[_Captured]:
    """The inputs the operation may change: one per TShape, in call order, less
    any that is a sub-shape of another input (its ancestor's delta covers it).
    With ``embedded`` (an uncached call), each persistent root a foreign or
    transient input embeds is captured separately, with fresh scalar state. A
    transient input keeps only its topology map so a structural change forgets
    its old registration without blaming the unchanged roots it contains. A
    foreign input that embeds none is noted for the run (``_Run.foreign``) and
    passed over without a walk while its children are as many as when noted.
    With ``top`` (a call that composes its inputs, ``_composes``, which changes
    nothing of one but its own ``Free`` flag), each memoized input is captured as
    its own TShape alone, and nothing else is: no input's structure or embedded
    root can change."""
    state = getattr(_LOCAL, "run", None)
    distinct: list[_Captured] = []
    protected: dict[Any, _Captured] = {}
    seen: set = set()
    for index, shape in enumerate(shapes):
        wrapped = _wrapped(shape)
        if wrapped is None:
            continue
        tshape = wrapped.TShape()
        if tshape in seen:
            continue
        seen.add(tshape)
        made = _made_of(tshape, state)
        if top:
            if made is not None and made.persistent():
                distinct.append(_Captured(index, wrapped.Located(wrapped.Location()), [], known=True, top=True))
            continue
        topology = None
        structural_only = False
        if embedded and (made is None or not made.persistent()):
            if made is None and state is not None and state.foreign.get(tshape) == tshape.NbChildren():
                continue
            topology = _mapped(wrapped)
            roots = _embedded(wrapped, state, tshapes=topology[1])
            for root in roots:
                if root.tshape not in protected:
                    protected[root.tshape] = _Captured(index, root.handle(), [root], known=False)
            if made is None:
                if not roots and state is not None:
                    state.foreign[tshape] = tshape.NbChildren()
                continue
            structural_only = made.origin is _NO_COPY or made.origin is None
        distinct.append(_Captured(index, wrapped.Located(wrapped.Location()), [],
                                  known=made is not None and made.persistent(),
                                  topology=topology, structural_only=structural_only))
    if top:
        return distinct  # one TShape each: none covers another's state
    # A protected root is captured once even if it is also a direct input. Keep
    # each root's protection independent of the wrappers' topology guards and
    # of other roots that share or contain some of its native sub-shapes.
    distinct = [item for item in distinct if item.rows is None or item.handle.TShape() not in protected]
    return [item for item in distinct
            if item.rows is None or not _covered(item, distinct)] + list(protected.values())


# Past this many inputs, which input may hold which is told by their sub-shapes first.
_COVER_SCAN = 4


def _covered(item: _Captured, distinct: list[_Captured]) -> bool:
    """Whether another captured input's map holds ``item``: its ancestor's delta covers it.
    Only an input holding item's TShape can; with many inputs (a wire's edges), those are
    found by their sub-shapes first, and only they are asked."""
    others = [other for other in distinct if other is not item and other.rows is not None]
    if len(others) > _COVER_SCAN:
        tshape = item.handle.TShape()
        others = [other for other in others if tshape in other.held()]
    return any(other.mapped.Contains(item.handle) for other in others)


def _embedded(wrapped: Any, state: _Run | None, *, tshapes: list | None = None) -> list[_Made]:
    """The persistent memoized roots a foreign or transient shape holds: by a root's own
    TShape or an extracted sub-shape's (registered), or by any sub-shape of a root
    (``_SUBS``) -- a boolean's result shares its inputs' faces and edges, and an
    operation on it changes them in place."""
    if tshapes is None:
        _map, tshapes = _mapped(wrapped)
    found: list[_Made] = []
    for tshape in tshapes:
        made = _made_of(tshape, state)
        if made is None:
            made = _SUBS.get(tshape)
            if made is not None and made.tainted:
                made = None
        if made is not None and made.persistent() and made.root() not in found:
            found.append(made.root())
    return found


def _effects(captured: list[_Captured], state: _Run) -> tuple[list[tuple[int, "_Effect"]], bool]:
    """What the operation did to its inputs, as replayable deltas noted in the
    ledger; ``sound`` is False when a change could not be captured (the input,
    or what it embeds, was tainted)."""
    effects: list[tuple[int, _Effect]] = []
    sound = True
    rowed: set = set()
    for item in captured:
        tshapes = item.tshapes if item.top else _mapped(item.handle)[1]
        if item.rows is None:
            if tshapes != item.tshapes:
                _STATS["unreplayable"] += 1
                sound = False
                _taint(_made_of(item.handle.TShape(), state), state)
            continue
        rows = [_state(tshape) for tshape in tshapes]
        if item.embedded:
            if tshapes != item.tshapes or rows != item.rows:
                for made in item.embedded:
                    _taint(made, state)
                sound = False
            continue
        if rows == item.rows:
            continue
        effect = _delta(item, tshapes, rows, rowed)
        made = _made_of(item.handle.TShape(), state)
        if effect is None:
            _STATS["unreplayable"] += 1
            sound = False
            _taint(made, state)
            continue
        effect.note(state.id, None if made is None else made.root())
        effects.append((item.index, effect))
        if made is not None:
            made.effects.append(effect)
    return effects, sound


def _mapped(handle: Any) -> tuple[Any, list]:
    """A shape's full ``TopExp`` map, and the TShape of each sub-shape by ordinal."""
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(handle, mapped)
    find = mapped.FindKey
    return mapped, [find(ordinal).TShape() for ordinal in range(1, mapped.Extent() + 1)]


def _state(tshape: Any) -> tuple:
    """One sub-shape's cheap state: kind, tolerance, the seven flags, how many
    representations it holds, and an edge's parametric flags. The kernel hands a
    TShape back as its own class, which says its kind: an edge, a vertex or a face
    is told by it without the kind being asked; any other by its kind."""
    flags = (tshape.Free(), tshape.Modified(), tshape.Checked(), tshape.Orientable(), tshape.Closed(),
             tshape.Infinite(), tshape.Convex())
    cls = type(tshape)
    if cls is BRep_TEdge:
        return (_EDGE, tshape.Tolerance(), flags, tshape.Curves().Extent(),
                (tshape.SameParameter(), tshape.SameRange(), tshape.Degenerated()))
    if cls is BRep_TVertex:
        return (_VERTEX, tshape.Tolerance(), flags, tshape.Points().Extent(), None)
    if cls is BRep_TFace:
        return (_FACE, tshape.Tolerance(), flags, None, None)
    return (int(tshape.ShapeType()), None, flags, None, None)


def _forget_states(made: _Made) -> None:
    """Drop the states kept of a root's sub-shapes, and that they name it (``_SUBS``):
    the memo no longer holds it. A sub-shape another entry's result shares is read
    again when next captured, and names a root again when a result holding it
    registers -- that entry misses next, its input gone, and registers its own."""
    for tshape in _mapped(made.handle())[1]:
        _STATE.pop(tshape, None)
        if _SUBS.get(tshape) is made:
            del _SUBS[tshape]


def _representations(tshape: Any, kind: int) -> Any:
    return tshape.ChangeCurves() if kind == _EDGE else tshape.ChangePoints()


def _appended(tshape: Any, kind: int, count: int) -> tuple:
    """The representations an edge or a vertex holds past the first ``count``:
    the ones the operation appended. The kernel's list reads from its head, and
    iterating it from Python costs milliseconds however short it is: it is
    reversed in place, its head taken as many times, reversed back and the tail
    put back -- nothing rebuilt, every read a step."""
    representations = _representations(tshape, kind)
    extra = representations.Extent() - count
    if extra <= 0:
        return ()
    representations.Reverse()
    taken = []
    for _ in range(extra):
        taken.append(representations.First())
        representations.RemoveFirst()
    representations.Reverse()
    taken.reverse()
    for representation in taken:
        representations.Append(representation)
    return tuple(taken)


def _truncate(representations: Any, count: int) -> None:
    """Drop the representations past the first ``count``, from the tail. The
    kernel's list removes from its head: it is reversed in place, its head
    removed as many times, and reversed back -- nothing is rebuilt."""
    extra = representations.Extent() - count
    if extra <= 0:
        return
    representations.Reverse()
    for _ in range(extra):
        representations.RemoveFirst()
    representations.Reverse()


def _delta(item: _Captured, tshapes: list, rows: list[tuple], rowed: set) -> "_Effect | None":
    """The sparse change between the input's state before and after: for each
    sub-shape whose state differs, its scalars and the representations appended,
    read past the count before. None when the change is one no delta expresses:
    a sub-shape added or removed, or standing at another's ordinal, a kind
    changed, representations taken away. A sub-shape two inputs share is rowed
    once; an input whose every change another input rowed has an empty effect."""
    if len(rows) != len(item.rows):
        return None
    changed: list[_Row] = []
    for ordinal, (before, after) in enumerate(zip(item.rows, rows)):
        if before == after:
            continue
        tshape = tshapes[ordinal]
        if tshape != item.tshapes[ordinal] or before[0] != after[0]:
            return None
        if item.known:
            _STATE[tshape] = after
        if tshape in rowed:
            continue
        appended: tuple = ()
        if before[3] is not None:
            if after[3] < before[3]:
                return None
            if after[3] > before[3]:
                appended = _appended(tshape, before[0], before[3])
        changed.append(_Row(tshape, before, after, appended))
        rowed.add(tshape)
    return _Effect(changed)


class _Row:
    """One sub-shape's state before and after an operation, settable either way."""

    __slots__ = ("tshape", "before", "after", "appended", "seq", "run")

    def __init__(self, tshape: Any, before: tuple, after: tuple, appended: tuple) -> None:
        self.tshape = tshape
        self.before = before
        self.after = after
        self.appended = appended
        self.seq = 0
        self.run = 0

    def set(self, state: tuple) -> None:
        """Set the sub-shape to ``state`` (``before`` or ``after``), touching only
        what differs between the two: the scalars set, the representations the
        operation appended put back or dropped from the tail."""
        tshape, before, after = self.tshape, self.before, self.after
        if before[1] != after[1]:
            tshape.Tolerance(state[1])
        if before[2] != after[2]:
            free, modified, checked, orientable, closed, infinite, convex = state[2]
            tshape.Free(free)
            tshape.Modified(modified)
            tshape.Checked(checked)
            tshape.Orientable(orientable)
            tshape.Closed(closed)
            tshape.Infinite(infinite)
            tshape.Convex(convex)
        if before[4] != after[4]:
            same_parameter, same_range, degenerated = state[4]
            tshape.SameParameter(same_parameter)
            tshape.SameRange(same_range)
            tshape.Degenerated(degenerated)
        if before[3] != after[3]:
            representations = _representations(tshape, before[0])
            if state is after:
                for representation in self.appended:
                    representations.Append(representation)
            else:
                _truncate(representations, before[3])
        _STATE[tshape] = state


class _Effect:
    """One operation's change to one input, as sparse rows, replayable."""

    __slots__ = ("rows", "id", "origin", "_geometric")

    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self._geometric: bool | None = None
        self.id = next(_EFFECT_IDS)
        # ``(key id, n, input index)`` of the memoized call that had this effect;
        # None for a call that ran plain.
        self.origin: tuple[int, int, int] | None = None

    def geometric(self) -> bool:
        """Whether the change reaches past the shapes' flags: a tolerance, a
        representation, an edge's parametric flags. Its rows never change: read once."""
        if self._geometric is None:
            self._geometric = any(row.before[1] != row.after[1] or row.before[3] != row.after[3] or row.appended
                                  or row.before[4] != row.after[4] for row in self.rows)
        return self._geometric

    def note(self, run_id: int, holder: "_Made | None" = None) -> None:
        """Into the ledger as applied by ``run_id``, the shapes already as the
        operation left them, each row indexed at the roots whose reset may undo it
        (``_rowed``); ``holder`` is the root of the input the effect was on."""
        for row in self.rows:
            row.seq = next(_SEQUENCE)
            row.run = run_id
            _LEDGER.setdefault(row.tshape, []).append(row)
            _rowed(row.tshape, holder)

    def apply(self, run_id: int, holder: "_Made | None" = None) -> None:
        for row in self.rows:
            row.set(row.after)
        self.note(run_id, holder)

    def forget(self) -> None:
        """Out of the ledger without touching the shapes: the memo no longer
        holds what these rows were applied to."""
        for row in self.rows:
            rows = _LEDGER.get(row.tshape)
            if rows is None:
                continue
            kept = [other for other in rows if other is not row]
            if kept:
                _LEDGER[row.tshape] = kept
            else:
                del _LEDGER[row.tshape]
