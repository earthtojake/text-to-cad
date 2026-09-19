import React from 'react';
import {cleanup,fireEvent,render as renderComponent,screen,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {StepReferenceSection} from '../../../../../dist/renderers/cad/components/workbench/StepReferenceSection.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../host/testing/host.js';
const host = testHost();
const render = (element: React.ReactNode) => renderComponent(element, { wrapper: ({children}) => <ViewerHostContext.Provider value={host}>{children}</ViewerHostContext.Provider> });
Object.assign(globalThis,{React});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const arc={id:'o1.e1',normalizedSelector:'o1.e1',selectorType:'edge',pickData:{curveType:'circle',length:7.8,params:{radius:5,sweepRadians:Math.PI/2,center:[0,0,0]},center:[3,3,0]}};

it('shows arc dimensions and analytic center coordinates immediately without a nested disclosure',()=>{
 const {container}=render(<StepReferenceSection references={[arc]}/>);
 expect(screen.getByText('Diameter Ø')).toBeTruthy();
 expect(screen.getByText('Sweep angle')).toBeTruthy();
 expect(screen.getByText('90 °')).toBeTruthy();
 const center=screen.getByText('Center').parentElement!;
 expect(within(center).getAllByText('0')).toHaveLength(3);
 expect(center.closest('details')).toBeNull();
 expect(container.querySelector('details')).toBeNull();
 expect(screen.queryByText('Details')).toBeNull();
 expect(screen.queryByRole('group',{name:'Selected element navigation'})).toBeNull();
});

it('keeps selection totals while browsing individual selected edges in the item header',()=>{
 const refs=[3,4].map((length,i)=>({id:`o1.e${i}`,selectorType:'edge',normalizedSelector:`o1.e${i}`,pickData:{curveType:'line',length}}));
 render(<StepReferenceSection references={refs}/>);
 expect(screen.getByText('Total length')).toBeTruthy();expect(screen.getByText('7 mm')).toBeTruthy();
 const header=screen.getByRole('banner',{name:'Selected reference'});
 const navigation=within(header).getByRole('group',{name:'Selected element navigation'});
 expect(within(navigation).getByText('2 / 2')).toBeTruthy();
 fireEvent.click(within(navigation).getByRole('button',{name:'Previous element'}));
 expect(screen.getByText('7 mm')).toBeTruthy();expect(screen.getByText('3 mm')).toBeTruthy();
 expect(within(header).getByText('o1.e0')).toBeTruthy();
 fireEvent.click(within(navigation).getByRole('button',{name:'Previous element'}));
 expect(within(header).getByText('o1.e1')).toBeTruthy();
});

it('updates always-visible coordinates and normal when the selected reference changes',()=>{
 const {rerender}=render(<StepReferenceSection references={[arc]}/>);
 const face={id:'o1.f2',normalizedSelector:'o1.f2',selectorType:'face',pickData:{surfaceType:'plane',center:[2,4,6],normal:[0,0,1],sourceName:'Camera'}};
 rerender(<StepReferenceSection references={[face]}/>);
 expect(screen.getByText('Center').closest('details')).toBeNull();
 expect(screen.getByText('Normal')).toBeTruthy();
 expect(screen.getByText('Camera')).toBeTruthy();
 expect(screen.queryByText('Details')).toBeNull();
 expect(screen.getByText('Planar')).toBeTruthy();
});

it('separates an assembly name, kind and canonical selector and preserves copy and newest-selection paging',()=>{
 const copy=vi.spyOn(host.clipboard,'writeText').mockResolvedValue();
 const name='camera_assembly_with_a_name_that_exceeds_the_panel_width';
 const selector='o1.8.1234567890.1234567890.1234567890.1234567890';
 const camera={id:selector,nodeType:'assembly',name,leafPartIds:['camera','mount'],children:[],bbox:{min:[0,0,0],max:[10,20,30]},copyText:'tom.step#camera'};
 const base={...camera,id:'o1.1',name:'Base',copyText:'tom.step#base'};
 const {rerender}=render(<StepReferenceSection references={[base,camera]}/>);
 const header=screen.getByRole('banner',{name:'Selected reference'});
 expect(within(header).getByText(name).getAttribute('title')).toBe(name);
 expect(within(header).getByText('Subassembly')).toBeTruthy();
 expect(within(header).getByText(selector)).toBeTruthy();
 expect(within(header).getByText(selector).className).not.toContain('truncate');
 expect(within(header).getByText('2 / 2')).toBeTruthy();
 expect(screen.getByText('Parts')).toBeTruthy();
 expect(screen.getByText('Center')).toBeTruthy();
 fireEvent.click(within(header).getByRole('button',{name:'Copy reference'}));
 expect(copy).toHaveBeenLastCalledWith('tom.step#camera');
 fireEvent.click(within(header).getByRole('button',{name:'Previous element'}));
 expect(within(header).getByText('Base')).toBeTruthy();
 rerender(<StepReferenceSection references={[base,camera,{...camera,id:'o1.9',name:'New part'}]}/>);
 expect(within(header).getByText('New part')).toBeTruthy();
 expect(within(header).getByText('3 / 3')).toBeTruthy();
});

it('keeps a single component header compact without losing its canonical path',()=>{
 render(<StepReferenceSection references={[{id:'o1.8',nodeType:'part',name:'Camera',leafPartIds:['o1.8'],children:[]}]}/>);
 const header=screen.getByRole('banner',{name:'Selected reference'});
 expect(within(header).getByText('Camera')).toBeTruthy();
 expect(within(header).getByText('Component')).toBeTruthy();
 expect(within(header).getByText('o1.8')).toBeTruthy();
 expect(within(header).getByRole('button',{name:'Copy reference'})).toBeTruthy();
 expect(screen.queryByRole('group',{name:'Selected element navigation'})).toBeNull();
 expect(screen.queryByText('Details')).toBeNull();
});

it('shows a read-only authored material summary for a face without turning its source color into a material name',()=>{
 const face={id:'o1.2.f4',normalizedSelector:'o1.2.f4',selectorType:'face',pickData:{surfaceType:'plane'}};
 const meshData={parts:[{occurrenceId:'o1.2',sourceColor:'#778899'}]};
 const sourceAppearance={
  materials:{steel:{name:'Brushed steel',roughness:0.25,metalness:1}},
  assignments:{'o1.2':'steel'}
 };
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
 fireEvent.click(screen.getByRole('button',{name:'Previous element'}));
 expect(within(material).getByText('Steel')).toBeTruthy();
 expect(within(material).queryByText('Rubber')).toBeNull();
});
