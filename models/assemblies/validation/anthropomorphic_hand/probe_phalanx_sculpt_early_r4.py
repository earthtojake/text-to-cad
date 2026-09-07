from pathlib import Path
p=Path('models/assemblies/src/anthropomorphic_hand/lib/phalanx.py')
s=p.read_text()
needle='        plate=bd.fillet(plate.edges(),.20)'
rep='''        # Outer-face waist before finishing the plate's perimeter.
        for lo,hi in [(4.4,11.45),(13.05,29.2),(33.55,37.2)]:
            mid=(lo+hi)/2;span=hi-lo;outer=1.70;inner=.58
            es=[bd.Edge.make_bezier((lo,0,outer),(lo+.22*span,0,outer),(mid-.18*span,0,inner),(mid,0,inner)),bd.Edge.make_bezier((mid,0,inner),(mid+.18*span,0,inner),(hi-.22*span,0,outer),(hi,0,outer)),bd.Edge.make_line((hi,0,outer),(hi,0,3)),bd.Edge.make_line((hi,0,3),(lo,0,3)),bd.Edge.make_line((lo,0,3),(lo,0,outer))]
            cutter=bd.extrude(bd.Face(bd.Wire(es)),amount=10,dir=(0,1,0),both=True)
            if sign<0:cutter=bd.Pos(0,0,1.45)*bd.mirror(cutter,bd.Plane.XY)
            plate=plate-cutter
        plate=bd.fillet(plate.edges(),.20)'''
assert needle in s;s=s.replace(needle,rep)
Path('models/assemblies/validation/anthropomorphic_hand/phalanx_early_sculpt_r4.py').write_text(s)
ns={};exec(compile(s,str(p),'exec'),ns)
v=ns['make_phalanx'](45,18)
print('result',v.is_valid,len(v.solids()),v.volume,flush=True)
ns['bd'].export_step(v,'models/assemblies/STEP/anthropomorphic_hand/phalanx_sculpt_early_probe_r4.step')
