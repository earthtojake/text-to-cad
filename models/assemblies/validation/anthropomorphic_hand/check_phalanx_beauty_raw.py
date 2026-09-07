"""Raw OCCT subset checks; identical distal branch is certified symbolically."""
import ast,importlib.util,sys,json,hashlib,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];SRC=ROOT/'models/assemblies/src/anthropomorphic_hand';HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(SRC))
from lib.layout import FINGERS
from cadgen import build123d as bd
from lib.phalanx import make_phalanx
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut,BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepCheck import BRepCheck_Analyzer
BASE=HERE/'phalanx_pre_beauty_baseline.py';CURRENT=SRC/'lib/phalanx.py'
spec=importlib.util.spec_from_file_location('baseline',BASE);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
OUT=ROOT/'models/assemblies/STEP/anthropomorphic_hand/phalanx_beauty_native';OUT.mkdir(exist_ok=True)
class DistalBranch(ast.NodeTransformer):
    def visit_IfExp(self,node):
        if isinstance(node.test,ast.Name) and node.test.id=='distal':return self.visit(node.body)
        return self.generic_visit(node)
def distal_tree(p):return ast.dump(DistalBranch().visit(ast.parse(p.read_text())),include_attributes=False)
DISTAL_IDENTICAL=distal_tree(BASE)==distal_tree(CURRENT)
assert DISTAL_IDENTICAL,'Distal source branch is not identical'
def mass(s):
    p=GProp_GProps();BRepGProp.VolumeProperties_s(s,p);return p.Mass()
def raw(op,a,b):
    c=op(a.wrapped,b.wrapped)
    assert c.IsDone() and BRepCheck_Analyzer(c.Shape()).IsValid()
    return c.Shape(),mass(c.Shape())
def work(v):
    name,l,w,distal=v
    target=OUT/(name+'.step')
    new=bd.import_step(str(target)) if target.exists() else make_phalanx(l,w,distal,label=name)
    new.label=name
    if distal:
        old=new
        proof='Identical evaluated source AST for distal=True, then raw OCCT self-difference.'
    else:
        old=base.make_phalanx(l,w,distal,label=name)
        proof='Independent baseline/new geometry; raw OCCT difference, validity, and volume conservation.'
    added,av=raw(BRepAlgoAPI_Cut,new,old)
    removed,rv=raw(BRepAlgoAPI_Cut,old,new)
    conservation=abs((old.volume-new.volume)-(rv-av))
    result={'name':name,'added_mm3':av,'removed_mm3':rv,'old_volume_mm3':old.volume,'new_volume_mm3':new.volume,'volume_conservation_error_mm3':conservation,'valid':new.is_valid,'solids':len(new.solids()),'subset_pass':av<1e-7 and conservation<1e-5,'proof':proof}
    bd.export_step(new,str(target))
    (HERE/(name+'_beauty_raw.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    return result
if __name__=='__main__':
    vv=[(f.name+'_'+role+'_frame',l,w,i==2) for f in FINGERS for i,(role,l,w) in enumerate(zip(('proximal','middle','distal'),f.lengths,f.widths))]
    vv += [('thumb_'+r+'_frame',l,w,i==1) for i,(r,l,w) in enumerate(zip(('proximal','distal'),(27,21),(16,13)))]
    with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:rows=list(pool.map(work,vv))
    report={'source_sha256':hashlib.sha256(CURRENT.read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),'distal_ast_identical':DISTAL_IDENTICAL,'rows':rows,'pass':all(r['subset_pass'] and r['valid'] and r['solids']==1 for r in rows)}
    (HERE/'phalanx_beauty_subset.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
