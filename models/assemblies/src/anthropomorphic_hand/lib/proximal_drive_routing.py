"""Terminal approaches and driven wraps for cup and the two wrist axes.

The preceding wrist-guide module supplies their real parent-side splices.
Wrist guide length changes are explicitly compensated in capstan payout.
"""
from lib.layout import JOINT_BY_NAME,transforms
from lib.finger_routing import transform_path,line,endpoint


def proximal_drive_route(name,pose=None):
    suffix='positive' if name.endswith('_positive') else 'negative'
    sign=1 if suffix=='positive' else -1
    joint=name.rsplit('_',1)[0];q=(pose or {}).get(joint,0.)
    if joint=='wrist_abduction':
        center=[0.,-9.,sign*5.5];start=[-sign*11.,-9.,sign*5.5]
        inlet=[-sign*11.,-15.,sign*5.5];axis=[0.,0.,1.]
    elif joint=='wrist_flexion':
        center=[sign*14.,0.,0.];start=[sign*14.,0.,sign*11.]
        inlet=[sign*14.,-6.,sign*11.];axis=[1.,0.,0.]
    elif joint=='palm_cup':
        y=45. if sign>0 else 47.
        center=[22.,y,0.];start=[22.,y,sign*7.]
        inlet=[2.,y,sign*7.];axis=[0.,-1.,0.]
    else:raise ValueError(name)
    parent=JOINT_BY_NAME[joint].parent;m=transforms(pose or {})[parent]
    arc={'kind':'arc','center':center,'axis':axis,'start':start,'sweepDeg':-sign*150.+q}
    approach=transform_path([line(inlet,start)],m);wrap=transform_path([arc],m)
    path=approach+wrap
    return {'name':name,'joint':joint,'sign':sign,'path':path,'termination':endpoint(path[-1],True),
            'termination_frame':joint,'moment_arm':sign*JOINT_BY_NAME[joint].drive_radius,
            'groups':[{'label':name+'_drive_approach','path':approach,'frame':parent,'guide':None},
                      {'label':name+'_drive_wrap','path':wrap,'frame':parent,'guide':'drive_pulley'}]}
