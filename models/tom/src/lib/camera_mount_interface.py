"""Stable Tom camera-foot interface shared by production and study profiles."""
import build123d as bd
from lib import sheet_rule_scs as scs
from lib.servo_case_flange import REVERSIBLE_FLANGE_HALF_WIDTH_MM

T=scs.THICKNESS_MM
RI=scs.EFFECTIVE_BEND_RADIUS_MM
RO=RI+T
FOOT_WIDTH=2*REVERSIBLE_FLANGE_HALF_WIDTH_MM
REAR_TANGENT_Y=-8.2558

def polygon(points):
    return bd.Face(bd.Wire.make_polygon([(*p,0) for p in points],close=True))


def cut_face(outline,cuts):
    for cut in cuts:outline=outline.cut(cut)
    if len(outline.faces())!=1:raise ValueError('Sheet profile must remain one connected face')
    return outline.faces()[0]
