import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ModelingTreeView from '../../../../../dist/renderers/cad/components/workbench/ModelingTree.js';

import { useStepModeling } from '../../../../../dist/renderers/cad/workbench/useStepModeling.js';
function ModelingTree(props:any) {
 const modeling=useStepModeling(props.entry,!props.disabled);
 return <ModelingTreeView {...props} modeling={modeling}/>;
}
Object.assign(globalThis,{React});
afterEach(()=>{cleanup();vi.unstubAllGlobals();WorkerStub.instances=[];});
const feature={id:'cut:1-2',kind:'cut',label:'Cut extrude 1',faces:[1,2],edges:[],measurements:[['Depth',2,'mm']],children:[]};
const tree=[{id:'body:1',kind:'body',label:'Body 1',faces:[1,2],edges:[],complete:true,children:[feature]}];
const refs=(o='o1')=>[1,2].map(n=>({id:`${o}.f${n}`,selectorType:'face',occurrenceId:o,normalizedSelector:`${o}.f${n}`}));
class WorkerStub {
 static instances:WorkerStub[]=[];
 terminate=vi.fn();postMessage=vi.fn();onmessage:((event:any)=>void)|null=null;
 constructor(){WorkerStub.instances.push(this);}
}
const entry={file:'case.step',kind:'part',url:'http://localhost/__cad/asset?file=/cache/case&v=one'};
const descriptor={components:{c:{surf:'components/c.surf'}},occurrences:[{id:'o1',component:'c',name:'Case'}]};
function setup(value=descriptor){
 vi.stubGlobal('Worker',WorkerStub);
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>value});vi.stubGlobal('fetch',fetch);return fetch;
}
async function respond(data:any,index=0){
 await waitFor(()=>expect(WorkerStub.instances.length).toBeGreaterThan(index));
 await act(async()=>WorkerStub.instances[index].onmessage?.({data}));
}
it('recognizes automatically while the inspector tab is inactive, and reuses its result on opening',async()=>{
 const fetch=setup(),onSelect=vi.fn();
 const props={entry,references:refs(),selectedReferenceIds:[],onSelect};
 const {rerender}=render(<ModelingTree {...props} active={false}/>);
 await respond({tree});
 expect(fetch).toHaveBeenCalledTimes(1);expect(WorkerStub.instances[0].terminate).toHaveBeenCalled();
 rerender(<ModelingTree {...props} active/>);
 fireEvent.click(await screen.findByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenCalledWith(['o1.f1','o1.f2']);expect(WorkerStub.instances).toHaveLength(1);
 expect(screen.queryByRole('button',{name:'Build modeling tree'})).toBeNull();
});
it('waits for every canonical face and cancels selection when its tab is inactive',async()=>{
 setup();const onSelect=vi.fn(),onLoadTopology=vi.fn();
 const props={active:true,entry,references:[],selectedReferenceIds:[],onSelect,onLoadTopology};
 const {rerender}=render(<ModelingTree {...props}/>);await respond({tree});
 fireEvent.click(await screen.findByRole('button',{name:'Select Cut extrude 1'}));
 expect(onLoadTopology).toHaveBeenCalledWith(['o1']);expect(onSelect).not.toHaveBeenCalled();
 rerender(<ModelingTree {...props} references={refs().slice(0,1)}/>);expect(onSelect).not.toHaveBeenCalled();
 rerender(<ModelingTree {...props} references={refs()}/>);await waitFor(()=>expect(onSelect).toHaveBeenCalledTimes(1));
 rerender(<ModelingTree {...props}/>);fireEvent.click(screen.getByRole('button',{name:'Select Cut extrude 1'}));
 rerender(<ModelingTree {...props} active={false}/>);rerender(<ModelingTree {...props} active={false} references={refs()}/>);
 expect(onSelect).toHaveBeenCalledTimes(1);
});
it('recognizes repeated parts once and scopes their selections to the correct occurrence',async()=>{
 setup({components:{c:{surf:'components/c.surf'}},occurrences:[{id:'o1',component:'c',name:'Left'},{id:'o2',component:'c',name:'Right'}]});
 const onSelect=vi.fn();render(<ModelingTree active entry={entry} references={[...refs('o1'),...refs('o2')]} selectedReferenceIds={[]} onSelect={onSelect}/>);
 await respond({tree});
 expect(WorkerStub.instances).toHaveLength(1);
 expect(screen.getByRole('button',{name:'Collapse Left'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Expand Right'}));
 const part=screen.getByRole('button',{name:'Select Right'}).closest('li')!;
 fireEvent.click(within(part).getByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenLastCalledWith(['o2.f1','o2.f2']);
});
it('continues past an unsupported first part and expands a recognized part automatically',async()=>{
 setup({components:{c:{surf:'components/c.surf'},d:{surf:'components/d.surf'}},occurrences:[{id:'o1',component:'c',name:'Bodywork'},{id:'o2',component:'d',name:'Wheel'}]});
 render(<ModelingTree active entry={entry}/>);
 await respond({tree:[{...tree[0],complete:false,children:[{id:'other',kind:'remainder',label:'Other geometry',faces:[1,2]}]}]});
 await respond({tree},1);
 expect(screen.getByRole('button',{name:'Expand Bodywork'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Collapse Wheel'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'})).toBeTruthy();
});
it('stops a worker on file disposal and ignores a late result',async()=>{
 setup();const {unmount}=render(<ModelingTree active entry={entry}/>);
 await waitFor(()=>expect(WorkerStub.instances).toHaveLength(1));const worker=WorkerStub.instances[0];
 unmount();expect(worker.terminate).toHaveBeenCalled();await act(async()=>worker.onmessage?.({data:{tree}}));
 expect(screen.queryByRole('button',{name:'Select Cut extrude 1'})).toBeNull();
});
it('retries failed components without rerunning successful ones',async()=>{
 setup({components:{c:{surf:'components/c.surf'},d:{surf:'components/d.surf'}},occurrences:[{id:'o1',component:'c',name:'Left'},{id:'o2',component:'d',name:'Right'}]});
 render(<ModelingTree active entry={entry}/>);
 await respond({tree});await respond({error:'Unavailable'},1);
 fireEvent.click(await screen.findByRole('button',{name:'Retry'}));
 await waitFor(()=>expect(WorkerStub.instances).toHaveLength(3));
 expect(WorkerStub.instances[2].postMessage).toHaveBeenCalledWith({url:expect.stringContaining('d.surf')});
 await respond({tree},2);expect(screen.queryByRole('alert')).toBeNull();
});
it('shows annotation-only data as empty instead of waiting for impossible selection',async()=>{
 setup();render(<ModelingTree active entry={entry}/>);await respond({tree:[]});
 expect(await screen.findByText('This component has no faces to inspect.')).toBeTruthy();
 expect(screen.queryByRole('button',{name:/^Select /})).toBeNull();
});
it('opens the part selected in Geometry without resetting its canonical selection',async()=>{
 setup({components:{c:{surf:'components/c.surf'}},occurrences:[{id:'o1',component:'c',name:'Left'},{id:'o2',component:'c',name:'Right'}]});
 const onSelect=vi.fn();render(<ModelingTree active entry={entry} selectedPartIds={['o2']} references={[...refs('o1'),...refs('o2')]} onSelect={onSelect}/>);
 await respond({tree});
 expect(screen.getByRole('button',{name:'Collapse Right'})).toBeTruthy();
 expect(onSelect).not.toHaveBeenCalled();
 const part=screen.getByRole('button',{name:'Select Right'}).closest('li')!;
 fireEvent.click(within(part).getByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenCalledWith(['o2.f1','o2.f2']);
});

it('inspects STEP features without requesting kernel replay',async()=>{
 const fetch=setup();render(<ModelingTree entry={entry} active/>);await respond({tree});
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'})).toBeTruthy();
 expect(fetch.mock.calls.every(([,init])=>!init?.method || init.method==='GET')).toBe(true);
 expect(screen.queryByRole('button',{name:/Play/})).toBeNull();
});

it('does not fetch geometry or start a worker when modeling is disabled',async()=>{
 const fetch=setup();
 render(<ModelingTree entry={entry} active disabled/>);
 await act(async()=>{});
 expect(fetch).not.toHaveBeenCalled();expect(WorkerStub.instances).toHaveLength(0);
});

it('highlights a picked face’s feature while preserving its precise reference and details',async()=>{
 setup();const onSelect=vi.fn();
 render(<ModelingTree active entry={entry} references={refs()} selectedReferenceIds={['o1.f1']} onSelect={onSelect} selectionDetails={<p>Picked face details</p>}/>);
 await respond({tree});
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'}).getAttribute('aria-pressed')).toBe('true');
 expect(screen.getByText('Picked face details')).toBeTruthy();
 expect(onSelect).not.toHaveBeenCalled();
});

it('keeps imported parts selectable and revealable before recognition finishes',async()=>{
 setup();const onSelectTreeNode=vi.fn(),onTogglePartVisibility=vi.fn();
 const stepRoot={id:'__step_model__',nodeType:'part',displayName:'Imported case',leafPartIds:['__model__'],children:[]};
 const props={entry,active:true,stepRoot,partControls:{onSelectTreeNode,onTogglePartVisibility,hiddenPartIds:[]}};
 const {rerender}=render(<ModelingTree {...props}/>);
 fireEvent.click(screen.getByRole('button',{name:'Select Imported case'}));
 expect(onSelectTreeNode).toHaveBeenCalledWith('__step_model__',expect.any(Object));
 fireEvent.click(screen.getByRole('button',{name:'Hide Imported case'}));
 expect(onTogglePartVisibility).toHaveBeenCalledWith('__step_model__');
 rerender(<ModelingTree {...props} partControls={{...props.partControls,hiddenPartIds:['__model__']}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Reveal Imported case'}));
 expect(onTogglePartVisibility).toHaveBeenCalledTimes(2);
 expect(screen.getByRole('button',{name:'Select Imported case'}).hasAttribute('disabled')).toBe(true);
 expect(screen.queryByRole('button',{name:'Isolate Imported case'})).toBeNull();
});

it('does not overwrite a newer viewport selection when a feature’s topology finishes loading',async()=>{
 setup();const onSelect=vi.fn();
 const props={active:true,entry,references:[],selectedReferenceIds:[],onSelect};
 const {rerender}=render(<ModelingTree {...props}/>);await respond({tree});
 fireEvent.click(screen.getByRole('button',{name:'Select Cut extrude 1'}));
 rerender(<ModelingTree {...props} selectedReferenceIds={['o1.e3']}/>);
 rerender(<ModelingTree {...props} selectedReferenceIds={['o1.e3']} references={refs()}/>);
 expect(onSelect).not.toHaveBeenCalled();
});
