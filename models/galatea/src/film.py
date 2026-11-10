"""Galatea's film: a dark studio, a list of shots, and the cut.

    cad run src/film.py list                              the shots, their clips and lengths
    cad run src/film.py still SHOT [FRAME ...]            frames of a shot, into tmp/film/stills/
    cad run src/film.py shot SHOT [--from N] [--to M] [--step K]     a shot's frames, into tmp/film/SHOT/
    cad run src/film.py cut [--step K]                    every shot's frames as tmp/film/galatea.mp4

    --draft, --preview      at 960 x 540 or 640 x 360 with few samples: for framing, and for the motion
    --again                 render a frame that is there already

It renders the GLB of the robot (GLB/galatea.glb, which `cad model export` writes; the README has the
line), loaded by `cad.blender`, in Cycles. Everything it writes goes under tmp/, which Git ignores.

A shot is one clip of the model (a motion of `lib/poses.py`) seen by one camera move. The pelvis is
the mechanism's fixed link, so a clip as exported treads and crouches in the air; `plant` moves the
whole robot instead, frame by frame, so that the foot it stands on stays where it is on the floor.
Camera points are written where the part they look at stands at the zero pose (millimetres, as
everywhere in this model) and ride on a link (`on`), so a close-up finds its part in any pose.

The looks are the model's, with three changes made for the film's sake: the face shield is drawn as
smoked glass (the GLB carries it opaque), the two status lights are keyed, and in the shots that
open the robot up every skin is given a shader that wipes it away from the head down.
"""

import math
import subprocess
import sys
import time
from pathlib import Path

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Vector

from cad.blender import load

HERE = Path(__file__).resolve().parents[1]
GLB = HERE / "GLB" / "galatea.glb"
OUT = HERE / "tmp" / "film"
FPS = 24
# How well a frame is rendered: its size and its samples (a shot may ask for more). The folder a quality's frames go in ends in its name.
QUALITY = {"final": ((1600, 900), 14), "draft": ((960, 540), 10), "preview": ((640, 360), 6)}
FONT = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"            # the title's face, and the captions': Inter where it is installed
FONT_LIGHT = "/usr/share/fonts/opentype/inter/Inter-Light.otf"

# Labels (or their beginnings) of the parts that are skin: what the wipe takes away.
SKINS = ("panel_", "liner_", "helmet", "face_shield", "head_liner", "face_fascia", "foot_shell", "toe_cap", "hand_back",
         "trim_", "wordmark", "status_light")
WALK_SPEED = 0.25          # m/s: a foot travels 300 mm under the hip in a stance of 1.2 s (`lib/poses.py`)


def mm(point):
    return Vector(point) / 1000.0


