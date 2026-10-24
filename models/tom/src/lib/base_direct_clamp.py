"""RoArm-inspired mounting return with independent M3 attachment screws.

The current assembly uses two identical 3.175 mm 5052 base/carrier plates.
The aluminum bracket has a 76.175 x 57.2 mm upper return, a 40 mm wall/lower jaw,
and four M3 screws on a 39.6 x 47.8 mm pitch. Standard M2.5 screws
separately attach the bottom Pi posts to the lower aluminum plate.
Clamp dimensions are Tom design choices, not measured RoArm dimensions.
The current Tom2 assembly uses M3x6 screws through a 3.175 mm plate into
the 3.175 mm 5052 return (legacy construction screws are revised upstream).
The modeled 2.6 mm pilot bores follow SendCutSend's M3 tapping chart.
Threads are not tessellated. Nominal M3x6 engagement remains 2.825 mm.
The internal back-wall datum remains X81.35 mm with the thinner bend tooling.
All four Pi recesses are concentric R4.5 with flush 40 mm neck transitions.
Driver and Pi Zero access cuts clear M2.5 socket heads by at least 1 mm radially.
The separate M8 steel nut needs mechanical retention or a wrench while
tightening; do not weld it to aluminum. Puck retention remains simplified.
This is checked fit geometry, not a qualified clamp load rating.
"""
from pathlib import Path
import build123d as b
from cadgen import read_step
from lib.booleans import as_single_shape as one
from lib.materials import ALUMINUM_5052_COLOR, SCREW_COLOR
from base.common_base_plate import common_base_plate
from lib.common_base_plate import SUPPORT_XY, WIDTH, THICKNESS, MOUNT_XY, SERVO_SHIFT_X, CLAMP_ATTACH_XY, ADAPTER_XY, PI_ZERO_XY, OUTER_RADIUS
from lib.common_base_plate import SERVO_SHIFT_X  # noqa: F401  read as bay.SERVO_SHIFT_X by the stage chain
from lib.pi_shared_stack import STACK_HEIGHT, shared_stack
from hardware.hex_socket_cap import hex_socket_m3x5

CLAMP_T = 3.175  # SendCutSend ALU-125, 5052 H32 aluminum; rush option.
CLAMP_R = 3.175  # ALU-125 effective inside bend radius.
CLAMP_WIDTH = 40.0  # Flush with the straight neck between the Pi corner cuts.
CLAMP_TOP_WIDTH = WIDTH  # Full plate-body width, excluding mounting ears.
CLAMP_FRONT = 20.0  # lower jaw
CLAMP_FLANGE_FRONT = 2.0
CLAMP_SCREW_X = 40.0
# Keep the inner back-wall datum at X81.35 when adapting stock/tool radius.
CLAMP_REAR_TANGENT = 81.35-CLAMP_R
PI_ACCESS_RADIUS = 4.5
REAR_RELIEF_INSET = 0.0  # Concentric Pi reliefs; driver screws have separate access.
ELECTRONICS_ACCESS_R = 3.25  # 4.5 mm M2.5 cap head plus 1 mm radial clearance.
CLAMP_OPENING = 76.0  # 72 mm tabletop plus a 4 mm pressure pad
FOOT_T = THICKNESS
FOOT_WIDTH = WIDTH
CLAMP_Z = -CLAMP_T  # top of upper jaw at Z=0, underneath the flat foot
TABLE_PLANE = CLAMP_Z
DISPLAY_TABLE_THICKNESS = 25.0
PAD_T = 4.0
SCREW_TIP_Z = TABLE_PLANE - DISPLAY_TABLE_THICKNESS - PAD_T/2
THUMB_SHIFT_Z = SCREW_TIP_Z - (-25.4)
ATTACH_XY = CLAMP_ATTACH_XY
POST_HEIGHT = STACK_HEIGHT
TRAY_T = THICKNESS
TRAY_BOTTOM = FOOT_T + POST_HEIGHT
TRAY_TOP = TRAY_BOTTOM + TRAY_T
SERVO_PAD = TRAY_TOP
ARM_RISE = SERVO_PAD - 13.175
LEGACY_SERVO_PAD = 69.525  # datum used while finishing the existing gripper
FINAL_ARM_SHIFT = SERVO_PAD - LEGACY_SERVO_PAD


def cyl(r, h, x, y, z):
    return b.Solid.make_cylinder(r, h, b.Plane(origin=(x, y, z)))


