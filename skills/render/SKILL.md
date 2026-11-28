---
name: render
description: Renders photoreal images and videos of a text-to-cad model, a STEP or an xbf with Blender - a hero shot, a product or README picture, a turntable, or a film of a model's motion. Use when the person wants a picture or a video for people to look at. Not for checking geometry, which the cad skill's snapshot does.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# Renders for people

A render is a picture for a person: a hero image, a README picture, a turntable, a film of a
mechanism. The model goes to Blender as a GLB, loaded by `cad.blender.load`; the scene (camera, lights,
world, engine, output) is an ordinary Python script that imports `bpy`, Blender as a Python module,
and `cad run` runs it. Geometry is judged with `cad model snapshot`, never a render: lens, light and
depth of field make it a poor measure.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| A still of a model | Export a GLB, write a `render.py` that loads it, `cad run render.py` | [The script](#the-script), [scene script](references/scene-script.md) |
| Draft, then a final | An EEVEE draft at 1080p, looked at, before Cycles | [Draft then final](references/shots.md#draft-then-final) |
| A pose, or a frame of an animation | `model.play(name)` and the frame | [Load the GLB](#load-the-glb) |
| A turntable | The camera on an empty that turns once | [Turntables](references/shots.md#turntables) |
| A film of a motion or an animation | `model.play(name)`, then an mp4 | [Films](references/shots.md#films) |
| Motion blur, depth of field, a glow | The scene's and the camera's settings; a keyed emission | [Shots](references/shots.md) |
| Looks and materials | Set in the model, exported again | [Looks](#looks) |
| A `.blend` for the person | `bpy.ops.wm.save_as_mainfile` at the end of the script | [A .blend](references/shots.md#a-blend-for-a-person) |
| The GPU, or a machine with no graphics driver | Cycles' device, chosen in the script | [Engines](references/scene-script.md#engines-and-the-gpu), [no driver](references/scene-script.md#no-graphics-driver) |

## Setup

Written for `cad==0.11.19`. Before first use in a chat, run `cad --version`. If it fails, or `cad` is missing or older
than 0.11.12, run `uv tool install --force cad`. If it is older than the release this skill was written for, run
`cad update`.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

`cad run` sees `import bpy` and makes the script an environment with bpy 5.2.3 (Blender 5.2 LTS) on
Python 3.13 beside cad, once: a download of 260 to 430 MB, so the first run is slow. Nothing starts the
Blender app, and the person's own Blender settings and add-ons never load. bpy has no build for Intel
Macs or Linux on ARM, where `cad run` refuses the script by name.

## Export the model

```bash
cad model export "$ID" scene.glb --tolerance 0.02 --angle 5
```

`$ID` is the model's id; a STEP or an xbf exports the same way (`cad step export part.step scene.glb
--tolerance 0.02 --angle 5`). The GLB is in metres, Z up once imported, with the assembly's tree as
nested empties, a PBR material per look, and each motion and `animation()` as a clip. `--tolerance`
(mm) and `--angle` (degrees) mesh it finer than the viewer's, so a close camera shows no facets, at the
cost of triangles: start near 0.02 mm and 5 degrees for a close-up of a hand-sized part, coarser for a
large assembly seen whole. The GLB is a copy: export again after every model change.

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

The script is the scene: every run starts empty and adds its camera, lights and world in Python.
Arguments after the script's name reach it as `sys.argv[1:]`. Lights, the world, colour management and
the GPU are in [the scene script](references/scene-script.md).

## Load the GLB

Load with `cad.blender.load`, never `bpy.ops.import_scene.gltf` alone: Blender's importer poses every
part a clip moves at that clip's first frame, with no error, leaves only the first clip live and keys
from frame 0. `load` runs that importer, puts every node back where the GLB places it, and plays the
clip asked for. It opens any GLB, not only cad's.

| Call | Gives |
| --- | --- |
| `load(path, clip=None, fps=24)` | Imports into the current scene and returns the model; `clip` plays one, `fps` keys its seconds. Give a film's rate here: `render.fps` set after the import plays every clip at the wrong speed, with no error |
| `model.root` | The document's root empty, at the origin, scale 0.001 (parts are in mm below it); `model.roots` for a file with several |
| `model.objects["arm/head"]` | A node's object by its path below the root, as the GLB names it; of two nodes with one name it is the last (`model.nodes[i]` reaches each) |
| `model.nodes[7]` | A node's object by its index in the file, which tells two of one name apart |
| `model.clips` | Each clip by name: `kind` (`motion` or `animation`) and `duration` in seconds |
| `model.box`, `model.center`, `model.size` | The world box of the pose cad wrote, in metres, for framing |
| `model.play("sweep")` | That clip from frame 0, the scene's range set to its duration; `model.play(None)` stands every part as placed |
| `model.bounds()` | The world box at the current frame |

A still of a pose is a clip's frame: `model.play("sweep")`, `scene.frame_set(24)`, render.

## Looks

A part's look is the model's: set it there and export again. `bd_materials` gives physics and a look;
`cad.build123d.materials` adds named looks Blender draws well (solder mask, ENIG, anodized, powder
coat, LED lenses). Blender's importer draws base colour, metalness, roughness, IOR, opacity,
transmission, clear coat, sheen, specular and emission; it does not draw anisotropy (brushed metal
draws plain), dispersion or texture maps.

A Blender material is named by the model's look (`bpy.data.materials["frame_black"]`), so a script can
restyle a look wherever it is worn, and the physical material it is a look of is its custom property
(`material["cad"]["material"]`). Change one in the script only for the render's sake (a glow, a
backdrop). A transmissive look's base colour tints what passes through, so smoked glass written as a
near-black colour with partial transmission renders black: write glass as `transmission=1` with the
tint as its colour, and judge it in a Cycles draft.

## Engines

EEVEE (`BLENDER_EEVEE`) draws a 1080p frame in seconds: drafts, framing, light. Cycles with OIDN
denoising is the final, on the GPU where there is one, at minutes a frame. They disagree on glass and
translucent parts, so draft those in Cycles at a few samples.

EEVEE needs a graphics driver. On a machine without one (a headless Linux server or container), an
EEVEE render prints `Couldn't open libEGL.so.1` and ends the process with exit 134 and no Python
exception, as does the compositor on its default device: draft in Cycles at 8 to 16 samples and set
`scene.render.compositor_device = "CPU"`
([no graphics driver](references/scene-script.md#no-graphics-driver)).

## Check each change

| Change | Check |
| --- | --- |
| Camera, framing, lights, world | An EEVEE draft at 1080p, opened and looked at |
| A pose, a clip's frame | `model.play(...)`, the frame, then a draft; a moved part's world position (`model.objects[path].matrix_world.translation`) against the model's |
| Looks, glass, emission | A small Cycles draft (32 to 64 samples) |
| A turntable or a film | Three frames (first, middle, last) as stills before the whole film |
| The final | Against its draft: same framing, nothing missing |

- An empty or black image is the camera inside, behind or too near the model, or no light: print
  `model.box` and the camera's location.
- A part in the wrong pose is a GLB imported without `load`, or a frame taken before `model.play`.
- First runs are slow once each: `import bpy` (10 to 20 s), EEVEE's shaders (about 13 s), Cycles'
  GPU kernels on a Mac (minutes). Run a final in the background with a long timeout, and each final in
  a run of its own, since Blender keeps a Cycles render's memory until its process ends.
