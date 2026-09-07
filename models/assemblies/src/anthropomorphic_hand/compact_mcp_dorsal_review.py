import json
from pathlib import Path
from cadgen import step,build123d as bd
from lib.compact_mcp_dorsal import compact_mcp_dorsal_hardware

@step(out='../../STEP/anthropomorphic_hand/compact_mcp_dorsal_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.01)
def compact_mcp_dorsal_review():
    rows=compact_mcp_dorsal_hardware();root=Path(__file__).resolve().parents[2]
    (root/'validation/anthropomorphic_hand/compact_mcp_dorsal_frames.json').write_text(json.dumps([
        {'name':s.label,'frame':fr,'system':sy,'kind':kind} for s,fr,sy,kind in rows],indent=2)+'\n')
    return bd.Compound(label='compact_MCP_dorsal_journals',children=[bd.Compound(label=s.label,children=[s]) for s,_,_,_ in rows])
if __name__=='__main__':compact_mcp_dorsal_review()
