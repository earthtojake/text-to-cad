import React from 'react';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {useStepReference} from '../../../../../dist/renderers/step/components/workbench/StepReferenceSection.js';
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
const arc={id:'o1.e1',normalizedSelector:'o1.e1',selectorType:'edge',pickData:{curveType:'circle',length:7.8,params:{radius:5,sweepRadians:Math.PI/2,center:[0,0,0]},center:[3,3,0]}};
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
 const refs=[3,4].map((length,i)=>({id:`o1.e${i}`,selectorType:'edge',normalizedSelector:`o1.e${i}`,pickData:{curveType:'line',length}}));
 render(<StepReferenceSection references={refs}/>);
 expect(screen.queryByText(/^Total/)).toBeNull();
 expect(picker()).toEqual(['o1 · edge 1','2/2']);
 expect(screen.getByText('4 mm')).toBeTruthy();
 browse('o1 · edge 0');
 expect(screen.getByText('3 mm')).toBeTruthy();expect(screen.queryByText('4 mm')).toBeNull();
 expect(picker()).toEqual(['o1 · edge 0','1/2']);
 expect(screen.queryByText('o1.e0')).toBeNull();
 expect(screen.queryByRole('button',{name:'Previous element'})).toBeNull();
});

it('a face shows its area, and a round one its radii: nothing of its kind, id, place or part beyond what its heading names',()=>{
 const {rerender}=render(<StepReferenceSection references={[arc]}/>);
 const face={id:'o1.f2',normalizedSelector:'o1.f2',selectorType:'face',pickData:{surfaceType:'plane',area:662.734,center:[2,4,6],normal:[0,0,1],sourceName:'Camera',bbox:{min:[0,0,0],max:[40,20,0]}}};
 rerender(<StepReferenceSection references={[face]}/>);
 expect(heading()).toBe('Camera · face 2');
 expect(rows()).toEqual(['Area662.73 mm²']);
 for (const gone of ['Type','Face · Planar','ID','o1.f2','Center','Normal','Size','Component']) expect(screen.queryByText(gone),gone).toBeNull();
 rerender(<StepReferenceSection references={[{...face,pickData:{...face.pickData,surfaceType:'cylinder',area:94.25,params:{radius:3}}}]}/>);
 expect(rows()).toEqual(['Diameter Ø6 mm','Radius R3 mm','Area94.25 mm²']);
});

it('heads several references with a picker naming the browsed one, and switches to the newest only when the selection changes',()=>{
 const name='camera_assembly_with_a_name_that_exceeds_the_panel_width';
 const selector='o1.8.1234567890.1234567890.1234567890.1234567890';
 const camera={id:selector,nodeType:'assembly',name,leafPartIds:['camera','mount'],children:[],bbox:{min:[0,0,0],max:[10,20,30]},copyText:'tom.step#camera'};
 const base={...camera,id:'o1.1',name:'Base',copyText:'tom.step#base'};
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
 rerender(<StepReferenceSection references={[base,camera,{...camera,id:'o1.9',name:'New part'}]}/>);
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
 const meshData={parts:[{occurrenceId:'o1.8',sourceColor:'#778899'}]};
 render(<StepReferenceSection references={[{id:'o1.8',nodeType:'part',name:'Camera',leafPartIds:['o1.8'],children:[],bbox:{min:[0,0,0],max:[40,29,10]}}]} meshData={meshData}/>);
 expect(heading()).toBe('Camera');
 expect(rows()).toEqual(['Size40 × 29 × 10 mm']);
 for (const gone of ['o1.8','Component','Center','Material','Color','#778899']) expect(screen.queryByText(gone),gone).toBeNull();
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
 const meshData={parts:[{id:'o1.1',occurrenceId:'o1.1',name:'base'}]};
 const named={id:'topology|o1.1|face|o1.1.f3',normalizedSelector:'o1.1.f3',selectorType:'face',occurrenceId:'o1.1',label:'Mounting face',pickData:{surfaceType:'plane'}};
 const {rerender}=render(<StepReferenceSection references={[named]} meshData={meshData}/>);
 expect(heading()).toBe('Mounting face');
 rerender(<StepReferenceSection references={[{...named,label:undefined}]} meshData={meshData}/>);
 expect(heading()).toBe('base · face 3');
 rerender(<StepReferenceSection references={[{id:'topology|o1.1|edge|o1.1.e4',normalizedSelector:'o1.1.e4',selectorType:'edge',occurrenceId:'o1.1',pickData:{curveType:'line',length:2}}]} meshData={meshData}/>);
 expect(heading()).toBe('base · edge 4');
 expect(rows()).toEqual(['Length2 mm']);
 expect(screen.queryByText('o1.1.e4')).toBeNull();
});

it('names the part of a single-part file with no name of its own after the file',()=>{
 // A part the STEP gave no name goes by its occurrence id in the tree, and the tree's root is the
 // part, named after the file.
 const meshData={parts:[{id:'o1.1',occurrenceId:'o1.1',name:'o1.1'}]};
 const root=new Map([['__step_model__','l_bracket.step']]);
 const partName=(id:string)=>root.get(id)||'';
 const face=(ord:number)=>({id:`o1.1.f${ord}`,normalizedSelector:`o1.1.f${ord}`,selectorType:'face',occurrenceId:'o1.1',
   label:`Face o1.1.f${ord}`,pickData:{surfaceType:'plane',name:null,sourceName:null}});
 const {rerender}=render(<StepReferenceSection references={[face(11)]} meshData={meshData} partName={partName}/>);
 expect(heading()).toBe('l_bracket · face 11');
 // The picker's entries read the same.
 rerender(<StepReferenceSection references={[face(11),face(12)]} meshData={meshData} partName={partName}/>);
 expect(picker()).toEqual(['l_bracket · face 12','2/2']);
 fireEvent.keyDown(screen.getByRole('combobox',{name:'Inspect selected reference'}),{key:'ArrowDown'});
 expect(screen.getAllByRole('option').map(option=>option.textContent)).toEqual(['l_bracket · face 11','l_bracket · face 12']);
 cleanup();
 // A lone part with a name of its own keeps it; one with none and no file to go by is its occurrence.
 render(<StepReferenceSection references={[face(3)]} meshData={{parts:[{id:'o1.1',occurrenceId:'o1.1',name:'sun_gear'}]}} partName={partName}/>);
 expect(heading()).toBe('sun_gear · face 3');
 cleanup();
 render(<StepReferenceSection references={[face(3)]} meshData={meshData}/>);
 expect(heading()).toBe('o1.1 · face 3');
});