def box(x0, x1, y0, y1, z, t):
    return b.Solid.make_box(x1-x0, y1-y0, t, b.Plane(origin=(x0, y0, z)))


def finish(p, label, color=ALUMINUM_5052_COLOR):
    p = one(p).clean()
    assert p.is_valid and len(p.solids()) == 1, label
    p.label = label
    p.color = color
    return p


def clamp(*, outer_radius=None, driver_xy=None, zero_xy=None, access_mouth_radius=OUTER_RADIUS, top_width=None, wall_width=None, thickness=None, bend_radius=None, rear_tangent=None):
    """Optional review parameters leave the production configuration unchanged."""
    driver_xy = ADAPTER_XY if driver_xy is None else driver_xy
    zero_xy = PI_ZERO_XY if zero_xy is None else zero_xy
    perimeter_r = OUTER_RADIUS if outer_radius is None else outer_radius
    top_half = (CLAMP_TOP_WIDTH if top_width is None else top_width)/2
    t = CLAMP_T if thickness is None else thickness
    r = CLAMP_R if bend_radius is None else bend_radius
    x = CLAMP_REAR_TANGENT if rear_tangent is None else rear_tangent
    w = CLAMP_WIDTH if wall_width is None else wall_width
    rear_inset = REAR_RELIEF_INSET if wall_width is None else 24.5-PI_ACCESS_RADIUS-w/2
    assert rear_inset >= 0, 'Wall must preserve the full Pi mounting reliefs'
    ro = r+t
    jaw = box(CLAMP_FLANGE_FRONT, x, -top_half, top_half, 0, t)
    # Open the four Pi clearances all the way to the flange's end corners.
    # The broad middle supports the plate; the corner recesses follow the
    # underside screw heads rather than leaving thin strips outside them.
    reliefs = []
    for px, py in SUPPORT_XY:
        left = px < (CLAMP_FLANGE_FRONT+x)/2
        cut_y = py if left else py-(rear_inset if py>0 else -rear_inset)
        nose_half = abs(cut_y)-PI_ACCESS_RADIUS
        xa, xb = (CLAMP_FLANGE_FRONT,px) if left else (px,x)
        xc, xd = (CLAMP_FLANGE_FRONT,px+PI_ACCESS_RADIUS) if left else (px-PI_ACCESS_RADIUS,x)
        ya, yb = (nose_half,top_half) if py>0 else (-top_half,-nose_half)
        yc, yd = (abs(cut_y),top_half) if py>0 else (-top_half,-abs(cut_y))
        reliefs += [box(xa,xb,ya,yb,0,t),box(xc,xd,yc,yd,0,t),cyl(PI_ACCESS_RADIUS,t,px,cut_y,0)]
    # Equal-radius quarter circles end on the same straight neck as the bend
    # and wall. No secondary taper, step or blend is needed at that junction.
    assert abs(2*(24.5-rear_inset-PI_ACCESS_RADIUS)-w)<1e-9
    jaw = one(jaw.cut(*reliefs)).clean()
    edges = [e for e in jaw.edges() if abs(e.length-t)<1e-6
             and abs(e.center().X-CLAMP_FLANGE_FRONT)<1e-6]
    jaw = jaw.fillet(perimeter_r, edges)
    # Equal small outer corner radii; all four internal recesses remain R4.5.
    edges = [e for e in jaw.edges() if abs(e.length-t)<1e-6
             and abs(abs(e.center().Y)-top_half)<1e-6]
    rear_edges = [e for e in edges if e.center().X>50]
    jaw = jaw.fillet(perimeter_r, rear_edges)
    edges = [e for e in jaw.edges() if abs(e.length-t)<1e-6
             and abs(abs(e.center().Y)-top_half)<1e-6 and e.center().X<50]
    jaw = jaw.fillet(perimeter_r, edges)
    # Centered driver: four through access windows. Centered sideways Pi Zero:
    # four rounded side reliefs, independent of the structural Pi post recesses.
    access = [cyl(ELECTRONICS_ACCESS_R,t,px,py,0) for px,py in driver_xy]
    access += [cyl(ELECTRONICS_ACCESS_R,t,px,py,0) for px,py in zero_xy if px<50]
    jaw = one(jaw.cut(*access)).clean()
    if access_mouth_radius:
        # Round both ends of every open side cut without reducing head access.
        mouths = [e for e in jaw.edges() if abs(e.length-t)<1e-6
                  and abs(abs(e.center().Y)-top_half)<1e-6
                  and any(abs((e.center().X-px)**2+(e.center().Y-py)**2-ELECTRONICS_ACCESS_R**2)<1e-6
                          for px,py in zero_xy)]
        assert len(mouths)==2*len(zero_xy)
        jaw = jaw.fillet(access_mouth_radius, mouths).clean()
    lower = box(CLAMP_FRONT, x, -w/2, w/2, -CLAMP_OPENING-t, t)
    lower_edges = [e for e in lower.edges() if abs(e.length-t)<1e-6
                   and abs(e.center().X-CLAMP_FRONT)<1e-6]
    lower = lower.fillet(perimeter_r, lower_edges)
    wall = box(x+r, x+ro, -w/2, w/2, -CLAMP_OPENING+r, CLAMP_OPENING-2*r)
    bends = []
    for upper, z in ((True, -r), (False, -CLAMP_OPENING+r)):
        plane = b.Plane(origin=(x, -w/2, z), z_dir=(0, 1, 0))
        ring = one(b.Solid.make_cylinder(ro,w,plane).cut(b.Solid.make_cylinder(r,w,plane)))
        bends.append(one(ring.intersect(box(x,x+ro,-w/2,w/2,z if upper else z-ro,ro))))
    p = one(jaw.fuse(lower, wall, *bends))
    # Dedicated M3x0.5 taps, independent of the driver's plate holes.
    holes = [cyl(1.30,t,a,c,0) for a,c in ATTACH_XY]
    holes += [cyl(4.25,t,CLAMP_SCREW_X,-.5,-CLAMP_OPENING-t)]
    return finish(p.cut(*holes).moved(b.Pos(0,0,-t)),
                  'direct_servo_clamp',ALUMINUM_5052_COLOR)