# ---------------------------------------------------------------------------------------------
# The shots. Frames at 24 a second.
#
#   clip      the model's motion that plays, from the shot's frame `start` of it (None: the zero pose)
#   freeze    hold the clip at this frame of it for the whole shot
#   loop      repeat the clip (a walk)
#   plant     the link whose place on the floor is kept (a foot), or "walk": the robot travels forward
#   camera    [(frame, eye, target)] in mm at the zero pose, riding on the link `on` (None: the world)
#   lens, fstop   focal length in mm; an aperture gives depth of field, focused on the target
#   lights    [(frame, {light: level})]: `LIGHTS` names them; a level multiplies its power
#   face, chest   [(frame, strength)] of the two status lights
#   wipe      [(frame, height in mm)]: the skins are gone above that height; "off": no skins at all
#   turn      degrees the light rig is turned about the vertical: 0 puts the key before the robot's left
# ---------------------------------------------------------------------------------------------
ON = {"key": 1.0, "fill": 1.0, "rim_l": 1.0, "rim_r": 1.0, "top": 1.0, "pool": 1.0, "halo": 0.6}
LOW = {"key": 0.0, "fill": 0.0, "rim_l": 0.05, "rim_r": 0.05, "top": 0.0, "pool": 0.0, "halo": 0.0}
OPEN = {**ON, "key": 2.2, "fill": 3.2, "rim_l": 1.6, "rim_r": 1.6, "top": 2.0, "halo": 2.4}       # for the mechanism, black on black
SHOTS = {
    # The robot asleep on its feet, in the dark. Its face lights, then the studio's lights come up as it raises its head.
    "wake": dict(clip="wake", frames=96, plant="l_foot", lens=60, fstop=4.0, turn=-20, samples=20,
                 camera=[(0, (230, -1050, 1480), (0, -40, 1610)), (96, (430, -1620, 1540), (0, 0, 1545))],
                 lights=[(0, LOW), (24, LOW), (74, ON)],
                 face=[(0, 0.0), (10, 0.0), (13, 1.3), (15, 0.5), (20, 1.0)], chest=[(0, 0.0), (28, 0.0), (38, 1.0)]),
    # The whole figure, the camera going round it as it settles its weight on one leg.
    "hero": dict(clip="settle", frames=120, plant="r_foot", lens=45, turn=20,
                 camera=[(0, (-2700, -3500, 760), (0, 20, 900)), (60, (-200, -4420, 1000), (0, 20, 905)),
                         (120, (2500, -3650, 1240), (0, 20, 910))], lights=[(0, ON)]),
    # Close: the status light on the breastplate, up to the collar and the face.
    "chest": dict(clip="settle", freeze=110, frames=48, plant="r_foot", lens=85, fstop=4.0, on="chest", turn=20, samples=20,
                  camera=[(0, (330, -1010, 1370), (0, -95, 1436)), (48, (150, -1080, 1590), (0, -50, 1600))], lights=[(0, ON)]),
    # Close: the battery hatch and the name on it.
    "name": dict(clip="settle", freeze=110, frames=48, plant="r_foot", lens=100, fstop=2.8, on="chest", turn=200, samples=20,
                 camera=[(0, (-330, 640, 1330), (-40, 137, 1285)), (48, (250, 690, 1300), (30, 137, 1280))], lights=[(0, ON)]),
    # Close: down the leg, from the hip's cap to the knee.
    "leg": dict(clip="settle", freeze=110, frames=48, plant="r_foot", lens=100, fstop=4.0, on="l_thigh", turn=70, samples=20,
                camera=[(0, (900, -420, 1010), (150, -10, 915)), (48, (860, -520, 600), (105, -10, 520))], lights=[(0, ON)]),
    # The skins are wiped away from the head down.
    "scan": dict(clip="crouch", freeze=0, frames=78, plant="l_foot", lens=45, turn=-25, follow="pelvis",
                 camera=[(0, (2250, -3550, 1150), (0, 0, 900)), (162, (1650, -2950, 900), (0, -20, 860))],
                 lights=[(0, ON), (64, OPEN)], wipe=[(0, 1850), (6, 1850), (66, -40)]),
    # ... and the mechanism crouches: the camera's move carries on, turning down after it.
    "crouch": dict(clip="crouch", frames=84, plant="l_foot", lens=45, turn=-25, wipe="off", follow="pelvis",
                   camera=[(-78, (2250, -3550, 1150), (0, 0, 900)), (84, (1650, -2950, 900), (0, -20, 860))],
                   lights=[(0, OPEN)]),
    # Close on a leg from the side as it rises: the knee's crank and pushrod, the calf's drive and its rod.
    "linkage": dict(clip="crouch", start=50, frames=60, plant="l_foot", lens=70, fstop=5.6, turn=-110, wipe="off", follow="r_shin",
                    samples=20, camera=[(0, (-1500, -420, 500), (-82, 0, 520)), (60, (-1420, -120, 640), (-82, 0, 520))],
                    lights=[(0, OPEN)]),
    # The hand closes and opens.
    "hand": dict(clip="grasp", start=6, frames=60, plant="l_foot", lens=100, fstop=4.0, on="l_palm", turn=60, samples=20,
                 camera=[(0, (760, -500, 860), (212, -5, 790)), (60, (700, -620, 800), (212, -5, 785))], lights=[(0, ON)]),
    # It walks toward the camera, which gives ground before it.
    "walk": dict(clip="walk", loop=True, frames=96, plant="walk", lens=35, blur=True, turn=-15, follow="pelvis",
                 camera=[(0, (-1150, -3050, 420), (0, 0, 900)), (96, (-950, -3600, 500), (0, 0, 900))], lights=[(0, ON)]),
    # It bows; the lights go down on it, and its own stay.
    "bow": dict(clip="bow", frames=156, plant="l_foot", lens=50, turn=10,
                camera=[(0, (460, -5350, 1100), (0, -40, 880)), (156, (240, -4800, 1000), (0, -60, 880))],
                lights=[(0, ON), (102, ON), (126, LOW)], face=[(0, 1.0)], chest=[(0, 1.0)]),
}
ORDER = ("wake", "hero", "chest", "name", "leg", "scan", "crouch", "linkage", "hand", "walk", "bow")
# The title, which fades in over these frames of its shot, and the line under it.
TITLE = dict(shot="bow", text="G A L A T E A", frames=(118, 136), height=0.045, at=0.76,
             under="designed, modelled and checked in code with text-to-cad")
