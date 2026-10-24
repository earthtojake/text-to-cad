"""Square horn references at closed pinch, independent of the jaw face angle."""
import math
import build123d as bd
from lib.restored_claw_refinement import (
    GRIPPER_CLOSE_ANGLE_DEG, GRIPPER_SHAFT_X_MM, GRIPPER_SHAFT_Y_MM,
)
from lib.gripper_frame_layout import RECOVERED_JAW_BAND_SHIFT_Y_MM
from lib.horn_cap import FRAME_HORN_FORK_PATTERN

HORN_LABELS=('FK-AP-019-25T','WJ-DP00-0002-FK-AP-020')
NOMINAL_PHASE_DEG=-GRIPPER_CLOSE_ANGLE_DEG


def moving_screw_xy(index):
    """Six existing screw labels, now seated in the shared square fork pattern."""
    hole=FRAME_HORN_FORK_PATTERN.holes[(0,2,1,1,2,0)[index-1]]
    across,outboard,_=hole
    a=math.radians(NOMINAL_PHASE_DEG)
    # Opening faces the opposing claw (-Y). Keep forward, outer and rear holes.
    x,y=across,-outboard
    return (GRIPPER_SHAFT_X_MM+x*math.cos(a)-y*math.sin(a),
            GRIPPER_SHAFT_Y_MM+RECOVERED_JAW_BAND_SHIFT_Y_MM
            +x*math.sin(a)+y*math.cos(a))


def square_at_closed(original):
    """Rephase only the two horn occurrences, retaining the complete servo tree.

    This is the servo's angular reference pose, not a continuously adjustable
    spline mounting interface. Assembly kinematics carry both horns with the jaw.
    """
    axis=bd.Axis((GRIPPER_SHAFT_X_MM,
        GRIPPER_SHAFT_Y_MM+RECOVERED_JAW_BAND_SHIFT_Y_MM,0),(0,0,1))
    found=[]
    def clone(node,ancestors):
        if node.children:
            children=[clone(child,ancestors*node.location)for child in node.children]
            result=bd.Compound(children=children,label=node.label).moved(node.location)
        else:
            result=type(node)(node.wrapped)
            if node.label in HORN_LABELS:
                result=result.moved(ancestors).rotate(axis,NOMINAL_PHASE_DEG).moved(ancestors.inverse())
                found.append(node.label)
        result.label,result.color=node.label,node.color
        return result
    result=clone(original,bd.Location())
    if sorted(found)!=sorted(HORN_LABELS):raise ValueError('Expected both jaw horns')
    return result
