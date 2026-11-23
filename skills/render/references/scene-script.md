# The scene script

Read this for the parts of a render script past SKILL.md's skeleton: framing, lights, the world,
colour, Cycles' device and sample counts, and a machine with no graphics driver. Every snippet
continues the skeleton (`scene`, `model`, `camera`, `aim`, `distance`).

- [Framing](#framing)
- [Lights and the world](#lights-and-the-world)
- [Colour](#colour)
- [Engines and the GPU](#engines-and-the-gpu)
- [No graphics driver](#no-graphics-driver)

## Framing

The skeleton aims at `model.center`, not at the root: the GLB's root empty stands at the model's
origin, often a corner or a mounting face. `camera.data.angle` spans the frame's longer side, so
the skeleton's `view` fits the box's sphere in the shorter one and `distance` backs the camera off
by it. `Vector((1, -1, 0.6))` is the direction from the model to the camera (X right, Y away, Z
up): from the front right and a little above. A lens of 50 mm is a wide view, 85 to 135 a product
shot. A clip that swings a part out of the box needs `model.bounds()` at its widest frame.

## Lights and the world

A sun is one parallel light; its `energy` is in W/m² (3 to 5 for a bright day). For a product look,
three area lights around the model in place of the sun, their power in watts scaled by the square
of their distance so the light on the model is the same at any size. These numbers keep a white
part's lit faces just under full white in Cycles, with the world below and the Standard view; scale
the three together for a brighter or a darker look, and draft before the final:

```python
def area(name, direction, power, size):
    light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    light.data.energy, light.data.size = power * (distance ** 2), size * distance
    light.location = model.center + distance * Vector(direction).normalized()
    light.constraints.new("TRACK_TO").target = aim
    scene.collection.objects.link(light)

area("key", (1, -1, 1), 4, 0.5)  # the main light, above and in front
area("fill", (-1, -1, 0.3), 1, 1.0)  # softer, from the other side
area("rim", (0, 1, 0.8), 3, 0.3)  # behind, for the outline
```

The world is the light from everywhere else and the background behind the model:

```python
background = scene.world.node_tree.nodes["Background"]
background.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1.0)
background.inputs["Strength"].default_value = 0.4
scene.render.film_transparent = True  # a PNG with no background, for a page or a post
```

A floor to catch shadows is a plane under the box:

```python
bpy.ops.mesh.primitive_plane_add(
    size=10 * model.size.length, location=(model.center.x, model.center.y, model.box[0].z))
```

## Colour

Blender 5.2 shows a render through AgX, which keeps bright highlights from clipping but mutes
saturated colours. For colours as the model and the viewer give them, use Standard:

```python
scene.view_settings.view_transform = "Standard"  # "AgX" for photographic highlights
```

## Engines and the GPU

For a final in Cycles, choose the GPU where there is one, the first kind this build offers that
finds a device (OptiX before CUDA: it is faster on RTX cards), and the CPU otherwise:

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

Print `scene.cycles.device` and the devices in use, so a run on the CPU is never mistaken for one
on the GPU. 128 to 512 samples with OIDN make a clean final.

On the CPU the sample count is the whole budget (a frame's time is its samples times a constant),
and a model with scalar looks (flat colours, no texture maps) needs few: the denoiser has only
edges and smooth gradients to keep. Measured on four cores at 960 x 540, a frame of painted,
metal, clear-coated and glass parts at 16 samples with OIDN took 14 s and differed from the one
at 512 samples (4 minutes) by 0.6 of 255 a pixel on average; at 32, 24 s and 0.5. Start a CPU
final at 16 to 32 samples, compare one frame against four times as many, and raise the count only
where that shows a difference (fine glass, a soft shadow's edge, depth of field).

## No graphics driver

Nothing is raised in Python when EEVEE, or the compositor on its default device, ends the
process, so find out before rendering and use Cycles on the CPU for drafts as well as finals
(`final` is [draft then final](shots.md#draft-then-final)'s):

```python
import ctypes.util
import sys

headless = sys.platform == "linux" and ctypes.util.find_library("EGL") is None
scene.render.engine = "CYCLES" if final or headless else "BLENDER_EEVEE"
if headless:
    scene.render.compositor_device = "CPU"  # the default, "GPU", aborts the same way
    scene.cycles.samples = 16 if final else 8
```