# Lines laid over the picture in the cut, low on the left: (shot, first frame, last frame, words). Each fades in and out.
CAPTIONS = [
    ("hero", 28, 110, "1.76 m    57 kg    44 driven joints"),
    ("scan", 12, 72, "689 parts in 73 links"),
    ("crouch", 8, 78, "33 RobStride drives, each its maker's own CAD model"),
    ("linkage", 6, 54, "the knee's drive rides at the hip: a crank, a pushrod, a parallelogram"),
    ("hand", 6, 54, "six degrees of freedom in each hand"),
]

# The lights: (azimuth from the robot's front toward its left, elevation, distance m, width m, height m, watts, colour).
LIGHTS = {
    "key": (-38, 36, 4.2, 1.8, 2.6, 105.0, (1.0, 0.97, 0.93)),
    "fill": (55, 14, 4.6, 3.0, 2.4, 30.0, (0.90, 0.94, 1.0)),
    "rim_l": (152, 22, 3.8, 0.45, 2.8, 120.0, (0.86, 0.92, 1.0)),
    "rim_r": (-150, 26, 3.8, 0.45, 2.8, 135.0, (0.86, 0.92, 1.0)),
    "top": (180, 80, 3.3, 1.4, 1.0, 70.0, (1.0, 0.98, 0.95)),
}
POOL, HALO = 260.0, 3600.0                       # the lamp over the floor and the spot on the wall, watts
GLOW = {"face": 16.0, "chest": 12.0}             # the status lights' emission at strength 1


# ---------------------------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------------------------
def fcurves(owner):
    data = owner.animation_data
    if data is None or data.action is None:
        return []
    bag = anim_utils.action_get_channelbag_for_slot(data.action, data.action_slot)
    return list(bag.fcurves) if bag else []


def interpolate(owner, mode="LINEAR"):
    for curve in fcurves(owner):
        for key in curve.keyframe_points:
            key.interpolation = mode


def eased(u):
    """A smooth step: a move that starts and ends at rest."""
    return u * u * (3.0 - 2.0 * u)


# ---------------------------------------------------------------------------------------------
# The model in the scene
# ---------------------------------------------------------------------------------------------
def parts(model, labels):
    """Mesh objects of the parts whose label starts with one of `labels`."""
    found = []
    for path, obj in model.objects.items():
        if path.split("/")[-1].startswith(labels):
            found += [o for o in (obj, *obj.children_recursive) if o.type == "MESH"]
    return list(dict.fromkeys(found))


def own_material(obj, slot, made):
    """Give one object's slot its own copy of the material it shares (`made` keeps one copy per material)."""
    source = slot.material
    if source not in made:
        made[source] = source.copy()
    slot.link = "OBJECT"                      # on the object, not on the mesh its twins share
    slot.material = made[source]
    return made[source]


def principled(material):
    return next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")


def looks(model, shot):
    """The film's three changes to the model's looks. Returns the nodes the shot keys."""
    made, keyed = {}, {}
    for obj in parts(model, ("face_shield",)):
        for slot in obj.material_slots:
            shader = principled(own_material(obj, slot, made))
            shader.inputs["Base Color"].default_value = (0.34, 0.36, 0.39, 1.0)        # smoked: a third of the light each way
            shader.inputs["Transmission Weight"].default_value = 1.0
            shader.inputs["Roughness"].default_value = 0.03
            shader.inputs["IOR"].default_value = 1.58
    for name, link in (("face", "head"), ("chest", "chest")):
        for obj in parts(model, ("status_light",)):
            if model.objects.get(f"{link}/status_light") not in (obj, obj.parent):
                continue
            for slot in obj.material_slots:
                shader = principled(own_material(obj, slot, {}))
                shader.inputs["Emission Color"].default_value = (0.86, 0.93, 1.0, 1.0)
                keyed[name] = shader.inputs["Emission Strength"]
    for name in ("face", "chest"):
        for frame, strength in shot.get(name, [(0, 1.0)]):
            keyed[name].default_value = strength * GLOW[name]
            keyed[name].keyframe_insert("default_value", frame=frame)
    wipe = shot.get("wipe")
    if wipe == "off":
        for obj in parts(model, SKINS):
            obj.hide_render = True
    elif wipe:
        level = wipe_shaders(model)
        for frame, height in wipe:
            level.default_value = height / 1000.0
            level.keyframe_insert("default_value", frame=frame)
        interpolate(level.id_data, "LINEAR")


