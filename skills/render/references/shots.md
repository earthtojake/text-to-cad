# Shots

Read this for what a render script does past one still: a draft before a final, poses and clip
frames, turntables, films, motion blur, depth of field, a glow, and a `.blend` for a person. Every
snippet continues SKILL.md's skeleton (`scene`, `model`, `camera`, `aim`, `HERE`).

- [Draft then final](#draft-then-final)
- [Stills of a pose](#stills-of-a-pose)
- [Turntables](#turntables)
- [Films](#films)
- [Motion blur and depth of field](#motion-blur-and-depth-of-field)
- [Glow](#glow)
- [A .blend for a person](#a-blend-for-a-person)

## Draft then final

Look at a draft before every final. An EEVEE frame at the final's size takes about 2 s; read it
for framing, the camera's height, the light's direction and anything missing. Then the final in
Cycles, with the same scene. One script does both:

```python
import sys

final = "--final" in sys.argv[1:]
scene.render.engine = "CYCLES" if final else "BLENDER_EEVEE"
scene.render.filepath = str(HERE / ("hero.png" if final else "hero-draft.png"))
bpy.ops.render.render(write_still=True)
```

`cad run render.py` draws the draft; `cad run render.py --final` the final, once the draft is
right. Where glass, a lens, a diffuser or a glow matters, draft in Cycles at 32 to 64 samples too:
EEVEE draws those differently.

## Stills of a pose

A motion's pose or an animation's moment is a frame of its clip. Frames count from 0 at the
model's fps, so second `t` is frame `round(t * model.fps)`:

```python
model.play("explode")
scene.frame_set(round(1.5 * model.fps))  # 1.5 s in
bpy.ops.render.render(write_still=True)
```

`model.play(None)` puts every part back where cad placed it. Framing a pose that moves parts
outside the model's box takes `model.bounds()` at that frame.

## Turntables

The camera rides on an empty at the model's centre, and the empty turns once, at a constant
speed, so the film loops:

```python
import math
from bpy_extras import anim_utils

frames = 96  # 4 s at 24 fps
turn = bpy.data.objects.new("turn", None)
turn.location = model.center
scene.collection.objects.link(turn)
camera.parent = turn
camera.location = camera.location - turn.location  # the same place, now relative to the empty
turn.rotation_euler.z = 0.0
turn.keyframe_insert("rotation_euler", index=2, frame=0)
turn.rotation_euler.z = 2 * math.pi
turn.keyframe_insert("rotation_euler", index=2, frame=frames)
bag = anim_utils.action_get_channelbag_for_slot(turn.animation_data.action, turn.animation_data.action_slot)
for curve in bag.fcurves:
    for key in curve.keyframe_points:
        key.interpolation = "LINEAR"  # Blender's keys ease in and out unless told otherwise
scene.frame_start, scene.frame_end = 0, frames - 1  # the last frame is the first: left out
```

Then render it as a film (below). The camera's `TRACK_TO` constraint still aims it at `aim`.

## Films

A clip plays from frame 0 to its duration (`model.play` sets the scene's range); a turntable sets
its own. The film is one mp4 (H.264, High profile, yuv420p, which every player and site takes):

```python
model.play("sweep")
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.image_settings.media_type = "VIDEO"
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.filepath = str(HERE / "sweep.mp4")
bpy.ops.render.render(animation=True)
```

A clip plays once; a player loops the mp4, which runs smoothly only when the clip ends where it
starts (a motion that returns to its first configuration). Check three
frames as EEVEE stills (`scene.frame_set(...)` then `write_still=True`) before the whole film:
a film costs every frame's render, and a Cycles film on the CPU is hours.

## Motion blur and depth of field

```python
scene.render.use_motion_blur = True  # EEVEE and Cycles: a moving part and a turning camera blur
camera.data.dof.use_dof = True
camera.data.dof.focus_object = aim  # or a part: model.objects["arm/head"]
camera.data.dof.aperture_fstop = 2.8  # smaller is a shallower focus
```

Motion blur multiplies EEVEE's time a frame (a 24-frame 360p turntable with it took 17 s on an M1
Max). A small model at a shallow f-stop blurs almost everything: start at f/8 for a hand-sized part.

## Glow

A lit LED, a screen or a heater is the look's emission, keyed in the script. The importer gives
each look a Principled BSDF:

```python
led = model.objects["board/D1/lens"]
material = led.active_material.copy()  # this part alone; parts that share a look share a material
led.material_slots[0].link = "OBJECT"  # the look on the object, not on the mesh it shares
led.material_slots[0].material = material
bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
bsdf.inputs["Emission Color"].default_value = (1.0, 0.25, 0.05, 1.0)  # linear RGB
strength = bsdf.inputs["Emission Strength"]
for frame, value in ((0, 0.0), (12, 20.0), (24, 0.0)):  # off, on, off
    strength.default_value = value
    strength.keyframe_insert("default_value", frame=frame)
```

cad's GLB gives every instance of a part one mesh (72 LEDs, one lens), and a mesh's material is
every instance's, so `led.active_material = material` would light all 72: the slot is linked to the
object first. A steady glow needs no keys: set the strength once. The halo around a bright part is the
compositor's glare:

```python
tree = bpy.data.node_groups.new("glare", "CompositorNodeTree")
scene.compositing_node_group = tree
tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
layers, glare = tree.nodes.new("CompositorNodeRLayers"), tree.nodes.new("CompositorNodeGlare")
glare.inputs["Type"].default_value = "Bloom"
tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs["Image"], tree.nodes.new("NodeGroupOutput").inputs[0])
```

On a machine with no graphics driver, set `scene.render.compositor_device = "CPU"` first: the
compositor's default device is the GPU, and without one the render ends the process
([no graphics driver](scene-script.md#no-graphics-driver)).

## A .blend for a person

At the end of the script, save the scene for a person to open in Blender 5.2 and keep working on:

```python
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "scene.blend"))
```

It holds the imported model, its clips (the playing one assigned), the camera, the lights and the
render settings; the GLB is not needed beside it. The script stays the source: the `.blend`, like a
render, is an output that running it makes again, and is never committed.
