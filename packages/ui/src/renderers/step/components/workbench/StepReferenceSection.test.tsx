import React from 'react';
import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {useStepReference} from '../../../../../dist/renderers/step/components/workbench/StepReferenceSection.js';
import {createFaceAreas} from '../../../../../dist/renderers/step/workbench/faceAreas.js';
Object.assign(globalThis,{React});
beforeEach(()=>{
 vi.stubGlobal('ResizeObserver',class {observe(){} unobserve(){} disconnect(){}});
 vi.spyOn(HTMLElement.prototype,'scrollIntoView').mockImplementation(()=>{});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
// jsdom has no scrolling implementation.
HTMLElement.prototype.scrollIntoView ||= ()=>{};
// The Reference panel as the tree draws it: the heading the hook gives, then its rows.
function StepReferenceSection(props:any){
 const reference=useStepReference(props);
 return reference ? <section aria-label="Reference details"><h3>{reference.title}</h3>{reference.content}</section> : null;
}
const heading=()=>screen.getByRole('heading').textContent;
// The picker's name and its "i/N", read apart.
const picker=()=>{const label=screen.getByRole('combobox').querySelector('[data-reference-label]')!;return [label.firstElementChild!.textContent,label.querySelector('[data-reference-count]')!.textContent];};
const arc={id:'o:1a2b3c4d5e6f/e:knob.revolve1.1',normalizedSelector:'o:1a2b3c4d5e6f/e:knob.revolve1.1',selectorType:'edge',pickData:{curveType:'circle',length:7.8,params:{radius:5,sweepRadians:Math.PI/2,center:[0,0,0]},center:[3,3,0]}};
function browse(name:string){
 fireEvent.keyDown(screen.getByRole('combobox',{name:'Inspect selected reference'}),{key:'ArrowDown'});
 fireEvent.click(screen.getByRole('option',{name,exact:true}));
}

// What the panel's rows say, label then value, in order.
const rows=()=>[...document.querySelectorAll('[data-info-row]')].map(row=>row.textContent);

it('an edge shows its key measurements alone: an arc\'s diameter, radius, arc length and sweep, without disclosures or actions',()=>{
 const {container}=render(<StepReferenceSection references={[arc]}/>);
 expect(rows()).toEqual(['Diameter Ø10 mm','Radius R5 mm','Arc length7.85 mm','Sweep angle90 °']);
 expect(screen.queryByText('Center')).toBeNull();
 expect(container.querySelector('details')).toBeNull();
 expect(screen.queryByRole('button')).toBeNull();
 expect(screen.queryByRole('combobox')).toBeNull();
});

it('browses individual selected edges from the heading, and shows only the browsed one\'s rows',()=>{
 const refs=[3,4].map((length,i)=>({id:`o:1a2b3c4d5e6f/e:base.extrude1.${i+1}`,selectorType:'edge',normalizedSelector:`o:1a2b3c4d5e6f/e:base.extrude1.${i+1}`,pickData:{curveType:'line',length}}));
 render(<StepReferenceSection references={refs}/>);
 expect(screen.queryByText(/^Total/)).toBeNull();
 expect(picker()).toEqual(['o:1a2b3c4d5e6f · edge e:base.extrude1.2','2/2']);
 expect(screen.getByText('4 mm')).toBeTruthy();
 browse('o:1a2b3c4d5e6f · edge e:base.extrude1.1');
 expect(screen.getByText('3 mm')).toBeTruthy();expect(screen.queryByText('4 mm')).toBeNull();
 expect(picker()).toEqual(['o:1a2b3c4d5e6f · edge e:base.extrude1.1','1/2']);
 expect(screen.queryByText('o:1a2b3c4d5e6f/e:base.extrude1.1')).toBeNull();
 expect(screen.queryByRole('button',{name:'Previous element'})).toBeNull();
});

it('a face shows its area, cadgen\'s measure of it, and a round one its radii: nothing of its kind, id, place or part beyond what its heading names',async()=>{
 // Each face's area as cadgen measures it on asking (`POST /__cad/measure`): held until the test lets it come.
 const answers:Record<number,(area:number)=>void>={};
 const faceAreas=createFaceAreas({
  requestFor:(reference:any)=>({tree:'t',viewId:'v',producer:{},cid:'c',part:'p',face:reference.pickData.ordinal}),
  measure:(body:any)=>new Promise(resolve=>{answers[body.face]=(area:number)=>resolve({face:body.face,area,center:[0,0,0]});}),
 });
 // cadgen answers the face's request, once the panel has made it.
 const answer=(face:number,area:number)=>act(async()=>{await Promise.resolve();answers[face](area);});
 const {rerender}=render(<StepReferenceSection references={[arc]} faceAreas={faceAreas}/>);
 const face={id:'o:1a2b3c4d5e6f/f:base.extrude1.2',normalizedSelector:'o:1a2b3c4d5e6f/f:base.extrude1.2',selectorType:'face',pickData:{ordinal:2,surfaceType:'plane',normal:[0,0,1],sourceName:'Camera',bbox:{min:[0,0,0],max:[40,20,0]}}};
 rerender(<StepReferenceSection references={[face]} faceAreas={faceAreas}/>);
 expect(heading()).toBe('Camera · face f:base.extrude1.2');
 expect(rows()).toEqual([]);
 await answer(2,662.734);
 expect(rows()).toEqual(['Area662.73 mm²']);
 for (const gone of ['Type','Face · Planar','ID','o:1a2b3c4d5e6f/f:base.extrude1.2','Center','Normal','Size','Component']) expect(screen.queryByText(gone),gone).toBeNull();
 rerender(<StepReferenceSection references={[{...face,id:'o:1a2b3c4d5e6f/f:base.extrude1.5',normalizedSelector:'o:1a2b3c4d5e6f/f:base.extrude1.5',pickData:{...face.pickData,ordinal:5,surfaceType:'cylinder',params:{radius:3}}}]} faceAreas={faceAreas}/>);
 await answer(5,94.25);
 expect(rows()).toEqual(['Diameter Ø6 mm','Radius R3 mm','Area94.25 mm²']);
});

it('heads several references with a picker naming the browsed one, and switches to the newest only when the selection changes',()=>{
 const name='camera_assembly_with_a_name_that_exceeds_the_panel_width';
 const selector='o:0e1f2a3b4c5d/o:1234567890ab/o:1234567890cd/o:1234567890ef/o:123456789012';
 const camera={id:selector,nodeType:'assembly',name,leafPartIds:['camera','mount'],children:[],bbox:{min:[0,0,0],max:[10,20,30]},copyText:'tom.step#camera'};
 const base={...camera,id:'o:0a1b2c3d4e5f',name:'Base',copyText:'tom.step#base'};
 const {rerender}=render(<StepReferenceSection references={[base,camera]}/>);
 // The picker is the heading: the name and id it shows are not repeated as rows.
 expect(within(screen.getByRole('heading')).getByRole('combobox')).toBeTruthy();
 expect(picker()).toEqual([name,'2/2']);
 // The id is not the name, and no row: what a copy carries is the panel's Copy.
 expect(screen.queryByText(selector)).toBeNull();
 expect(screen.queryByText('Name')).toBeNull();
 expect(screen.queryByText(/Selection ·|references/)).toBeNull();
 // A subassembly's key measurements: its parts, its size.
 expect(rows()).toEqual(['Parts2','Size10 × 20 × 30 mm']);
 expect(screen.queryByText('Subassembly')).toBeNull();
 expect(screen.queryByText('Center')).toBeNull();
 expect(screen.queryByRole('button',{name:'Copy reference'})).toBeNull();
 browse('Base');
 expect(picker()).toEqual(['Base','1/2']);
 rerender(<StepReferenceSection references={[{...base},{...camera}]}/>);
 expect(picker()).toEqual(['Base','1/2']);
 rerender(<StepReferenceSection references={[base,camera,{...camera,id:'o:0f1a2b3c4d5e',name:'New part'}]}/>);
 expect(picker()).toEqual(['New part','3/3']);
});

it('shows the browsed part\'s own Volume, never a total over the selection',()=>{
 // Two 10 mm cubes, as a mesh part's triangles: the volume is read off the displayed mesh.
 const cube=(id:string)=>({id,nodeType:'part',name:id,leafPartIds:[id],children:[],bbox:{min:[0,0,0],max:[10,10,10]}});
 const box=[[0,0,0],[10,0,0],[10,10,0],[0,10,0],[0,0,10],[10,0,10],[10,10,10],[0,10,10]].flat();
 const faces=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7];
 const meshData={vertices:new Float32Array([...box,...box]),indices:new Uint32Array([...faces,...faces.map(i=>i+8)]),
  parts:[{id:'a',occurrenceId:'a',vertexOffset:0,vertexCount:8,triangleOffset:0,triangleCount:12},{id:'b',occurrenceId:'b',vertexOffset:8,vertexCount:8,triangleOffset:12,triangleCount:12}]};
 const {rerender}=render(<StepReferenceSection references={[cube('a')]} meshData={meshData}/>);
 expect(heading()).toBe('a');
 expect(screen.getAllByText(/volume$/i).map(node=>node.textContent)).toEqual(['Volume']);
 rerender(<StepReferenceSection references={[cube('a'),cube('b')]} meshData={meshData}/>);
 expect(screen.getAllByText(/volume$/i).map(node=>node.textContent)).toEqual(['Volume']);
 expect(screen.getByText('1,000 mm³')).toBeTruthy();
 expect(screen.queryByText('2,000 mm³')).toBeNull();
});

it('heads a single component with its name, over its size alone: no id, type, centre or material rows',()=>{
 const meshData={parts:[{occurrenceId:'o:0e1f2a3b4c5d',sourceColor:'#778899'}]};
 render(<StepReferenceSection references={[{id:'o:0e1f2a3b4c5d',nodeType:'part',name:'Camera',leafPartIds:['o:0e1f2a3b4c5d'],children:[],bbox:{min:[0,0,0],max:[40,29,10]}}]} meshData={meshData}/>);
 expect(heading()).toBe('Camera');
 expect(rows()).toEqual(['Size40 × 29 × 10 mm']);
 for (const gone of ['o:0e1f2a3b4c5d','Component','Center','Material','Color','#778899']) expect(screen.queryByText(gone),gone).toBeNull();
 expect(screen.queryByRole('button')).toBeNull();
 expect(screen.queryByRole('combobox')).toBeNull();
 expect(screen.queryByText('Details')).toBeNull();
});

it('a part browsed among several shows its own size, never the selection\'s',()=>{
 const part=(id:string)=>({id,nodeType:'part',name:id,leafPartIds:[id],children:[]});
 const sizes:Record<string,number[]>={a:[10,10,10],b:[40,20,5]};
 const partsSize=(ids:string[])=>ids.length===1 ? sizes[ids[0]] : null;
 render(<StepReferenceSection references={[part('a'),part('b')]} measurements={{size:[50,30,10]}} partsSize={partsSize}/>);
 expect(rows()).toEqual(['Size40 × 20 × 5 mm']);
 browse('a');
 expect(rows()).toEqual(['Size10 × 10 × 10 mm']);
});

it('retains bounding measurements as read-only facts when only part geometry is available',()=>{
 render(<StepReferenceSection measurements={{size:[10,20,30],radii:[]}}/>);
 expect(screen.getByText('10 × 20 × 30 mm')).toBeTruthy();
 expect(screen.queryByRole('button')).toBeNull();
});

it('names a face or edge by its own label, else by its part and kind, never by its raw id',()=>{
 const meshData={parts:[{id:'o:0a1b2c3d4e5f',occurrenceId:'o:0a1b2c3d4e5f',name:'base'}]};
 const named={id:'topology|o:0a1b2c3d4e5f|face|o:0a1b2c3d4e5f/f:base.extrude1.3',normalizedSelector:'o:0a1b2c3d4e5f/f:base.extrude1.3',selectorType:'face',occurrenceId:'o:0a1b2c3d4e5f',label:'Mounting face',pickData:{surfaceType:'plane'}};
 const {rerender}=render(<StepReferenceSection references={[named]} meshData={meshData}/>);
 expect(heading()).toBe('Mounting face');
 rerender(<StepReferenceSection references={[{...named,label:undefined}]} meshData={meshData}/>);
 expect(heading()).toBe('base · face f:base.extrude1.3');
 rerender(<StepReferenceSection references={[{id:'topology|o:0a1b2c3d4e5f|edge|o:0a1b2c3d4e5f/e:base.fillet1.4',normalizedSelector:'o:0a1b2c3d4e5f/e:base.fillet1.4',selectorType:'edge',occurrenceId:'o:0a1b2c3d4e5f',pickData:{curveType:'line',length:2}}]} meshData={meshData}/>);
 expect(heading()).toBe('base · edge e:base.fillet1.4');
 expect(rows()).toEqual(['Length2 mm']);
 expect(screen.queryByText('o:0a1b2c3d4e5f/e:base.fillet1.4')).toBeNull();
});

it('names the part of a single-part file with no name of its own after the file',()=>{
 // A part the STEP gave no name goes by its occurrence id in the tree, and the tree's root is the
 // part, named after the file.
 const meshData={parts:[{id:'o:0a1b2c3d4e5f',occurrenceId:'o:0a1b2c3d4e5f',name:'o:0a1b2c3d4e5f'}]};
 const root=new Map([['__step_model__','l_bracket.step']]);
 const partName=(id:string)=>root.get(id)||'';
 const name=(n:number)=>`f:bracket.extrude1.${n}`;
 const face=(n:number)=>({id:`o:0a1b2c3d4e5f/${name(n)}`,normalizedSelector:`o:0a1b2c3d4e5f/${name(n)}`,selectorType:'face',occurrenceId:'o:0a1b2c3d4e5f',
   label:`Face o:0a1b2c3d4e5f/${name(n)}`,pickData:{surfaceType:'plane',name:null,sourceName:null}});
 const {rerender}=render(<StepReferenceSection references={[face(11)]} meshData={meshData} partName={partName}/>);
 expect(heading()).toBe('l_bracket · face f:bracket.extrude1.11');
 // The picker's entries read the same.
 rerender(<StepReferenceSection references={[face(11),face(12)]} meshData={meshData} partName={partName}/>);
 expect(picker()).toEqual(['l_bracket · face f:bracket.extrude1.12','2/2']);
 fireEvent.keyDown(screen.getByRole('combobox',{name:'Inspect selected reference'}),{key:'ArrowDown'});
 expect(screen.getAllByRole('option').map(option=>option.textContent)).toEqual(['l_bracket · face f:bracket.extrude1.11','l_bracket · face f:bracket.extrude1.12']);
 cleanup();
 // A lone part with a name of its own keeps it; one with none and no file to go by is its occurrence.
 render(<StepReferenceSection references={[face(3)]} meshData={{parts:[{id:'o:0a1b2c3d4e5f',occurrenceId:'o:0a1b2c3d4e5f',name:'sun_gear'}]}} partName={partName}/>);
 expect(heading()).toBe('sun_gear · face f:bracket.extrude1.3');
 cleanup();
 render(<StepReferenceSection references={[face(3)]} meshData={meshData}/>);
 expect(heading()).toBe('o:0a1b2c3d4e5f · face f:bracket.extrude1.3');
});
