"""Open in's Blender: the script a person's own Blender runs (``--python``) when they open a GLB or an STL in it.

Blender opens only its own ``.blend`` files from its command line: handed a GLB or an STL it says the file format is
not supported. So ``apps.open_file`` starts it as ``blender --python <this file> -- <file>``. This imports the file,
then removes every object the startup scene held -- the default cube, light and camera, or whatever a person's own
startup file puts there -- and the data only those objects used, so the model is opened alone, as in a new file. The
rest of the startup file and every preference stay the person's own: layout, world, render settings, add-ons, keymap,
theme and render device. (``--factory-startup`` would give a clean scene too, but it ignores the person's preferences,
their GPU render device among them.) It then selects what it imported and frames it in every 3D viewport once the
window is up.

The file is the one argument after ``--``, read from ``sys.argv``: the path is data, never code. When it cannot open
the file -- none named, not a GLB, glTF or STL, not there, no importer in this Blender for it, or the importer failed --
the startup scene is left exactly as it was and the reason is shown in Blender itself, where the person is looking (the
viewer started Blender detached and has already answered): a dialog once the window is up, a text block named
``Open in Blender`` in the file, and a line on Blender's console.

The glTF importer poses a part that a clip moves at that clip's first frame, the first clip's where several move it:
for opening a file that is the model, at the start of its first clip. Nothing here plays or changes a clip.

Blender 2.80 and later. It runs on Blender's bundled Python, where nothing of the package is installed, so it uses
Blender's Python API (``bpy``) and the standard library alone, and every line of it is valid on Python 3.7, the oldest
a Blender it supports bundles (2.80): no annotation at all, nothing newer than 3.7. Each API that came later is asked
for: STL's built-in importer (``wm.stl_import``, 3.6) before the add-on's (``import_mesh.stl``), and a context
override (``temp_override``, 3.2) before the dictionary that older Blenders take.

MIT, as the rest of the package. It runs only inside Blender; nothing of the package imports it.
"""

import importlib
import os
import sys

# Blender's own module, imported only where Blender runs this file (as ``__main__``, below): importing the module
# elsewhere, as anything that walks the package does, loads nothing of Blender's.
bpy = None

# What each extension is imported by, the first of its operators this Blender has: glTF's add-on (enabled by default
# since 2.80), STL's built-in importer (3.6) and else its add-on (enabled by default in the Blenders before it).
IMPORTERS = {".glb": ("import_scene.gltf",), ".gltf": ("import_scene.gltf",),
             ".stl": ("wm.stl_import", "import_mesh.stl")}
KINDS = {".glb": "glTF", ".gltf": "glTF", ".stl": "STL"}

# Where a failure is written in the file, and the dialog's title.
TITLE = "Open in Blender"

# The startup scene's objects are renamed out of the importer's way while it runs, so the model's own names are
# never suffixed (a part named "Cube" stays "Cube"), and back if the import fails.
ASIDE = "open_in_blender aside "

# The lines the dialog shows (``dialog``).
SAID = []


def requested(argv):
    """The file named after ``--``: the one argument there, else None. Blender leaves its whole command line in
    ``sys.argv`` and parses nothing after ``--``, so the path is passed as it is, whatever it holds."""
    if "--" not in argv:
        return None
    rest = argv[argv.index("--") + 1:]
    return rest[0] if len(rest) == 1 and rest[0] else None


def operators(ops, modules):
    """The operators of ``modules`` this Blender has registered, as ``"module.name"``. ``dir(bpy.ops.<module>)``
    lists the registered ones (``_bpy.ops.dir()``, in every Blender from 2.80); an attribute of ``bpy.ops.<module>``
    is no test, being a callable for any name at all."""
    return {"%s.%s" % (module, name) for module in modules for name in dir(getattr(ops, module))}


def importer(extension, have):
    """The operator that imports a file of ``extension`` (``"module.name"``): the first of ``IMPORTERS``' for it in
    ``have``, else None."""
    return next((name for name in IMPORTERS.get(extension.lower(), ()) if name in have), None)


def refusal(argv, isfile, have):
    """Why the file ``argv`` names cannot be opened (a sentence for the person), else None: ``isfile`` says whether a
    path is a file, ``have`` holds the operators this Blender has."""
    path = requested(argv)
    if path is None:
        return "No file was named after -- on Blender's command line."
    extension = os.path.splitext(path)[1].lower()
    if extension not in IMPORTERS:
        return "%s is not a GLB, glTF or STL file." % path
    if not isfile(path):
        return "%s is not there." % path
    if importer(extension, have) is None:
        return ("This Blender has no %s importer: enable its %s import add-on (Edit > Preferences > Add-ons), then "
                "open the file again." % (KINDS[extension], KINDS[extension]))
    return None


def in_window(window, area, region, call, *args, **kwargs):
    """``call(*args, **kwargs)`` with ``window`` (and ``area`` and ``region``, where not None) as its context: through
    ``temp_override`` where Blender has it (3.2), else as the dictionary an operator takes first (until 4.0)."""
    given = {"window": window, "screen": window.screen, "area": area, "region": region}
    given = {key: value for key, value in given.items() if value is not None}
    if hasattr(bpy.context, "temp_override"):
        with bpy.context.temp_override(**given):
            return call(*args, **kwargs)
    return call(given, *args, **kwargs)


