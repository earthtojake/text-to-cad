# The scene script

Read this for the parts of a render script past SKILL.md's skeleton: arguments, framing, lights,
the world, colour, the engines and the GPU.

- [Running it](#running-it)
- [Framing](#framing)
- [Lights and the world](#lights-and-the-world)
- [Colour](#colour)
- [Engines and the GPU](#engines-and-the-gpu)
- [No graphics driver](#no-graphics-driver)

## Running it

```bash
cad run render.py
cad run render.py --final
```

`cad run` runs the script with Python 3.13, bpy 5.2.3 and cad, so `from cad.blender import load`
imports, as does a module beside the script. Its arguments are `sys.argv[1:]`:

```python
import sys

final = "--final" in sys.argv[1:]
```

Start every script with `bpy.ops.wm.read_factory_settings(use_empty=True)`: an empty scene and
Blender's factory settings, so a run never depends on what a person's Blender saved. Nothing the
script does not write survives it, so a run is repeatable: export the model again, run again.

## Framing

The GLB's root empty stands at the model's origin, often a corner or a mounting face, so aim at
`model.center`, not at the root, and back the camera off by the box's size and the lens's field of
view:

```python
import math
from mathutils import Vector

aim = bpy.data.objects.new("aim", None)
aim.location = model.center
camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
camera.data.lens = 85  # mm: 50 for a wide view, 85 to 135 for a product shot
# camera.data.angle spans the frame's longer side: fit the box's sphere in the shorter one
view = math.tan(camera.data.angle / 2) * min(1, scene.render.resolution_y / scene.render.resolution_x)
distance = model.size.length / 2 / view * 1.1
camera.location = model.center + distance * Vector((1, -1, 0.6)).normalized()
camera.constraints.new("TRACK_TO").target = aim
```

`Vector((1, -1, 0.6))` is the direction from the model to the camera (X right, Y away, Z up): from the
front right and a little above. The box is of the pose cad wrote; a clip
that swings a part out needs `model.bounds()` at its widest frame. Units are metres throughout: a
100 mm part is 0.1 across.

## Lights and the world

A sun is one parallel light; its `energy` is in W/m² (3 to 5 for a bright day). For a product look,
three area lights around the model in place of the sun, their power in watts scaled by the square
of their distance so the light on the model is the same at any size (these numbers, with the world
below and the Standard view, light a white part without clipping it; draft and adjust):

```python
def area(name, direction, power, size):
    light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    light.data.energy, light.data.size = power * (distance ** 2), size * distance
    light.location = model.center + distance * Vector(direction).normalized()
    light.constraints.new("TRACK_TO").target = aim
    scene.collection.objects.link(light)

area("key", (1, -1, 1), 10, 0.5)  # the main light, above and in front
area("fill", (-1, -1, 0.3), 2.5, 1.0)  # softer, from the other side
area("rim", (0, 1, 0.8), 7.5, 0.3)  # behind, for the outline
```

The world is the light from everywhere else and the background behind the model:

```python
scene.world = bpy.data.worlds.new("world")
background = scene.world.node_tree.nodes["Background"]
background.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1.0)
background.inputs["Strength"].default_value = 0.4
scene.render.film_transparent = True  # a PNG with no background, for a page or a post
```

A floor to catch shadows is a plane under the box: `bpy.ops.mesh.primitive_plane_add(size=...,
location=(cx, cy, model.box[0].z))`.

## Colour

Blender 5.2 shows a render through AgX, which keeps bright highlights from clipping but mutes
saturated colours. For colours as the model and the CAD Viewer give them, use Standard:

```python
scene.view_settings.view_transform = "Standard"  # "AgX" for photographic highlights
```

## Engines and the GPU

EEVEE draws a frame in seconds and is the draft:

```python
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 64
```

Cycles traces paths and is the final. Choose the GPU where there is one, the first kind this build
offers that finds a device, and the CPU otherwise:

```python
scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"):
    try:
        prefs.compute_device_type = kind
    except TypeError:  # not offered on this build
        continue
    prefs.get_devices()
    if any(device.type == kind for device in prefs.devices):
        break
for device in prefs.devices:
    device.use = device.type != "CPU"
scene.cycles.device = "GPU" if any(device.use for device in prefs.devices) else "CPU"
scene.cycles.samples = 256
scene.cycles.use_denoising, scene.cycles.denoiser = True, "OPENIMAGEDENOISE"
```

Metal is the Mac's (Apple silicon), OptiX and CUDA NVIDIA's (OptiX first: it is faster on RTX
cards), HIP AMD's and oneAPI Intel's. Print `scene.cycles.device` and the devices in use in the
script's output, so a run on the CPU is never mistaken for one on the GPU. 128 to 512 samples
with OIDN make a clean final; a draft in Cycles (for glass, emission or a translucent part, where
EEVEE disagrees) takes 32 to 64.

On the CPU the sample count is the whole budget (a frame's time is its samples times a constant),
and a model with scalar looks (flat colours, no texture maps) needs few: the denoiser has only
edges and smooth gradients to keep. Measured on four cores at 960 x 540, a frame of painted,
metal, clear-coated and glass parts at 16 samples with OIDN took 14 s and differed from the one
at 512 samples (4 minutes) by 0.6 of 255 a pixel on average; at 32, 24 s and 0.5. Start a CPU
final at 16 to 32 samples, compare one frame against four times as many, and raise the count only
where that shows a difference (fine glass, a soft shadow's edge, depth of field).

## No graphics driver

EEVEE and the compositor's default device draw with the GPU through a graphics driver. A headless
Linux machine without one cannot start either: the render prints `Couldn't open libEGL.so.1` and
the process aborts (exit 134), with nothing raised in Python. Find out before rendering, and use
Cycles on the CPU for drafts as well as finals:

```python
import ctypes.util
import sys

headless = sys.platform == "linux" and ctypes.util.find_library("EGL") is None
scene.render.engine = "CYCLES" if final or headless else "BLENDER_EEVEE"
if headless:
    scene.render.compositor_device = "CPU"  # the default, "GPU", aborts the same way
    scene.cycles.samples = 16 if final else 8
```
