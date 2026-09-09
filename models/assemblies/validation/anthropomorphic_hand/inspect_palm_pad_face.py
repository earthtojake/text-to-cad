from cadgen import read_step,build123d as bd
s=read_step('models/assemblies/STEP/anthropomorphic_hand/palm_frame_candidate_review.step');faces=[]
for i,f in enumerate(s.faces()):
 b=f.bounding_box()
 if f.geom_type==bd.GeomType.PLANE and abs(b.min.Z-12.6)<1e-5 and abs(b.max.Z-12.6)<1e-5 and -27<b.min.X<-21 and 52<b.min.Y<58:
  faces.append((i,f));print('PAD_TOP_FACE',i,'area',f.area,'wires',len(f.wires()),'bounds',b,flush=True)
for i,(a,x) in enumerate(faces):
 for b,y in faces[i+1:]:
  c=x&y;print('FACE_OVERLAP',a,b,sum(f.area for f in c.faces()) if c else 0,flush=True)
