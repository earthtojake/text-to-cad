"""Constant-total-length capstan compensation, including the moving free lead.

This is the mechanism's payout equation, independent of animation timing.
All distances are mm, spool angles radians about the motor's local +Z.
"""
from functools import lru_cache
import math
from scipy.optimize import brentq
from lib.forearm_routing import forearm_route
from lib.path_analysis import path_length
from lib.layout import TENDONS
from lib.capstan_path import OPERATIONAL_ROTATION_LIMIT_RAD
_BY_NAME={t['name']:t for t in TENDONS}
@lru_cache(maxsize=48)
def neutral_forearm_length(name):return path_length(forearm_route(_BY_NAME[name])['path'])
def solve_rotation(name,downstream_length_change):
    """Solve Lforearm(q)+Ldownstream(pose)=Ltotal(neutral)."""
    if abs(downstream_length_change)<1e-11:return 0.
    tendon=_BY_NAME[name];target=neutral_forearm_length(name)-downstream_length_change
    def residual(q):return path_length(forearm_route(tendon,float(q))['path'])-target
    limit=OPERATIONAL_ROTATION_LIMIT_RAD
    a,b=residual(-limit),residual(limit)
    if a*b>0:raise ValueError(f'{name}: capstan storage exhausted for {downstream_length_change:.8f}mm change, residuals{a,b}')
    q=brentq(residual,-limit,limit,xtol=1e-12,rtol=1e-13)
    if abs(residual(q))>1e-7:raise ValueError(f'{name}: payout residual')
    return float(q)
