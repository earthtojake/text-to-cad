import React from 'react';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {StepReferenceSection} from '../../../../../dist/renderers/step/components/workbench/StepReferenceSection.js';
Object.assign(globalThis,{React});
beforeEach(()=>{
 vi.stubGlobal('ResizeObserver',class {observe(){} unobserve(){} disconnect(){}});
 vi.spyOn(HTMLElement.prototype,'scrollIntoView').mockImplementation(()=>{});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
// jsdom has no scrolling implementation.
HTMLElement.prototype.scrollIntoView ||= ()=>{};
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

it('keeps selection totals while directly browsing individual selected edges',()=>{
 const refs=[3,4].map((length,i)=>({id:`o1.e${i}`,selectorType:'edge',normalizedSelector:`o1.e${i}`,pickData:{curveType:'line',length}}));
 render(<StepReferenceSection references={refs}/>);
 expect(screen.getByText('Total length')).toBeTruthy();expect(screen.getByText('7 mm')).toBeTruthy();
 expect(screen.getByRole('combobox').textContent).toBe('Edge · o1.e1');
 browse('Edge · o1.e0');
 expect(screen.getByText('7 mm')).toBeTruthy();expect(screen.getByText('3 mm')).toBeTruthy();
 expect(screen.getByRole('combobox').textContent).toBe('Edge · o1.e0');
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

it('shows wrapping assembly facts and switches to the newest reference only when selection changes',()=>{
 const name='camera_assembly_with_a_name_that_exceeds_the_panel_width';
 const selector='o1.8.1234567890.1234567890.1234567890.1234567890';
 const camera={id:selector,nodeType:'assembly',name,leafPartIds:['camera','mount'],children:[],bbox:{min:[0,0,0],max:[10,20,30]},copyText:'tom.step#camera'};
 const base={...camera,id:'o1.1',name:'Base',copyText:'tom.step#base'};
 const {rerender}=render(<StepReferenceSection references={[base,camera]}/>);
 expect(screen.getByText(name)).toBeTruthy();
 expect(screen.getByText('Subassembly')).toBeTruthy();
 expect(screen.getByText(selector).className).not.toContain('truncate');
 expect(screen.getByText('Parts')).toBeTruthy();
 expect(screen.getByText('Center')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Copy reference'})).toBeNull();
 browse('Base · o1.1');
 expect(screen.getByText('Base')).toBeTruthy();
 rerender(<StepReferenceSection references={[{...base},{...camera}]}/>);
 expect(screen.getByText('Base')).toBeTruthy();
 rerender(<StepReferenceSection references={[base,camera,{...camera,id:'o1.9',name:'New part'}]}/>);
 expect(screen.getByText('New part')).toBeTruthy();
 expect(screen.getByRole('combobox').textContent).toBe('New part · o1.9');
});

it('shows a single component as compact read-only rows without losing its canonical path',()=>{
 render(<StepReferenceSection references={[{id:'o1.8',nodeType:'part',name:'Camera',leafPartIds:['o1.8'],children:[]}]}/>);
 expect(screen.getByText('Camera')).toBeTruthy();
 expect(screen.getByText('Component')).toBeTruthy();
 expect(screen.getByText('o1.8')).toBeTruthy();
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
 browse('Face · o1.f1');
 expect(within(material).getByText('Steel')).toBeTruthy();
 expect(within(material).queryByText('Rubber')).toBeNull();
});

it('retains bounding measurements as read-only facts when only part geometry is available',()=>{
 render(<StepReferenceSection measurements={{size:[10,20,30],radii:[]}}/>);
 expect(screen.getByText('10 × 20 × 30 mm')).toBeTruthy();
 expect(screen.queryByRole('button')).toBeNull();
});
