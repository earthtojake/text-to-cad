---
name: render
description: Renders photoreal images and videos of a text-to-cad model, a STEP or an xbf with Blender, for people to look at, such as a hero shot, a README picture, a product post, a turntable or a film of a model's motion or animation. Exports a GLB, loads it with cad.blender, lights and frames it in a bpy script that `cad run` runs, drafts in EEVEE and finishes in Cycles on the GPU, and can save a .blend. Not for checking geometry, which a snapshot does.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# Renders for people

A render is a picture for a person: a hero image, a README picture, a post, a turntable, a film of
a mechanism. The model goes to Blender as a GLB, loaded by `cad.blender.load`; the scene (camera,
lights, world, engine, output) is an ordinary Python script that imports `bpy`, Blender as a
Python module, and `cad run` runs it. Judge geometry with `cad model snapshot`, never with a
render: a render's lens, light and depth of field make it a poor measure, so never read a
dimension off one.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **A still of a model** | Export a GLB, write a `render.py` that loads it, `cad run render.py`. | [The script](#the-script), [scene script](references/scene-script.md) |
| **Draft, then a final** | An EEVEE draft at 1080p, looked at, before Cycles. | [Draft then final](references/shots.md#draft-then-final) |
| **A pose of a motion or a frame of an animation** | `model.play(name)` and the frame. | [Clips](#load-the-glb) |
| **A turntable** | The camera on an empty that turns once. | [Turntables](references/shots.md#turntables) |
| **A film of a motion or an animation** | `model.play(name)`, then an mp4. | [Films](references/shots.md#films) |
| **Motion blur, depth of field, a glow** | The scene's and the camera's settings; a keyed emission. | [Shots](references/shots.md) |
| **Choose looks** | `cad.build123d.materials` in the model. | [Looks](#looks) |
| **Give the person a .blend** | `bpy.ops.wm.save_as_mainfile` at the end of the script. | [A .blend](references/shots.md#a-blend-for-a-person) |
| **Use the GPU** | Cycles' device, chosen in the script. | [Engines](references/scene-script.md#engines-and-the-gpu) |

## Setup

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor
--check` explains any other failure, changing nothing; `cad doctor` repairs what it reports. Tell the
person any next step `cad setup` prints.

`cad run render.py` sees `import bpy` and gives the script cad's blender integration: an
environment on Python 3.13, the one Blender is built for, holding bpy 5.2.3 (Blender 5.2 LTS)
beside cad, made the first time and kept. The script imports what it likes of cad and build123d
beside bpy, so one script can build a model, export it and render it. Blender's own preferences,
add-ons and extensions folders are cad's, never the person's, so their Blender settings never load
into a run; every `cad run` shares them, so an extension or a preference one script installs or saves
is there for the next, and a script that needs one sets it up itself. bpy has no build for Intel Macs
or Linux on ARM, where `cad run` refuses such a script by name. A `--python` or a header's
`requires-python` that leaves 3.13 out is refused the same way; one that admits it (`--python 3.13`)
runs on the same environment as none. Nothing here starts the Blender app.

## Export the model

```bash
cad model export "$ID" scene.glb --tolerance 0.02 --angle 5
```

`ID` is the model's id (running its script prints it); a STEP or an xbf exports the same way
(`cad step export part.step scene.glb --tolerance 0.02 --angle 5`). The GLB is in metres, Z up once
imported, with the assembly's tree as nested empties, a PBR material per look, and each motion
and `animation()` as a clip. The viewer's mesh shows its facets in a path tracer or a close camera:
`--tolerance` (mm, absolute) and `--angle` (degrees, 1 to 28.5) mesh this file finer, for it alone.
The cost is triangles and seconds: a tenth of the tolerance is about three times the segments round
a curve and ten times the triangles of a doubly curved face. Start at 0.02 mm and 5 degrees for a
close-up of a hand-sized part and coarser for a large assembly seen whole, and export finer when a
draft shows facets. Say the file's size when it is large. Export again after every model change:
the GLB is a copy.

## The script

```python
# render.py: cad run render.py
import math
from pathlib import Path

import bpy
from mathutils import Vector

from cad.blender import load

HERE = Path(__file__).resolve().parent

bpy.ops.wm.read_factory_settings(use_empty=True)  # no person's startup file, no default cube
scene = bpy.context.scene
model = load(HERE / "scene.glb")  # every part where cad placed it

scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
aim = bpy.data.objects.new("aim", None)
aim.location = model.center
camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
camera.data.lens = 85
view = math.tan(camera.data.angle / 2) * min(1, scene.render.resolution_y / scene.render.resolution_x)
distance = model.size.length / 2 / view * 1.1  # the whole box in the frame's shorter side
camera.location = model.center + distance * Vector((1, -1, 0.6)).normalized()
camera.constraints.new("TRACK_TO").target = aim
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy, sun.rotation_euler = 3.0, (0.8, 0.2, 0.6)
for item in (aim, camera, sun):
    scene.collection.objects.link(item)
scene.camera = camera
scene.world = bpy.data.worlds.new("world")
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4

scene.render.engine = "BLENDER_EEVEE"  # a draft; "CYCLES" for the final
scene.render.filepath = str(HERE / "hero.png")
bpy.ops.render.render(write_still=True)
```

```bash
cad run render.py
```

The script is the scene: a camera, lights and a world are added in Python, every run starts from
an empty scene, and the outputs are wherever the script writes them. Arguments after the script's
name reach it as `sys.argv[1:]` (`cad run render.py --final`). Lights, the world, colour
management and a GPU are in [the scene script](references/scene-script.md).

## Load the GLB

Always load a GLB with `cad.blender.load`, never `bpy.ops.import_scene.gltf` alone. Blender's
importer poses every part a clip moves at that clip's first frame (a hinge written at 30 degrees
reads at the clip's start, with no error), leaves only the first clip live, and keys from frame 0.
`load` runs that importer, puts every node a clip moves back where the GLB places it, clears what
the import set playing, and plays the clip asked for. It opens any GLB, not only cad's: a node is
found by its place in the file, whatever Blender names its object.

| Call | What it gives |
| --- | --- |
| `load(path, clip=None, fps=24)` | Imports into the current scene and returns the model; `clip` plays one, `fps` keys its seconds (the scene's `render.fps`, with `render.fps_base` 1, set before the import, so a clip is in frames at that rate). |
| `model.root` | The document's root empty, at the origin, scale 0.001 (the parts are in mm below it). `model.roots` is every root's, for another tool's file with several. |
| `model.objects["arm/head"]` | Each node's object by its path below the root, as the GLB names it. A node with no name is under the name Blender gave its object; of two nodes with one name (KiCad names every lens `lens`), the last. |
| `model.nodes[7]` | Each node's object by its index in the file, which tells two of one name apart. A skin's joints are bones of the armature Blender makes for it (the skinned mesh's `parent`), not objects, and `load` never places a bone. |
| `model.clips` | Each clip by name: `kind` (`motion` or `animation`) and `duration` in seconds. |
| `model.box`, `model.center`, `model.size` | The world box of the pose cad wrote, in metres, for framing (the root sits at the document's origin, not the model's middle). |
| `model.play("sweep")` | That clip from frame 0, the scene's range 0 to its duration; `model.play(None)` stands every part where cad placed it. |
| `model.bounds()` | The world box at the current frame. |

A still of a pose is a clip's frame: `model.play("sweep")`, `scene.frame_set(24)`, render.

## Looks

The parts' looks are the model's: set them in the model, export again. `bd_materials` gives
physics and a look; `cad.build123d.materials` adds named looks Blender draws well (soldermask,
ENIG, anodized, powder coat, LED lenses, ...), each a scalar look with no texture maps
(the cad skill's colour and materials reference lists them). Blender's importer reads these of a look:

| Drawn | Not drawn |
| --- | --- |
| base colour, metalness, roughness, IOR, opacity, transmission, clear coat, sheen, specular, emission and its strength; iridescence in part | anisotropy (brushed metal draws plain), dispersion, a transmissive part's volume thickness (the light refracts through the real part), texture maps |

A transmissive look is written opaque, so a lens or a window refracts rather than fades. A
material is changed in the script only for the render's sake (a glow, a backdrop): the model
stays the source of every look.

## Engines

EEVEE (`BLENDER_EEVEE`) draws a 1080p frame in about 2 s: drafts, framing, light. Cycles with
OIDN denoising is the final, on the GPU where there is one (Metal, CUDA, OptiX, HIP, oneAPI) and
on the CPU where there is not, at minutes a frame. They disagree on translucent and glass parts
(an LED's glow ghosts through its diffuser in EEVEE), so a draft does not prove a final where glass
matters: draft those in Cycles at a few samples. Device setup is in
[the scene script](references/scene-script.md#engines-and-the-gpu).

## Check each change

| Change | Check |
| --- | --- |
| Camera, framing, lights, world | An EEVEE draft at 1080p, opened and looked at. |
| A pose, a clip's frame | `model.play(...)`, the frame, then a draft; for a moved part, its world position (`model.objects[path].matrix_world.translation`) against the model's. |
| Looks, glass, emission | A small Cycles draft (32 to 64 samples): EEVEE is not the final's evidence for them. |
| A turntable or a film | Three frames (first, middle, last) as EEVEE stills before the whole film. |
| The final | The final's frame against its draft: same framing, nothing missing. |

- An empty or black image is the camera inside, behind or too near the model, or no light: print
  `model.box` and the camera's location.
- A part in the wrong pose is a GLB imported without `load`, or a clip's frame taken before
  `model.play`.
- A render proves a picture, not a dimension: geometry is checked with `cad model snapshot`.

## What to expect

- The first `cad run` of a script that imports bpy downloads Blender's module once: about 262 MB
  on a Mac, 356 MB on Windows, 430 MB on Linux, and a Python 3.13 (65 MB). Later runs and other
  projects reuse it, and after an update of text-to-cad it is made again from what was downloaded.
- The first `import bpy` after that takes 11 to 18 s; then about 1.3 s.
- The first EEVEE render compiles its shaders (about 13 s); the first Cycles render on a Mac's GPU
  compiles its kernels once, about 3.5 minutes. Run it in the background with a long timeout.
- 1080p of a 537-part assembly on an M1 Max: EEVEE 64 samples 1.3 to 2.1 s; Cycles on the GPU at
  256 samples with OIDN 23 to 26 s, 4.4 GB of memory at peak; Cycles on the CPU 2.5 to 3.5
  minutes.
- Blender keeps a Cycles render's memory until its process ends: render each final in a run of its
  own rather than many in one long loop.