def set_aside(objects):
    """Rename ``objects`` and their data out of the importer's way: what puts the names back."""
    named = []
    for item in [*objects, *{obj.data for obj in objects if obj.data is not None}]:
        named.append((item, item.name))
        item.name = ASIDE + item.name
    return named


def put_back(named):
    for item, name in named:
        item.name = name


def remove(objects):
    """Remove ``objects``, and the data only they used."""
    used = {obj.data for obj in objects if obj.data is not None}
    bpy.data.batch_remove(list(objects))
    bpy.data.batch_remove([data for data in used if data.users == 0])


def bring_in(name, path):
    """Import the file at ``path`` with the operator ``name`` (``"module.name"``): the objects it made. Raises when
    the importer fails or cancels."""
    module, operator = name.split(".")
    before = set(bpy.data.objects.keys())
    try:
        done = getattr(getattr(bpy.ops, module), operator)(filepath=path)
        if "FINISHED" not in done:
            raise RuntimeError("the importer stopped (%s)" % ", ".join(sorted(done)))
    except Exception:
        remove([obj for obj in bpy.data.objects if obj.name not in before])  # what it made before it failed
        raise
    return [obj for obj in bpy.data.objects if obj.name not in before]


def select(view_layer, objects):
    """Select ``objects``' roots alone, the first of them active."""
    made = {obj.name for obj in objects}
    roots = [obj for obj in objects if obj.parent is None or obj.parent.name not in made]
    for obj in view_layer.objects:
        obj.select_set(False)
    for obj in roots:
        obj.select_set(True)
    if roots:
        view_layer.objects.active = roots[0]


def frame():
    """Frame the selection in every 3D viewport of every window: once, from a timer, the window being up by then.
    A viewport that cannot is left as it was."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            region = next((region for region in area.regions if region.type == "WINDOW"), None)
            if area.type != "VIEW_3D" or region is None:
                continue
            try:
                in_window(window, area, region, bpy.ops.view3d.view_selected)
            except Exception as error:  # noqa: BLE001 - framing is a nicety; the model is open either way
                print("open_in_blender: could not frame the model: %s" % error, file=sys.stderr)
    return None  # a timer that returns None runs once


def dialog(message):
    """Blender's operator that shows ``message`` in a dialog where it is invoked, registered on first use."""
    SAID[:] = message.split("\n")
    if "open_in_blender.said" not in operators(bpy.ops, ("open_in_blender",)):
        def draw(self, context):
            for number, line in enumerate(SAID):
                self.layout.label(text=line, icon="ERROR" if number == 0 else "NONE")

        bpy.utils.register_class(type("OPEN_IN_BLENDER_OT_said", (bpy.types.Operator,), {
            "bl_idname": "open_in_blender.said", "bl_label": TITLE, "bl_options": {"INTERNAL"}, "draw": draw,
            "execute": lambda self, context: {"FINISHED"},
            "invoke": lambda self, context, event: context.window_manager.invoke_props_dialog(self, width=560)}))
    return bpy.ops.open_in_blender.said


def show(message):
    """A timer's: the dialog saying ``message`` in Blender's first window, once."""
    windows = list(bpy.context.window_manager.windows)
    if windows:
        try:
            in_window(windows[0], None, None, dialog(message), "INVOKE_DEFAULT")
        except Exception as error:  # noqa: BLE001 - the text block and the console still say it
            print("open_in_blender: could not show the dialog: %s" % error, file=sys.stderr)
    return None


def say(message):
    """Tell the person why their file was not opened: on the console, in the text block ``TITLE``, and in a dialog
    once the window is up (no dialog without one, as in the background)."""
    message = "Open in Blender did not open the file.\n" + message
    print("open_in_blender: " + message.replace("\n", " "), file=sys.stderr)
    text = bpy.data.texts.get(TITLE) or bpy.data.texts.new(TITLE)
    text.clear()
    text.write(message + "\n")
    if not bpy.app.background:
        bpy.app.timers.register(lambda: show(message), first_interval=0.5)


def main(argv):
    """Open the file ``argv`` names: imported, then the startup scene's objects removed, the import selected and
    framed. When it cannot, the scene is as it was and ``say`` tells the person why."""
    have = operators(bpy.ops, {name.split(".")[0] for names in IMPORTERS.values() for name in names})
    reason = refusal(argv, os.path.isfile, have)
    if reason is not None:
        say(reason)
        return
    path = requested(argv)
    context = bpy.context
    startup = list(context.scene.objects)
    named = set_aside(startup)
    try:
        made = bring_in(importer(os.path.splitext(path)[1], have), path)
    except Exception as error:  # noqa: BLE001 - whatever the importer raised, the person is told and keeps the scene
        put_back(named)
        say("Blender could not import %s:\n%s" % (path, str(error).strip()))
        return
    if not made:
        put_back(named)
        say("%s holds nothing Blender imports." % path)
        return
    select(context.view_layer, made)  # first: a view layer lists a removed object (as None) until it is next synced
    remove(startup)
    if not bpy.app.background:
        bpy.app.timers.register(frame, first_interval=0.2)


if __name__ == "__main__":  # Blender's --python runs a file as __main__
    bpy = importlib.import_module("bpy")
    main(sys.argv)