def wipe_shaders(model):
    """Every skin given a shader that is clear above a height, with a lit edge at it. Returns the height's socket."""
    group = bpy.data.node_groups.new("wipe", "ShaderNodeTree")
    group.interface.new_socket("Keep", in_out="OUTPUT", socket_type="NodeSocketFloat")
    group.interface.new_socket("Edge", in_out="OUTPUT", socket_type="NodeSocketFloat")
    nodes, links = group.nodes, group.links
    level = nodes.new("ShaderNodeValue")
    level.name = "level"
    height = nodes.new("ShaderNodeSeparateXYZ")
    links.new(nodes.new("ShaderNodeNewGeometry").outputs["Position"], height.inputs[0])
    below = nodes.new("ShaderNodeMath")
    below.operation = "LESS_THAN"
    links.new(height.outputs["Z"], below.inputs[0])
    links.new(level.outputs[0], below.inputs[1])
    near = nodes.new("ShaderNodeMath")                 # within 5 mm under the level
    near.operation = "SUBTRACT"
    links.new(level.outputs[0], near.inputs[0])
    links.new(height.outputs["Z"], near.inputs[1])
    band = nodes.new("ShaderNodeMath")
    band.operation = "LESS_THAN"
    band.inputs[1].default_value = 0.005
    links.new(near.outputs[0], band.inputs[0])
    edge = nodes.new("ShaderNodeMath")
    edge.operation = "MULTIPLY"
    links.new(band.outputs[0], edge.inputs[0])
    links.new(below.outputs[0], edge.inputs[1])
    out = nodes.new("NodeGroupOutput")
    links.new(below.outputs[0], out.inputs["Keep"])
    links.new(edge.outputs[0], out.inputs["Edge"])

    made = {}
    for obj in parts(model, SKINS):
        for slot in obj.material_slots:
            if slot.material is None or slot.material in made.values():
                continue
            fresh = slot.material not in made
            material = own_material(obj, slot, made)
            if not fresh:
                continue
            tree = material.node_tree
            output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output)
            surface = output.inputs["Surface"].links[0].from_socket
            use = tree.nodes.new("ShaderNodeGroup")
            use.node_tree = group
            glow = tree.nodes.new("ShaderNodeEmission")
            glow.inputs["Color"].default_value = (1.0, 0.82, 0.55, 1.0)
            strength = tree.nodes.new("ShaderNodeMath")
            strength.operation = "MULTIPLY"
            strength.inputs[1].default_value = 60.0
            tree.links.new(use.outputs["Edge"], strength.inputs[0])
            tree.links.new(strength.outputs[0], glow.inputs["Strength"])
            lit = tree.nodes.new("ShaderNodeAddShader")
            tree.links.new(surface, lit.inputs[0])
            tree.links.new(glow.outputs[0], lit.inputs[1])
            mix = tree.nodes.new("ShaderNodeMixShader")
            tree.links.new(use.outputs["Keep"], mix.inputs["Fac"])
            tree.links.new(tree.nodes.new("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
            tree.links.new(lit.outputs[0], mix.inputs[2])
            tree.links.new(mix.outputs[0], output.inputs["Surface"])
    return level.outputs[0]


def animated(model):
    """Every object a clip moves."""
    return [obj for obj in bpy.data.objects if obj.animation_data and obj.animation_data.action]


def play(model, shot):
    """The shot's clip on the model: offset, looped or frozen as the shot asks. Returns the frames it spans."""
    scene = bpy.context.scene
    clip, frames = shot.get("clip"), shot["frames"]
    model.play(clip)
    if clip is None:
        return
    if "freeze" in shot:
        scene.frame_set(shot["freeze"])
        held = [(obj, obj.matrix_basis.copy()) for obj in animated(model)]
        for obj, basis in held:
            obj.animation_data_clear()
            obj.matrix_basis = basis
    else:
        for obj in animated(model):
            for curve in fcurves(obj):
                if shot.get("start"):
                    for key in curve.keyframe_points:
                        key.co.x -= shot["start"]
                        key.handle_left.x -= shot["start"]
                        key.handle_right.x -= shot["start"]
                if shot.get("loop"):
                    curve.modifiers.new("CYCLES")
                curve.update()
    scene.frame_start, scene.frame_end = 0, frames - 1


def plant(model, shot, floor):
    """Move the whole robot so that it stands on the floor: by the link `plant` names, kept where it is at
    the shot's first frame, or, walking, by going forward as fast as its feet go back."""
    scene, root, frames = bpy.context.scene, model.root, shot["frames"]
    root.rotation_mode = "QUATERNION"
    rest = root.matrix_world.copy()

    def lowest():
        bpy.context.view_layer.update()
        return model.bounds()[0].z

    if shot.get("plant") == "walk":
        low = min(lowest() for frame in range(0, int(FPS * 2.0)) if scene.frame_set(frame) is None)
        travel = WALK_SPEED * frames / FPS
        for frame, along in ((0, travel / 2), (frames, -travel / 2)):
            root.matrix_world = Matrix.Translation((0, along, floor - low)) @ rest
            root.keyframe_insert("location", frame=frame)
        interpolate(root, "LINEAR")
        return
    foot = model.objects[shot["plant"]]
    seen = []
    for frame in range(frames + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        seen.append((foot.matrix_world.copy(), None))
    scene.frame_set(0)
    down = Matrix.Translation((0, 0, floor - lowest()))
    target = down @ seen[0][0]
    for frame, (matrix, _) in enumerate(seen):
        root.matrix_world = target @ matrix.inverted() @ rest
        root.keyframe_insert("location", frame=frame)
        root.keyframe_insert("rotation_quaternion", frame=frame)
    interpolate(root, "LINEAR")


# ---------------------------------------------------------------------------------------------
# The studio
# ---------------------------------------------------------------------------------------------
def cove(radius=11.0, bend=3.5, height=9.0, around=96):
    """The studio's floor and wall as one surface: a flat disc that turns up into a wall all round, with no
    corner between them for a horizon to show in."""
    profile = [(radius * k / 6, 0.0) for k in range(7)]
    profile += [(radius + bend * math.sin(a), bend * (1 - math.cos(a))) for a in (math.radians(90 * k / 12) for k in range(1, 13))]
    profile += [(radius + bend, height)]
    vertices = [(0.0, 0.0, 0.0)]
    for r, z in profile[1:]:
        vertices += [(r * math.cos(2 * math.pi * k / around), r * math.sin(2 * math.pi * k / around), z) for k in range(around)]
    ring = lambda j, k: 1 + j * around + k % around
    faces = [(0, ring(0, k), ring(0, k + 1)) for k in range(around)]
    faces += [(ring(j, k), ring(j + 1, k), ring(j + 1, k + 1), ring(j, k + 1)) for j in range(len(profile) - 2) for k in range(around)]
    mesh = bpy.data.meshes.new("cove")
    mesh.from_pydata(vertices, [], faces)
    mesh.shade_smooth()
    return bpy.data.objects.new("cove", mesh)


def studio(scene, shot, centre):
    """A dark cove, the lights on a rig that turns with the shot, a pool of light on the floor and a glow on the wall."""
    floor = cove()
    floor.location = (centre.x, centre.y, 0.0)
    scene.collection.objects.link(floor)
    material = bpy.data.materials.new("cove")
    shader = principled(material)
    shader.inputs["Base Color"].default_value = (0.045, 0.047, 0.052, 1.0)
    shader.inputs["Roughness"].default_value = 0.5            # satin: no lamp shows in it
    shader.inputs["Specular IOR Level"].default_value = 0.25
    floor.data.materials.append(material)
    world = scene.world = bpy.data.worlds.new("world")
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)

    rig = bpy.data.objects.new("rig", None)
    rig.location = (centre.x, centre.y, 0.0)
    rig.rotation_euler.z = math.radians(shot.get("turn", 0.0))
    scene.collection.objects.link(rig)
    aim = bpy.data.objects.new("light_aim", None)
    aim.location = (0, 0, 1.05)
    aim.parent = rig
    scene.collection.objects.link(aim)
    lights = {}
    for name, (azimuth, elevation, distance, width, height, watts, colour) in LIGHTS.items():
        a, e = math.radians(azimuth), math.radians(elevation)
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        light.data.shape, light.data.size, light.data.size_y = "RECTANGLE", width, height
        light.data.color, light.data.spread = colour, math.radians(150)
        light.parent = rig
        light.location = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * distance + Vector((0, 0, 1.05))
        light.constraints.new("TRACK_TO").target = aim
        scene.collection.objects.link(light)
        lights[name] = (light.data, watts)

    def spot(name, at, toward, cone, watts, colour):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SPOT"))
        light.data.spot_size, light.data.spot_blend, light.data.shadow_soft_size = math.radians(cone), 1.0, 0.5
        light.data.color = colour
        target = bpy.data.objects.new(f"{name}_aim", None)
        light.location, target.location = at, toward
        light.constraints.new("TRACK_TO").target = target
        for item in (light, target):
            scene.collection.objects.link(item)
        lights[name] = (light.data, watts)

    # A pool of light on the floor under the robot: a lamp straight above, wide and soft, so the pool has no edge.
    pool = bpy.data.objects.new("pool", bpy.data.lights.new("pool", "AREA"))
    pool.data.shape, pool.data.size, pool.data.spread, pool.data.color = "DISK", 2.4, math.radians(75), (0.92, 0.95, 1.0)
    pool.location = centre + Vector((0, 0, 6.0))                       # an area lamp looks down its own -Z: straight down as it is
    scene.collection.objects.link(pool)
    lights["pool"] = (pool.data, POOL)
    # A glow on the wall behind the robot, as the camera sees it half way through the shot: from behind its feet, up the wall.
    keys = shot["camera"]
    eye = (mm(keys[0][1]) + mm(keys[-1][1])) / 2 if len(keys) == 2 else mm(keys[len(keys) // 2][1])
    away = Vector((centre.x - eye.x, centre.y - eye.y, 0.0)).normalized()
    spot("halo", centre + away * 4.5 + Vector((0, 0, 0.4)), centre + away * 14.5 + Vector((0, 0, 2.2)), 80, HALO, (0.72, 0.80, 1.0))

    for frame, levels in shot["lights"]:
        for name, (data, full) in lights.items():
            data.energy = full * levels.get(name, 1.0)
            data.keyframe_insert("energy", frame=frame)
    return rig


def camera_move(scene, model, shot, rest):
    """The camera and what it looks at, keyed through the shot. Its points are written at the zero pose: they
    ride on the link `on` names, as it stands when the shot begins, and the target alone rides on the link
    `follow` names frame by frame, so the camera turns after a part that moves."""
    def carry(link):
        return Matrix.Identity(4) if link is None else model.objects[link].matrix_world @ rest[link].inverted()

    aim = bpy.data.objects.new("aim", None)
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    camera.data.lens, camera.data.sensor_width = shot.get("lens", 50), 36.0
    camera.data.clip_start, camera.data.clip_end = 0.05, 300.0
    camera.constraints.new("TRACK_TO").target = aim
    for item in (aim, camera):
        scene.collection.objects.link(item)
    keys = shot["camera"]
    first, last = keys[0][0], keys[-1][0]
    scene.frame_set(0)
    bpy.context.view_layer.update()
    still = carry(shot.get("on"))
    for frame in range(shot["frames"] + 1):
        at = min(max(frame, first), last)
        k = max(i for i, key in enumerate(keys) if key[0] <= at)
        a, b = keys[k], keys[min(k + 1, len(keys) - 1)]
        u = 0.0 if a is b else (at - a[0]) / (b[0] - a[0])
        if len(keys) > 2:                                   # through several points: a smooth path (Catmull-Rom)
            p0, p3 = keys[max(k - 1, 0)], keys[min(k + 2, len(keys) - 1)]
            spline = lambda i: 0.5 * ((2 * Vector(a[i])) + (Vector(b[i]) - Vector(p0[i])) * u
                                      + (2 * Vector(p0[i]) - 5 * Vector(a[i]) + 4 * Vector(b[i]) - Vector(p3[i])) * u * u
                                      + (-Vector(p0[i]) + 3 * Vector(a[i]) - 3 * Vector(b[i]) + Vector(p3[i])) * u ** 3)
            eye, target = spline(1), spline(2)
        else:
            eye, target = Vector(a[1]).lerp(Vector(b[1]), u), Vector(a[2]).lerp(Vector(b[2]), u)
        moving = still
        if shot.get("follow"):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            moving = carry(shot["follow"])
        camera.location, aim.location = still @ mm(eye), moving @ mm(target)
        camera.keyframe_insert("location", frame=frame)
        aim.keyframe_insert("location", frame=frame)
    interpolate(camera, "LINEAR")
    interpolate(aim, "LINEAR")
    if shot.get("fstop"):
        camera.data.dof.use_dof, camera.data.dof.focus_object = True, aim
        camera.data.dof.aperture_fstop = shot["fstop"]
    scene.camera = camera
    scene.frame_set(0)
    return camera, aim


# ---------------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------------
def settings(scene, shot, quality):
    (width, height), samples = QUALITY[quality]
    draft = quality != "final"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = width, height, 100
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.device = "CPU"
    cycles.samples = samples if draft else shot.get("samples", samples)
    cycles.use_adaptive_sampling, cycles.adaptive_threshold, cycles.adaptive_min_samples = True, 0.05, 8
    cycles.use_denoising, cycles.denoiser = True, "OPENIMAGEDENOISE"
    cycles.denoising_input_passes, cycles.denoising_prefilter = "RGB_ALBEDO_NORMAL", "FAST"
    # A black studio gives little light back: two bounces, and enough passes through glass for the face behind its shield.
    cycles.max_bounces, cycles.diffuse_bounces, cycles.glossy_bounces = 4, 1, 2
    cycles.transmission_bounces, cycles.transparent_max_bounces = 4, 24 if shot.get("wipe") else 4
    cycles.caustics_reflective = cycles.caustics_refractive = False
    cycles.sample_clamp_indirect, cycles.blur_glossy = 4.0, 0.6
    scene.render.use_persistent_data = True
    scene.render.use_motion_blur = bool(shot.get("blur")) and not draft
    scene.render.motion_blur_shutter = 0.4
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    glare(scene)


def glare(scene):
    """A little bloom, so that a status light and the wipe's edge glow."""
    tree = bpy.data.node_groups.new("bloom", "CompositorNodeTree")
    scene.render.compositor_device = "CPU"           # no GPU is asked for: this renders on a machine without one
    scene.compositing_node_group = tree
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    layers, bloom = tree.nodes.new("CompositorNodeRLayers"), tree.nodes.new("CompositorNodeGlare")
    bloom.inputs["Type"].default_value = "Bloom"
    for name, value in (("Threshold", 4.0), ("Strength", 0.35), ("Size", 0.4)):
        if name in bloom.inputs:
            bloom.inputs[name].default_value = value
    tree.links.new(layers.outputs["Image"], bloom.inputs["Image"])
    tree.links.new(bloom.outputs["Image"], tree.nodes.new("NodeGroupOutput").inputs[0])


def build(name, quality):
    """The scene of one shot, ready to render."""
    if not GLB.exists():
        raise SystemExit(f"{GLB} is not there: export the model first (the README has the line)")
    shot = SHOTS[name]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    model = load(GLB, fps=FPS)
    rest = {path: obj.matrix_world.copy() for path, obj in model.objects.items() if "/" not in path}
    centre = Vector((model.center.x, model.center.y, 0.0))
    play(model, shot)
    if shot.get("plant"):
        plant(model, shot, 0.0)
    scene.frame_set(0)
    bpy.context.view_layer.update()
    looks(model, shot)
    studio(scene, shot, centre)
    camera_move(scene, model, shot, rest)
    settings(scene, shot, quality)
    scene.frame_start, scene.frame_end = 0, shot["frames"] - 1
    return scene, model


def render_frames(name, frames, quality, folder, again=False):
    """Frames of a shot as PNGs in `folder`; one that is there already is kept unless `again`."""
    folder.mkdir(parents=True, exist_ok=True)
    frames = [frame for frame in frames if again or not (folder / f"{frame:04d}.png").exists()]
    if not frames:
        return
    scene, _ = build(name, quality)
    for frame in frames:
        path = folder / f"{frame:04d}.png"
        started = time.time()
        scene.frame_set(frame)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print(f"{name} {frame:4d}: {time.time() - started:5.1f} s", flush=True)


# ---------------------------------------------------------------------------------------------
# The cut
# ---------------------------------------------------------------------------------------------
def folder_of(name, quality):
    return OUT / (name if quality == "final" else f"{name}-{quality}")


def cut(quality, step=1):
    """Every shot's frames in order as one mp4: in from black, the captions and the title laid over, out to
    black. With `step`, every step-th frame, played as slowly: a preview's cut."""
    reel = folder_of("reel", quality)
    reel.mkdir(parents=True, exist_ok=True)
    for old in reel.iterdir():
        old.unlink()
    count, missing, begins = 0, [], {}
    for name in ORDER:
        begins[name] = count
        for frame in range(0, SHOTS[name]["frames"], step):
            source = folder_of(name, quality) / f"{frame:04d}.png"
            if not source.exists():
                missing.append(f"{name} {frame}")
                continue
            (reel / f"{count:05d}.png").symlink_to(source)
            count += 1
    if missing:
        print(f"{len(missing)} frames are not rendered yet (the first: {missing[0]}); the cut has the rest, without its text")
    rate = FPS / step
    seconds, height = count / rate, QUALITY[quality][0][1]
    at = lambda shot, frame: begins[shot] / rate + frame / FPS            # when a shot's frame plays, seconds

    def text(words, size, colour, x, y, alpha, face=FONT):
        """One drawtext step. The words go by a file, so that nothing in them needs escaping."""
        page = reel / f"text{len(list(reel.glob('text*.txt')))}.txt"
        page.write_text(words)
        font = f"fontfile={face}:" if Path(face).exists() else ""
        return (f"drawtext={font}textfile={page}:expansion=none:fontsize={round(size * height)}:fontcolor={colour}:"
                f"shadowcolor=0x000000@0.5:shadowx={max(1, round(height / 540))}:shadowy={max(1, round(height / 540))}:"
                f"alpha='{alpha}':x={x}:y={y}")

    steps = ["fade=t=in:st=0:d=0.4"]
    if not missing:
        for shot, first, last, words in CAPTIONS:
            a, b = at(shot, first), at(shot, last)
            fade = f"0.85*min(1,min((t-{a:.3f})/0.35,({b:.3f}-t)/0.35))*between(t,{a:.3f},{b:.3f})"
            steps.append(text(words, 0.027, "0xDADCE0", "w*0.06", "h*0.885", fade, FONT_LIGHT))
        a, b = (at(TITLE["shot"], frame) for frame in TITLE["frames"])
        rise = f"min(1,max(0,(t-{a:.3f})/{b - a:.3f}))"
        steps.append(text(TITLE["text"], TITLE["height"] / 0.727, "0xCDB288", "(w-text_w)/2", f"h*{TITLE['at']}", rise))
        steps.append(text(TITLE["under"], 0.024, "0xDADCE0", "(w-text_w)/2", f"h*{TITLE['at'] + 0.085}", f"0.8*{rise}", FONT_LIGHT))
    steps.append(f"fade=t=out:st={seconds - 0.35:.3f}:d=0.35")
    film = OUT / ("galatea.mp4" if quality == "final" else f"galatea-{quality}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{rate:g}", "-i", str(reel / "%05d.png"), "-vf", ",".join(steps),
                    "-r", str(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(film)], check=True)
    print(f"wrote {film}: {count} frames, {seconds:.1f} s")


def main(arguments):
    options, words, k = {}, [], 0
    while k < len(arguments):                       # --from 10 --to 20 --step 4 take a number; the others stand alone
        word = arguments[k]
        if word in ("--from", "--to", "--step"):
            options[word], k = int(arguments[k + 1]), k + 1
        elif word.startswith("--"):
            options[word] = True
        else:
            words.append(word)
        k += 1
    quality = "draft" if "--draft" in options else "preview" if "--preview" in options else "final"
    step = options.get("--step", 1)
    if not words or words[0] == "list":
        total = 0
        for name in ORDER:
            shot = SHOTS[name]
            total += shot["frames"]
            print(f"{name:8s} {shot['frames']:4d} frames  {shot['frames'] / FPS:4.1f} s   clip {shot.get('clip')}")
        print(f"{total} frames, {total / FPS:.1f} s")
    elif words[0] == "still":
        frames = [int(word) for word in words[2:]] or [0]
        render_frames(words[1], frames, quality, folder_of(f"stills/{words[1]}", quality), "--again" in options)
    elif words[0] == "shot":
        last = SHOTS[words[1]]["frames"] - 1
        frames = range(options.get("--from", 0), options.get("--to", last) + 1, step)
        render_frames(words[1], frames, quality, folder_of(words[1], quality), "--again" in options)
    elif words[0] == "cut":
        cut(quality, step)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