def foot_plate():
    p = common_base_plate()
    p.label = 'flat_base_foot_5052_2mm'
    return p


def pressure_pad():
    bottom = SCREW_TIP_Z-PAD_T/2
    p = cyl(16,PAD_T,CLAMP_SCREW_X,-.5,bottom)
    # Blind pocket seats over the existing M8 screw end.
    p = p.cut(cyl(4.1,PAD_T/2,CLAMP_SCREW_X,-.5,bottom))
    return finish(p,'clamp_pressure_pad_32mm','#B4B8BC')


def carrier():
    p = common_base_plate().moved(b.Pos(0, 0, TRAY_BOTTOM))
    p.label = 'servo_carrier_5052_2mm'
    return p


def servo_screw(index):
    x,y = MOUNT_XY[index-1]
    p = read_step(Path(__file__).resolve().parents[2]/'STEP/imported/hardware/iso4762_socket_head_cap_screw_m2x4.step')
    p = p.moved(b.Pos(x,y,TRAY_BOTTOM)*b.Rot(X=180))
    p.label = f'clamp_standoff_screw_{index}'  # retained mate label
    p.color = SCREW_COLOR
    return p


def hardware(name):
    p = read_step(Path(__file__).resolve().parents[2]/'STEP/imported/hardware'/f'{name}.step')
    p.color = SCREW_COLOR
    return p


def clamp_attachment_screw():
    # Standard screw, bearing face at Z=0, shank along -Z.
    return hex_socket_m3x5()


def fixed_bay():
    nut = read_step(Path(__file__).resolve().parents[2]/'STEP/imported/hardware/iso4032_hex_nut_m8.step')
    nut = nut.moved(b.Pos(CLAMP_SCREW_X,-.5,CLAMP_Z-CLAMP_OPENING-CLAMP_T-6.5))
    nut.label='clamp_m8_captive_nut';nut.color=SCREW_COLOR
    out = [carrier(),foot_plate(),nut,pressure_pad()]
    out.extend(shared_stack(FOOT_T, TRAY_TOP))
    screw=clamp_attachment_screw()
    for i,(x,y) in enumerate(ATTACH_XY,1):
        q=screw.moved(b.Pos(x,y,FOOT_T))
        q.label=f'clamp_attach_m3x5_{i}';out.append(q)
    base_screw=hardware('iso4762_socket_head_cap_screw_m2p5x6').moved(b.Rot(X=180))
    for i,(x,y) in enumerate(SUPPORT_XY,1):
        q=base_screw.moved(b.Pos(x,y,0));q.label=f'base_post_m2p5x6_{i}';out.append(q)
    return b.Compound(children=out,label='fixed_electronics_bay')
