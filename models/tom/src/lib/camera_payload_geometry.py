"""Camera datums in bracket coordinates; no hidden assembly transforms."""
import build123d as bd
from lib import camera_mount_geometry as g
from lib.materials import NUT_COLOR

PCB_SEAT_OFFSET=-g.T
CAMERA_PCB_THICKNESS=1.5
CAMERA_NUT_HEIGHT=1.6


def camera_plane():
    return g.camera_plane()


def mount_holes():
    return [(x,y) for x in (-g.CAMERA_HOLE_PITCH/2,g.CAMERA_HOLE_PITCH/2)
            for y in (-g.CAMERA_HOLE_PITCH/2,g.CAMERA_HOLE_PITCH/2)]


def build_payload(camera,screw,nut):
    frame=camera_plane().location
    components=[]
    camera=camera.moved(bd.Location((0,0,PCB_SEAT_OFFSET))).moved(frame)
    camera.label='innomaker_u20cam_camera'
    components.append(camera)
    for i,(x,y) in enumerate(mount_holes(),1):
        front=screw.moved(bd.Location((x,y,0))).moved(frame)
        front.label=f'camera_front_m2x6_{i}'
        components.append(front)
    for i,(x,y) in enumerate(mount_holes(),1):
        rear=nut.moved(bd.Location((x,y,PCB_SEAT_OFFSET-CAMERA_PCB_THICKNESS-CAMERA_NUT_HEIGHT))).moved(frame)
        rear.label=f'camera_rear_m2_nut_{i}';rear.color=NUT_COLOR
        components.append(rear)
    return bd.Compound(children=components,label='camera_payload')
