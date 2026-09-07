from copy import deepcopy
from cadgen import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common,BRepAlgoAPI_Cut
def _run(cls,a,b):
    a,b=deepcopy(a),deepcopy(b)
    op=cls(a.wrapped,b.wrapped)
    if not op.IsDone():raise ValueError('Native contact Boolean failed')
    return bd.Part(op.Shape())
def common(a,b):return _run(BRepAlgoAPI_Common,a,b)
def cut(a,b):return _run(BRepAlgoAPI_Cut,a,b)
