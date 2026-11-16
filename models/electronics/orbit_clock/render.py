"""Orbit's hero still, rendered by Blender: the clock exploded out of its stand, its LEDs showing 2:14:23.

    cad run render.py            # an EEVEE draft, RENDERS/hero-draft.png
    cad run render.py --final    # Cycles on the GPU, RENDERS/hero.png
    cad run render.py --blend    # either, and the scene as RENDERS/orbit.blend

It reads two GLBs, made first as the README's "Rebuild" says: the assembly with its explode,
GLB/orbit_assembly.glb (`cad run src/exports.py`), and the board as KiCad draws it, its copper, mask and
silkscreen, GLB/orbit.glb (`cad kicad_pcb export orbit.kicad_pcb --to glb -o GLB`). The assembly gives
every part and the explode; the board's GLB gives its layers, laid on the assembly's bare PCB. The script
is the source of the render: what it writes in RENDERS/ is made again by running it.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from cad.blender import load

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
final = "--final" in args
OUT = HERE / "RENDERS"

bpy.ops.wm.read_factory_settings(use_empty=True)  # no person's startup file, no default cube
scene = bpy.context.scene
model = load(HERE / "GLB" / "orbit_assembly.glb")

# The board's layers. KiCad's GLB is imported in the board's frame, in metres; the assembly's PCB holds its
# mesh in the same frame in mm, turned to glTF's Y up (its root turns it back). So the layers ride on the PCB,
# and with it the explode, scaled by 1000 and given that quarter turn. KiCad's parts are the assembly's
# again: only the layers are kept.
pcb = model.objects["board/orbit_PCB"]
layers = load(HERE / "GLB" / "orbit.glb").root
for item in list(layers.children):
    if item.type != "MESH":  # a footprint's 3D model
        bpy.data.batch_remove(item.children_recursive + [item])
y_up = Matrix.Rotation(math.pi / 2, 4, "X")
layers.parent, layers.matrix_parent_inverse, layers.matrix_basis = pcb, Matrix(), y_up @ Matrix.Scale(1000, 4)
pcb.hide_render = True

# The pose: the explode at its end, every part apart.
model.play("explode")
scene.frame_set(round(4.6 * model.fps))
low, high = model.bounds()
center, size = (low + high) / 2, high - low


# 2:14:23 on the rings, on the half the baffle leaves in view: D1-D60 the minutes from 12 o'clock clockwise,
# D61-D72 the hours.
def glow(designator: str, colour: tuple, strength: float) -> None:
    lens = model.objects[f"board/{designator}/WS2812B-2020/lens"]
    material = lens.active_material.copy()  # this LED alone: all 72 lenses share one look and one mesh,
    lens.material_slots[0].link = "OBJECT"  # so the look is the object's, not the mesh's
    lens.material_slots[0].material = material
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Emission Color"].default_value = (*colour, 1.0)
    bsdf.inputs["Emission Strength"].default_value = strength

for minute in range(60):
    glow(f"D{minute + 1}", (0.05, 0.2, 1.0), 8.0 if minute % 5 == 0 else 2.5)  # the dial, brighter at the hours
glow("D15", (0.0, 1.0, 0.5), 30.0)  # minute 14
glow("D24", (1.0, 0.05, 0.3), 30.0)  # second 23
for hour in range(12):
    glow(f"D{61 + hour}", (1.0, 0.35, 0.05), 30.0 if hour == 2 else 2.5)  # the hour, warm

scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
aim = bpy.data.objects.new("aim", None)
aim.location = center
camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
camera.data.lens = 85
view = math.tan(camera.data.angle / 2) * min(1, scene.render.resolution_y / scene.render.resolution_x)
distance = size.length / 2 / view * 0.9
camera.location = center + distance * Vector((1.9, -1, 0.45)).normalized()  # the face is -Y: into the gaps
camera.constraints.new("TRACK_TO").target = aim
for item in (aim, camera):
    scene.collection.objects.link(item)
scene.camera = camera


def area(name: str, direction: tuple, power: float, size: float) -> None:
    light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    light.data.energy, light.data.size = power * (distance ** 2), size * distance
    light.location = center + distance * Vector(direction).normalized()
    light.constraints.new("TRACK_TO").target = aim
    scene.collection.objects.link(light)


area("key", (1, -1, 1), 10, 0.5)
area("fill", (-1, -1, 0.3), 2.5, 1.0)
area("rim", (0, 1, 0.8), 7.5, 0.3)
bpy.ops.mesh.primitive_plane_add(size=20 * size.length, location=(center.x, center.y, low.z))  # the desk
desk = bpy.data.materials.new("desk")
desk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.04, 0.04, 0.045, 1.0)
desk.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35
bpy.context.object.data.materials.append(desk)
scene.world = bpy.data.worlds.new("world")
background = scene.world.node_tree.nodes["Background"]
background.inputs["Color"].default_value = (0.03, 0.035, 0.045, 1.0)
background.inputs["Strength"].default_value = 0.5
scene.view_settings.view_transform = "Standard"

if final:
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
    print("cycles on", scene.cycles.device, [device.name for device in prefs.devices if device.use])
else:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
scene.render.filepath = str(OUT / ("hero.png" if final else "hero-draft.png"))
bpy.ops.render.render(write_still=True)
if "--blend" in args:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "orbit.blend"))
