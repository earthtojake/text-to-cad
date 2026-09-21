import { near } from './modelingGeometry.js';

export const boundaryProfile = (id, loop, edges) => ({
  id: `${id}:profile`, kind: 'profile', label: 'Sketch profile', faces: [], edges: loop.map(e => e.edgeOrd),
  note: 'Recovered STEP boundary; no original sketch constraints.',
  measurements: [['Perimeter', loop.reduce((sum, e) => sum+edges.get(e.edgeOrd).length,0), 'mm']],
  children: loop.map((use, i) => {
    const edge = edges.get(use.edgeOrd);
    return { id:`${id}:edge:${edge.ord}`, kind:'curve', label:`${edge.curveType === 'circle' ? near(edge.length,2*Math.PI*edge.params.radius) ? 'Circle' : 'Arc' : 'Line'} ${i+1}`, faces:[], edges:[edge.ord],
      measurements: [['Length',edge.length,'mm'], ...(edge.params?.radius ? [['Radius',edge.params.radius,'mm']] : [])] };
  }),
});
