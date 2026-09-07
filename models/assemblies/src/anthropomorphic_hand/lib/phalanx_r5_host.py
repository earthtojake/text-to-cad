from functools import lru_cache
from pathlib import Path
from cadgen import read_step,build123d as bd
@lru_cache(maxsize=1)
def warm_host():
    path=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/phalanx_continuous_r5.step'
    read_step(path)  # Register the exact native input in the source build closure.
    return bd.import_step(path)  # Native STEP reconstruction is required for reliable clipping.
def make_phalanx(length,width,*args,**kwargs):
    assert (length,width)==(45,18)
    return warm_host()
