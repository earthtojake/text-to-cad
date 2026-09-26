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

it('shows arc dimensions and analytic center coordinates without disclosures or actions',()=>{
 const {container}=render(<StepReferenceSection references={[arc]}/>);
 expect(screen.getByText('Diameter Ø')).toBeTruthy();
 expect(screen.getByText('Sweep angle')).toBeTruthy();
 expect(screen.getByText('90 °')).toBeTruthy();
 const center=screen.getByText('Center').parentElement!;
 expect(within(center).getAllByText('0')).toHaveLength(3);
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
 expect(screen.getByText('o1.e0')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Previous element'})).toBeNull();
});

it('updates always-visible coordinates and normal when the selected reference changes',()=>{
 const {rerender}=render(<StepReferenceSection references={[arc]}/>);
 const face={id:'o1.f2',normalizedSelector:'o1.f2',selectorType:'face',pickData:{surfaceType:'plane',center:[2,4,6],normal:[0,0,1],sourceName:'Camera'}};
 rerender(<StepReferenceSection references={[face]}/>);
 expect(screen.getByText('Center').closest('details')).toBeNull();
 expect(screen.getByText('Normal')).toBeTruthy();
 expect(screen.getByText('Camera')).toBeTruthy();
 expect(screen.getByText('Face · Planar')).toBeTruthy();
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
 // The id is not the name: it is the ID row, what a copy carries.
 expect(screen.getByText(selector)).toBeTruthy();
 expect(screen.queryByText('Name')).toBeNull();
 expect(screen.queryByText(/Selection ·|references/)).toBeNull();
 expect(screen.getByText('Subassembly')).toBeTruthy();
 expect(screen.getByText('Parts')).toBeTruthy();
 expect(screen.getByText('Center')).toBeTruthy();
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

it('heads a single component with its name and canonical path, as a label, and keeps its rows compact',()=>{
 render(<StepReferenceSection references={[{id:'o1.8',nodeType:'part',name:'Camera',leafPartIds:['o1.8'],children:[]}]}/>);
 expect(heading()).toBe('Camera');
 expect(screen.getByText('o1.8')).toBeTruthy();
 expect(screen.getByText('Component')).toBeTruthy();
 expect(screen.queryByRole('button')).toBeNull();
 expect(screen.queryByRole('combobox')).toBeNull();
 expect(screen.queryByText('Details')).toBeNull();
});

it('shows read-only authored material without turning source color into a material name',()=>{
 const face={id:'o1.2.f4',normalizedSelector:'o1.2.f4',selectorType:'face',pickData:{surfaceType:'plane'}};
 const meshData={parts:[{occurrenceId:'o1.2',sourceColor:'#778899'}]};
 const sourceAppearance={materials:{steel:{name:'Brushed steel',roughness:0.25,metalness:1}},assignments:{'o1.2':'steel'}};
 render(<StepReferenceSection references={[face]} meshData={meshData} sourceAppearance={sourceAppearance}/>);
 const material=screen.getByRole('generic',{name:'Source material'});
 expect(within(material).getByText('Brushed steel')).toBeTruthy();
 expect(within(material).getByText('#778899')).toBeTruthy();
 expect(within(material).getByText('Roughness')).toBeTruthy();
 expect(within(material).getByText('25%')).toBeTruthy();
 expect(within(material).getByText('Metalness')).toBeTruthy();
 expect(within(material).getByText('100%')).toBeTruthy();
 expect(within(material).queryByText('Steel')).toBeNull();
 expect(within(material).queryByRole('button')).toBeNull();
});

it('material details follow the reference being browsed within a multi-selection',()=>{
 const references=['o1','o2'].map(id=>({id:`${id}.f1`,normalizedSelector:`${id}.f1`,selectorType:'face',pickData:{surfaceType:'plane'}}));
 const meshData={parts:[{occurrenceId:'o1',sourceColor:'#778899'},{occurrenceId:'o2',sourceColor:'#222222'}]};
 const sourceAppearance={materials:{steel:{name:'Steel'},rubber:{name:'Rubber'}},assignments:{o1:'steel',o2:'rubber'}};
 render(<StepReferenceSection references={references} meshData={meshData} sourceAppearance={sourceAppearance}/>);
 const material=screen.getByRole('generic',{name:'Source material'});
 expect(within(material).getByText('Rubber')).toBeTruthy();
 browse('o1 · face 1');
 expect(within(material).getByText('Steel')).toBeTruthy();
 expect(within(material).queryByText('Rubber')).toBeNull();
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
 expect(screen.getByText('o1.1.e4')).toBeTruthy();
});
