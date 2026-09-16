"""Render a comparison directly from measured STL geometry (no invented shapes)."""
from pathlib import Path
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.colors import to_rgb
ROOT=Path(__file__).resolve().parents[1]
fig=plt.figure(figsize=(14,11),facecolor='#f4f5f7')
fig.text(.055,.952,'One part. Three manufacturing paths.',fontsize=26,weight='bold',color='#172638')
fig.text(.055,.916,'Same 80 × 60 × 25 mm envelope · same four Ø4.5 mounting holes',fontsize=13,color='#536273')
cards=[('baseline','Starting geometry','#9ba9bb','0.8 mm walls · 3 mm floor','Thin walls trigger the existing FDM wall check.'),('fdm','01 / FDM printing','#58a6bb','2.4 mm walls + floor · four gussets','DfAM: 2.4 mm sampled minimum; no flagged overhangs upright.'),('sheet','02 / Bent sheet metal','#d5a66a','1.5 mm uniform stock · R2 inside bends','Two bends replace the solid-wall construction.'),('cnc','03 / CNC milling','#8091c4','3 mm walls + floor · optional R3 roots','Thicker walls; open channel. Root fillets add finishing work.')]
for i,(key,title,color,spec,caption) in enumerate(cards):
 col=i%2; row=i//2; left=.055+col*.475; bottom=.49-row*.405
 ax=fig.add_axes([left,bottom,.425,.31])
 mesh=trimesh.load(ROOT/'STL'/f'{key}.stl',force='mesh')
 # Orthographic software depth buffer avoids painter-order artifacts on thin plates.
 az,el=np.deg2rad([-62,43])
 toward=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
 right=np.array([-np.sin(az),np.cos(az),0]); up=np.cross(toward,right)
 verts=(mesh.vertices-np.array([0,0,12.5]))@np.stack([right,up,toward],axis=1)
 W,H=850,580
 verts[:,:2]*=6.5; verts[:,0]+=W/2; verts[:,1]=H/2-verts[:,1]
 pixels=np.full((H,W,3),to_rgb('#f4f5f7')); depth=np.full((H,W),-np.inf)
 light=np.array([-.4,-.6,1.]);light/=np.linalg.norm(light)
 for face,normal in zip(mesh.faces,mesh.face_normals):
  a,b,c=verts[face]; xmin=max(0,int(np.floor(min(a[0],b[0],c[0])))); xmax=min(W-1,int(np.ceil(max(a[0],b[0],c[0]))))
  ymin=max(0,int(np.floor(min(a[1],b[1],c[1])))); ymax=min(H-1,int(np.ceil(max(a[1],b[1],c[1]))))
  den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
  if abs(den)<1e-9: continue
  yy,xx=np.mgrid[ymin:ymax+1,xmin:xmax+1]; xx=xx+.5;yy=yy+.5
  u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
  v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den; w=1-u-v
  z=u*a[2]+v*b[2]+w*c[2]; section=depth[ymin:ymax+1,xmin:xmax+1]
  mask=(u>=-1e-8)&(v>=-1e-8)&(w>=-1e-8)&(z>section)
  section[mask]=z[mask]; pixels[ymin:ymax+1,xmin:xmax+1][mask]=np.array(to_rgb(color))*(.48+.52*max(0,normal@light))
 ax.imshow(pixels);ax.set_axis_off()
 fig.text(left,bottom+.322,title,fontsize=17,weight='bold',color='#172638')
 fig.text(left,bottom-.012,spec,fontsize=12,weight='bold',color='#25384b')
 fig.text(left,bottom-.038,caption,fontsize=9.4,color='#536273')
fig.text(.055,.022,'Geometry verified from STEP. Concept comparison: no equal-strength claim; no CAM, flat-pattern or production qualification.',fontsize=10,color='#647183')
fig.savefig(ROOT/'tmp'/'manufacturing-comparison.png',dpi=180,facecolor=fig.get_facecolor())
