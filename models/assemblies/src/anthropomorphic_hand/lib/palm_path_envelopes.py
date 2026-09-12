"""Conservative primitive envelopes captured from actual palm source datums.

Circular rib envelopes include .05 mm for root blends plus a certified .02 mm
centerline-sample covering radius. Bosses deliberately include their bores;
no tendon route is allowed to exploit bearing holes as a routing shortcut.
Independent exact STEP distances remain the final acceptance criterion.
"""
import json
from pathlib import Path
from functools import lru_cache
import numpy as np
from scipy.spatial import cKDTree
from lib.path_analysis import sample_path
from lib.bowden_mcp import cylinder_sdf

@lru_cache(maxsize=1)
def geometry():
    from lib.palm_routing_envelopes_data import PALM_ENVELOPES
    packet=PALM_ENVELOPES;out={}
    for key in ('fixed','moving'):
        ribs={};bosses=[]
        for primitive in packet[key]:
            if primitive['kind']=='rib':ribs.setdefault(primitive['radius'],[]).extend(sample_path([{'kind':'bezier','points':primitive['points']}],.04))
            else:bosses.append(primitive)
        out[key]=([(r,cKDTree(np.asarray(points))) for r,points in ribs.items()],bosses)
    return out


def palm_clearances(points,rotation,origin=(22,40,0)):
    values=[];world=np.asarray(points);origin=np.asarray(origin)
    for key in ('fixed','moving'):
        p=world if key=='fixed' else (world-origin)@rotation+origin
        ribs,bosses=geometry()[key]
        values.extend(tree.query(p,workers=1)[0]-radius-.52 for radius,tree in ribs)
        for boss in bosses:
            local=p-np.asarray(boss['center']);axis=1 if boss['axis']=='y' else 2
            radial=np.linalg.norm(np.delete(local,axis,axis=1),axis=1)-boss['radius']
            axial=np.abs(local[:,axis])-boss['thickness']/2
            values.append(cylinder_sdf(radial,axial)-.50)
    return np.concatenate(values)
