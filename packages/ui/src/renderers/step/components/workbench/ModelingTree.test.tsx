import React from 'react';
import { createCadClient } from '@hardcore/core/client';
let client: ReturnType<typeof createCadClient>;
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ModelingTreeView from '../../../../../dist/renderers/step/components/workbench/ModelingTree.js';
import { HostReferenceContext } from '../../../../../dist/renderers/step/file-view/hostReference.js';

import { useStepModeling } from '../../../../../dist/renderers/step/workbench/useStepModeling.js';
function ModelingTree(props:any) {
 const modeling=useStepModeling(props.entry,!props.disabled,{client,requestedOccurrenceIds:fixtureDescriptor.occurrences.map(o=>o.id)});
 return <ModelingTreeView {...props} modeling={modeling}/>;
}
Object.assign(globalThis,{React});
afterEach(()=>{cleanup();client?.dispose();vi.unstubAllGlobals();WorkerStub.instances=[];});
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
let fixtureVersion=0;
let fixtureDescriptor=descriptor;
function expandIfCollapsed(label:string){ const trigger=screen.queryByRole('button',{name:`Expand ${label}`});if(trigger)fireEvent.click(trigger); }
function setup(value=descriptor){
 fixtureDescriptor=value;
 entry.url=`http://localhost/__cad/asset?file=/cache/case&v=fixture-${++fixtureVersion}`;
 vi.stubGlobal('Worker',WorkerStub);
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>value});vi.stubGlobal('fetch',fetch);client=createCadClient();return fetch;
}
async function respond(data:any,index=0){
 await waitFor(()=>expect(WorkerStub.instances.length).toBeGreaterThan(index));
 await act(async()=>WorkerStub.instances[index].onmessage?.({data}));
}
it('renders previously requested recognition when the inspector opens',async()=>{
 const fetch=setup(),onSelect=vi.fn();
 const props={entry,references:refs(),selectedReferenceIds:[],onSelect};
 const {rerender}=render(<ModelingTree {...props} active={false}/>);
 await respond({tree});expandIfCollapsed('Body 1');
 expect(fetch).toHaveBeenCalledTimes(1);expect(WorkerStub.instances[0].terminate).toHaveBeenCalled();
 rerender(<ModelingTree {...props} active/>);
 fireEvent.click(await screen.findByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenCalledWith(['o1.f1','o1.f2']);expect(WorkerStub.instances).toHaveLength(1);
 expect(screen.queryByRole('button',{name:'Build modeling tree'})).toBeNull();
});
it('waits for every canonical face and cancels selection when its tab is inactive',async()=>{
 setup();const onSelect=vi.fn(),onLoadTopology=vi.fn();
 const props={active:true,entry,references:[],selectedReferenceIds:[],onSelect,onLoadTopology};
 const {rerender}=render(<ModelingTree {...props}/>);await respond({tree});expandIfCollapsed('Body 1');
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
 await respond({tree});expandIfCollapsed('Body 1');
 expect(WorkerStub.instances).toHaveLength(1);
 expect(screen.getByRole('button',{name:'Expand Left'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Expand Right'}));
 const part=screen.getByRole('button',{name:'Select Right'}).closest('li')!;
 fireEvent.click(within(part).getByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenLastCalledWith(['o2.f1','o2.f2']);
});
it('keeps both unsupported and recognized parts collapsed until explicitly expanded',async()=>{
 setup({components:{c:{surf:'components/c.surf'},d:{surf:'components/d.surf'}},occurrences:[{id:'o1',component:'c',name:'Bodywork'},{id:'o2',component:'d',name:'Wheel'}]});
 render(<ModelingTree active entry={entry}/>);
 await respond({tree:[{...tree[0],complete:false,children:[{id:'other',kind:'remainder',label:'Other geometry',faces:[1,2]}]}]});
 await respond({tree},1);
 expect(screen.getByRole('button',{name:'Expand Bodywork'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Expand Wheel'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Expand Wheel'}));
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
 await respond({tree});expandIfCollapsed('Body 1');await respond({error:'Unavailable'},1);
 fireEvent.click(await screen.findByRole('button',{name:'Retry'}));
 await waitFor(()=>expect(WorkerStub.instances).toHaveLength(3));
 expect(WorkerStub.instances[2].postMessage).toHaveBeenCalledWith({resource:{kind:'url',url:expect.stringContaining('d.surf'),maxBytes:16*1024*1024}},[]);
 await respond({tree},2);expect(screen.queryByRole('alert')).toBeNull();
});
it('shows annotation-only data as empty instead of waiting for impossible selection',async()=>{
 setup();render(<ModelingTree active entry={entry}/>);await respond({tree:[]});
 expect(await screen.findByText('This component has no faces to inspect.')).toBeTruthy();
 expect(screen.queryByRole('button',{name:/^Select /})).toBeNull();
});
it('reveals a part selected in Geometry without opening its topology or resetting selection',async()=>{
 setup({components:{c:{surf:'components/c.surf'}},occurrences:[{id:'o1',component:'c',name:'Left'},{id:'o2',component:'c',name:'Right'}]});
 const onSelect=vi.fn();render(<ModelingTree active entry={entry} selectedPartIds={['o2']} references={[...refs('o1'),...refs('o2')]} onSelect={onSelect}/>);
 await respond({tree});expandIfCollapsed('Body 1');
 expect(screen.getByRole('button',{name:'Expand Right'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Expand Right'}));
 expect(onSelect).not.toHaveBeenCalled();
 const part=screen.getByRole('button',{name:'Select Right'}).closest('li')!;
 fireEvent.click(within(part).getByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenCalledWith(['o2.f1','o2.f2']);
});

it('inspects STEP features without requesting kernel replay',async()=>{
 const fetch=setup();render(<ModelingTree entry={entry} active/>);await respond({tree});expandIfCollapsed('Body 1');
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
 await respond({tree});expandIfCollapsed('Body 1');
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
 const {rerender}=render(<ModelingTree {...props}/>);await respond({tree});expandIfCollapsed('Body 1');
 fireEvent.click(screen.getByRole('button',{name:'Select Cut extrude 1'}));
 rerender(<ModelingTree {...props} selectedReferenceIds={['o1.e3']}/>);
 rerender(<ModelingTree {...props} selectedReferenceIds={['o1.e3']} references={refs()}/>);
 expect(onSelect).not.toHaveBeenCalled();
});
it('uses one static Reference heading and clears through the host',async()=>{
 setup();const onClearSelection=vi.fn();
 const props={active:true,entry,references:refs(),selectedReferences:refs(),selectedReferenceIds:refs().map(r=>r.id),selectionDetails:<p>Face measurements</p>,onClearSelection};
 const {rerender}=render(<ModelingTree {...props}/>);await respond({tree});expandIfCollapsed('Body 1');
 expect(screen.getByRole('heading',{name:'Reference'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Hide selection details'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Clear selection'}));expect(onClearSelection).toHaveBeenCalledTimes(1);
 rerender(<ModelingTree {...props} selectedReferences={[]} selectedReferenceIds={[]} selectionDetails={null}/>);
 expect(screen.queryByRole('button',{name:'Clear selection'})).toBeNull();
});

const assemblyDescriptor={components:{c:{surf:'components/c.surf'}},occurrences:[{id:'arm.wrist',component:'c',name:'Wrist'},{id:'base',component:'c',name:'Base'}]};
const partNode=(id:string,name:string)=>({id,nodeType:'part',name,leafPartIds:[id],children:[]});
const assemblyRoot={id:'document',nodeType:'assembly',name:'tom',children:[{id:'arm',nodeType:'assembly',name:'Arm',leafPartIds:['arm.wrist'],children:[partNode('arm.wrist','Wrist')]},partNode('base','Base')]};
const directModeling={descriptor:assemblyDescriptor,results:{},error:null,retryFailed:vi.fn()};

it('double-click isolates subassemblies and components but copies topology references',()=>{
 const onFocusTreeNode=vi.fn(),onCopySelection=vi.fn();
 render(<ModelingTreeView modeling={{...directModeling,results:{c:{tree}}}}
  stepRoot={assemblyRoot} active references={refs('arm.wrist')}
  partControls={{isAssemblyView:true,expandedTreeNodeIds:['arm','arm.wrist'],onFocusTreeNode,onCopySelection}}/>);
 fireEvent.doubleClick(screen.getByRole('button',{name:'Select Arm',exact:true}));
 expect(onFocusTreeNode).toHaveBeenLastCalledWith('arm');
 fireEvent.doubleClick(screen.getByRole('button',{name:'Select Wrist',exact:true}));
 expect(onFocusTreeNode).toHaveBeenLastCalledWith('arm.wrist');
 expect(onCopySelection).not.toHaveBeenCalled();
 fireEvent.doubleClick(screen.getByRole('button',{name:'Select Cut extrude 1',exact:true}));
 expect(onCopySelection).toHaveBeenCalledTimes(1);
 expect(onFocusTreeNode).toHaveBeenCalledTimes(2);
});

it('starts the compact tree immediately below the filter and keeps disclosure separate from selection',()=>{
 const onSelectTreeNode=vi.fn(),onToggleTreeNode=vi.fn(),onLoadTopology=vi.fn();
 const controls={expandedTreeNodeIds:[],onSelectTreeNode,onToggleTreeNode};
 const props={modeling:directModeling,stepRoot:assemblyRoot,active:true,onLoadTopology,partControls:controls};
 const {rerender}=render(<ModelingTreeView {...props}/>);
 expect(screen.queryByRole('button',{name:'Select tom'})).toBeNull();
 const filter=screen.getByRole('textbox',{name:'Filter model'}).parentElement!.parentElement!;
 expect(screen.queryByLabelText('Model tree summary')).toBeNull();
 expect(screen.queryByText('2 features')).toBeNull();
 expect(screen.queryByText(/Recognizing/)).toBeNull();
 const select=screen.getByRole('button',{name:'Select Arm'});
 expect(select.parentElement?.style.height).toBe('28px');
 fireEvent.click(screen.getByRole('button',{name:'Expand Arm'}));
 expect(onToggleTreeNode).toHaveBeenCalledWith('arm');
 expect(onSelectTreeNode).not.toHaveBeenCalled();
 fireEvent.click(select);
 expect(onSelectTreeNode).toHaveBeenCalledWith('arm',expect.any(Object));
 expect(onLoadTopology).not.toHaveBeenCalled();
 expect(screen.queryByRole('button',{name:'Isolate Arm'})).toBeNull();
 const eye=screen.getByRole('button',{name:'Hide Arm'});
 expect(eye.className).toContain('text-muted-foreground');
 rerender(<ModelingTreeView {...props} partControls={{...controls,hiddenPartIds:['base']}}/>);
 expect(within(filter).getByRole('button',{name:'Show all'})).toBeTruthy();
});

it('requests recognition only for visible expanded parts, never row selection or collapsed descendants',()=>{
 const request=vi.fn(),onToggleTreeNode=vi.fn(),onSelectTreeNode=vi.fn();
 const props={modeling:directModeling,stepRoot:assemblyRoot,active:true,onRequestRecognition:request};
 const {rerender}=render(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds:[],onToggleTreeNode,onSelectTreeNode}}/>);
 expect(request).toHaveBeenLastCalledWith([]);
 fireEvent.click(screen.getByRole('button',{name:'Select Base'}));
 expect(request).toHaveBeenCalledTimes(1);
 rerender(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds:['arm'],onToggleTreeNode}}/>);
 expect(screen.getByRole('button',{name:'Expand Wrist'})).toBeTruthy();
 expect(request).toHaveBeenCalledTimes(1);
 rerender(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds:['arm','arm.wrist'],onToggleTreeNode}}/>);
 expect(request).toHaveBeenLastCalledWith(['arm.wrist']);
 rerender(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds:['arm.wrist'],onToggleTreeNode}}/>);
 expect(request).toHaveBeenLastCalledWith([]);
});

it('does not inherit isolate restrictions from an unavailable ancestor into the isolated subtree',()=>{
 const modeling={...directModeling,results:{c:{tree}}};
 const controls={expandedTreeNodeIds:['arm','arm.wrist'],selectableNodeIds:['arm.wrist'],focusedNodeIds:['arm.wrist'],isAssemblyView:true};
 const props={modeling,stepRoot:assemblyRoot,active:true,references:refs('arm.wrist'),partControls:controls};
 const {rerender}=render(<ModelingTreeView {...props}/>);
 expect(screen.getByRole('button',{name:'Select Arm'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Wrist'}).hasAttribute('disabled')).toBe(false);
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'}).hasAttribute('disabled')).toBe(false);
 rerender(<ModelingTreeView {...props} partControls={{...controls,hiddenPartIds:['arm.wrist']}}/>);
 expect(screen.getByRole('button',{name:'Select Wrist'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'}).hasAttribute('disabled')).toBe(true);
});

it('reveals selection once, allows subsequent scrolling/collapse, and honors a new explicit reveal',()=>{
 const scroll=vi.fn();
 const previous=HTMLElement.prototype.scrollIntoView;
 HTMLElement.prototype.scrollIntoView=scroll;
 try{
  const modeling={...directModeling,results:{c:{tree}}};
  const props={modeling,stepRoot:assemblyRoot,active:true,selectedPartIds:['arm.wrist']};
  const {rerender}=render(<ModelingTreeView {...props}/>);
  expect(screen.getByRole('button',{name:'Select Wrist'})).toBeTruthy();
  expect(scroll).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button',{name:'Collapse Arm'}));
  expect(screen.queryByRole('button',{name:'Select Wrist'})).toBeNull();
  rerender(<ModelingTreeView {...props} modeling={{...modeling,results:{c:{tree:[...tree]}}}}/>);
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button',{name:'Select Wrist'})).toBeNull();
  rerender(<ModelingTreeView {...props} activeTreeNodeScrollKey={1}/>);
  expect(screen.getByRole('button',{name:'Select Wrist'})).toBeTruthy();
  expect(scroll).toHaveBeenCalledTimes(2);
 }finally{HTMLElement.prototype.scrollIntoView=previous;}
});

it('keeps feature summaries and measurements below the tree instead of truncating rows',()=>{
 const modeling={...directModeling,results:{c:{tree}}};
 render(<ModelingTreeView modeling={modeling} stepRoot={assemblyRoot} active selectedPartIds={['arm.wrist']} partControls={{expandedTreeNodeIds:['arm','arm.wrist']}}/>);
 const row=screen.getByRole('button',{name:'Select Wrist'});
 expect(row.textContent).toBe('Wrist');
 expect(screen.getByText('1 feature')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'}).textContent).toBe('Cut extrude 1');
});

it('does not request recognition for hidden or excluded isolated parts, while allowing an isolated descendant',()=>{
 const request=vi.fn();
 const props={modeling:directModeling,stepRoot:assemblyRoot,active:true,onRequestRecognition:request};
 const expandedTreeNodeIds=['arm','arm.wrist','base'];
 const {rerender}=render(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds,hiddenPartIds:['base']}}/>);
 expect(request).toHaveBeenLastCalledWith(['arm.wrist']);
 rerender(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds,selectableNodeIds:['arm.wrist']}}/>);
 expect(request).toHaveBeenLastCalledWith(['arm.wrist']);
 rerender(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds,selectableNodeIds:['arm.wrist'],hiddenPartIds:['arm.wrist']}}/>);
 expect(request).toHaveBeenLastCalledWith([]);
});

it('selects a collapsed feature group without expanding its children through canonical selection feedback',()=>{
 const groupTree=[{...tree[0],children:Array.from({length:6},(_,index)=>({...feature,id:`pocket:${index}`,kind:'pocket',label:`Pocket ${index}`,faces:[index+1]}))}];
 const modeling={...directModeling,results:{c:{tree:groupTree}}};
 const references=Array.from({length:6},(_,index)=>({id:`arm.wrist.f${index+1}`,selectorType:'face',occurrenceId:'arm.wrist',normalizedSelector:`arm.wrist.f${index+1}`}));
 const onSelect=vi.fn();
 const props={modeling,stepRoot:assemblyRoot,active:true,references,onSelect,partControls:{expandedTreeNodeIds:['arm','arm.wrist']}};
 const {rerender}=render(<ModelingTreeView {...props}/>);
 fireEvent.click(screen.getByRole('button',{name:'Select Pockets (6)'}));
 expect(onSelect).toHaveBeenCalledWith(references.map(ref=>ref.id));
 rerender(<ModelingTreeView {...props} selectedReferenceIds={references.map(ref=>ref.id)}/>);
 expect(screen.getByRole('button',{name:'Expand Pockets (6)'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Select Pocket 0'})).toBeNull();
});

it('preserves a collapsed group when viewport selection sends its exact visible canonical bundle',()=>{
 const groupTree=[{...tree[0],children:Array.from({length:6},(_,index)=>({...feature,id:`pocket:${index}`,kind:'pocket',label:`Pocket ${index}`,faces:[index+1]}))}];
 const modeling={...directModeling,results:{c:{tree:groupTree}}};
 const references=Array.from({length:6},(_,index)=>({id:`arm.wrist.f${index+1}`,selectorType:'face',occurrenceId:'arm.wrist',normalizedSelector:`arm.wrist.f${index+1}`}));
 render(<ModelingTreeView modeling={modeling} stepRoot={assemblyRoot} active references={references} selectedReferenceIds={references.map(ref=>ref.id)} partControls={{expandedTreeNodeIds:['arm','arm.wrist']}}/>);
 expect(screen.getByRole('button',{name:'Expand Pockets (6)'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Select Pockets (6)'}).getAttribute('aria-pressed')).toBe('true');
 expect(screen.queryByRole('button',{name:'Select Pocket 0'})).toBeNull();
});

// Model search: a flat ranked view over the same presented tree, never a
// filter over its expansion (see packages/ui/src/renderers/kit/inspector/modelTreeSearch.js).
const wheelsDescriptor={components:{c:{surf:'components/c.surf'}},occurrences:[{id:'w1',component:'c',name:'Left Wheel'},{id:'w2',component:'c',name:'Right Wheel'},{id:'w3',component:'c',name:'Rear Wheel'}]};
const wheelsRoot={id:'document',nodeType:'assembly',name:'doc',children:[partNode('w1','Left Wheel'),partNode('w2','Right Wheel'),partNode('w3','Rear Wheel')]};
const wheelsModeling={descriptor:wheelsDescriptor,results:{},error:null,retryFailed:vi.fn()};
// Feeds a hit's selection back as selectedPartIds/expandedTreeNodeIds, the way a
// real host does, so the reveal effect's ancestor-expansion can be observed.
function ControlledSearch({onSelectTreeNode,onToggleTreeNode,...props}:any){
 const [expandedTreeNodeIds,setExpanded]=React.useState<string[]>([]);
 const [selectedPartIds,setSelectedPartIds]=React.useState<string[]>([]);
 const toggle=(id:string)=>{onToggleTreeNode?.(id);setExpanded(current=>current.includes(id)?current:[...current,id]);};
 const select=(id:string,options:any)=>{onSelectTreeNode?.(id,options);setSelectedPartIds([id]);};
 return <ModelingTreeView {...props} selectedPartIds={selectedPartIds} partControls={{...props.partControls,expandedTreeNodeIds,onToggleTreeNode:toggle,onSelectTreeNode:select}}/>;
}

it('finds a nested part inside a collapsed subassembly, showing its owner path, without touching expansion or recognition',async()=>{
 const modeling={...directModeling,results:{c:{tree}}};
 const request=vi.fn(),onToggleTreeNode=vi.fn();
 render(<ModelingTreeView modeling={modeling} stepRoot={assemblyRoot} active onRequestRecognition={request} partControls={{expandedTreeNodeIds:[],onToggleTreeNode}}/>);
 expect(screen.queryByRole('button',{name:'Select Wrist'})).toBeNull();
 const callsBefore=request.mock.calls.length;
 fireEvent.change(screen.getByRole('textbox',{name:'Filter model'}),{target:{value:'Wrist'}});
 await screen.findByRole('list',{name:'Model search results'});
 const hit=screen.getByRole('button',{name:'Select Wrist'});
 expect(hit.title).toBe('Arm/Wrist');
 expect(within(hit).getByText('Arm')).toBeTruthy();
 expect(onToggleTreeNode).not.toHaveBeenCalled();
 expect(request.mock.calls.length).toBe(callsBefore);
});

it('expands a search hit’s collapsed ancestor once selected, then restores it collapsed and pressed after clearing',async()=>{
 const modeling={...directModeling,results:{c:{tree}}};
 const onSelectTreeNode=vi.fn(),onToggleTreeNode=vi.fn();
 render(<ControlledSearch modeling={modeling} stepRoot={assemblyRoot} active onSelectTreeNode={onSelectTreeNode} onToggleTreeNode={onToggleTreeNode}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Filter model'}),{target:{value:'Wrist'}});
 await screen.findByRole('list',{name:'Model search results'});
 fireEvent.click(screen.getByRole('button',{name:'Select Wrist'}));
 expect(onSelectTreeNode).toHaveBeenCalledWith('arm.wrist',expect.any(Object));
 await waitFor(()=>expect(onToggleTreeNode).toHaveBeenCalledWith('arm'));
 expect(screen.queryByRole('list',{name:'Model'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Clear filter'}));
 const wrist=await screen.findByRole('button',{name:'Select Wrist'});
 expect(wrist.getAttribute('aria-pressed')).toBe('true');
 expect(screen.getByRole('button',{name:'Collapse Arm'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Expand Wrist'})).toBeTruthy();
});

it('disables a hidden search hit and one outside the isolate frontier, like the tree rows they mirror',async()=>{
 render(<ModelingTreeView modeling={wheelsModeling} stepRoot={wheelsRoot} active partControls={{expandedTreeNodeIds:[],hiddenPartIds:['w1'],selectableNodeIds:['w1','w3']}}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Filter model'}),{target:{value:'Wheel'}});
 await screen.findByRole('list',{name:'Model search results'});
 expect(screen.getByRole('button',{name:'Select Left Wheel'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Right Wheel'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Rear Wheel'}).hasAttribute('disabled')).toBe(false);
});

it('clears the search on Escape and selects the second hit with ArrowDown then Enter',async()=>{
 const onSelectTreeNode=vi.fn();
 render(<ModelingTreeView modeling={wheelsModeling} stepRoot={wheelsRoot} active partControls={{expandedTreeNodeIds:[],onSelectTreeNode}}/>);
 const input=screen.getByRole('textbox',{name:'Filter model'});
 fireEvent.change(input,{target:{value:'Wheel'}});
 const list=await screen.findByRole('list',{name:'Model search results'});
 const rows=within(list).getAllByRole('listitem');
 expect(rows.length).toBe(3);
 const secondLabel=within(rows[1]).getByRole('button',{name:/^Select /}).getAttribute('aria-label');
 const idByLabel:Record<string,string>={'Select Left Wheel':'w1','Select Right Wheel':'w2','Select Rear Wheel':'w3'};
 fireEvent.keyDown(input,{key:'ArrowDown'});
 fireEvent.keyDown(input,{key:'Enter'});
 expect(onSelectTreeNode).toHaveBeenCalledWith(idByLabel[secondLabel as string],expect.any(Object));
 fireEvent.keyDown(input,{key:'Escape'});
 await waitFor(()=>expect(screen.queryByRole('list',{name:'Model search results'})).toBeNull());
 expect(screen.getByRole('list',{name:'Model'})).toBeTruthy();
 expect((input as HTMLInputElement).value).toBe('');
});

it('finds a recognized feature by label and selects its scoped canonical references',async()=>{
 // Both occurrences share component 'c', so this label is shared by Wrist's and
 // Base's features too; scope to Wrist's row by its search-index node id.
 const modeling={...directModeling,results:{c:{tree}}};
 const onSelect=vi.fn();
 render(<ModelingTreeView modeling={modeling} stepRoot={assemblyRoot} active references={refs('arm.wrist')} onSelect={onSelect}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Filter model'}),{target:{value:'Cut extrude'}});
 const list=await screen.findByRole('list',{name:'Model search results'});
 const row=list.querySelector('[data-search-row="arm.wrist/cut:1-2"]') as HTMLElement;
 const hit=within(row).getByRole('button',{name:'Select Cut extrude 1'});
 fireEvent.click(hit);
 expect(onSelect).toHaveBeenCalledWith(['arm.wrist.f1','arm.wrist.f2']);
});


it('clears selection only from empty tree space, not a row or its controls',()=>{
 const clear=vi.fn(),select=vi.fn();
 render(<ModelingTreeView modeling={directModeling} stepRoot={assemblyRoot} active onClearSelection={clear} partControls={{onSelectTreeNode:select}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Select Base'}));
 expect(select).toHaveBeenCalledOnce();expect(clear).not.toHaveBeenCalled();
 fireEvent.click(screen.getByLabelText('Model tree area'));
 expect(clear).toHaveBeenCalledOnce();
});

it('opens a lone part implicitly, requests its recognition and topology once, and presents its features directly',()=>{
 const onLoadTopology=vi.fn(),request=vi.fn(),onSelect=vi.fn();
 const stepRoot={id:'__step_model__',nodeType:'part',name:'Case',leafPartIds:['__model__'],children:[]};
 const props={active:true,stepRoot,onLoadTopology,onSelect,onRequestRecognition:request,references:refs()};
 const {rerender}=render(<ModelingTreeView {...props} modeling={{descriptor,results:{},error:null}}/>);
 expect(onLoadTopology).toHaveBeenCalledExactlyOnceWith(['o1']);
 expect(request).toHaveBeenLastCalledWith(['o1']);
 expect(screen.getByText('Loading features…')).toBeTruthy();
 rerender(<ModelingTreeView {...props} modeling={{descriptor,results:{c:{tree}},error:null}}/>);
 expect(onLoadTopology).toHaveBeenCalledTimes(1);
 expect(screen.queryByRole('button',{name:'Select Case'})).toBeNull();
 expect(screen.queryByRole('button',{name:'Expand Body 1'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Select Cut extrude 1'}));
 expect(onSelect).toHaveBeenCalledWith(['o1.f1','o1.f2']);
 rerender(<ModelingTreeView {...props} modeling={{descriptor,results:{c:{tree}},error:null}} partControls={{hiddenPartIds:['__model__']}}/>);
 expect(screen.getByRole('button',{name:'Select Cut extrude 1'}).hasAttribute('disabled')).toBe(true);
 expect(request).toHaveBeenLastCalledWith([]);
});

it('blank-area deselection cancels pending geometry selection',async()=>{
 setup();const clear=vi.fn(),onSelect=vi.fn();
 const props={active:true,entry,references:[],selectedReferenceIds:[],onSelect,onClearSelection:clear};
 const {rerender}=render(<ModelingTree {...props}/>);await respond({tree});
 fireEvent.click(screen.getByRole('button',{name:'Select Cut extrude 1'}));
 expect(screen.getByText('Loading selectable geometry…')).toBeTruthy();
 fireEvent.click(screen.getByLabelText('Model tree area'));
 rerender(<ModelingTree {...props} references={refs()}/>);
 expect(onSelect).not.toHaveBeenCalled();expect(clear).toHaveBeenCalledOnce();
 expect(screen.queryByRole('region',{name:'Reference details'})).toBeNull();
});

// A feature row stands for faces, not for a part: its menu is the viewport's menu over those
// faces (the host's `menuForReferences`), never its owning part's, and its Select is the row's
// own click. The host's descriptor is stubbed here; what is under test is what the ROW asks for.
function featureMenuSetup(references:any[]){
 vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}});
 const calls={onSelect:vi.fn(),onLoadTopology:vi.fn(),add:vi.fn(),select:vi.fn(),menuForNode:vi.fn()};
 const menuForReferences=vi.fn((ids:string[],label:string)=>({referenceId:ids[0]||'',referenceIds:ids,label,selected:false,
  copyText:ids.length?`case.step#${ids.join(',')}`:'',zoomSelectionAvailable:false,showIsolate:false,showHideOther:false,showVisibility:false}));
 const stepRoot={id:'__step_model__',nodeType:'part',name:'Case',leafPartIds:['__model__'],children:[]};
 const view=(refsNow:any[])=><HostReferenceContext.Provider value={{canAddToPrompt:true}}>
  <ModelingTreeView active stepRoot={stepRoot} onLoadTopology={calls.onLoadTopology} onSelect={calls.onSelect} references={refsNow}
   modeling={{descriptor,results:{c:{tree}},error:null}}
   partControls={{menuForNode:calls.menuForNode,menuForReferences,partMenuActions:{onAddToPrompt:calls.add,onSelect:calls.select}}}/>
 </HostReferenceContext.Provider>;
 const {rerender}=render(view(references));
 return {...calls,menuForReferences,rerender:(refsNow:any[])=>rerender(view(refsNow))};
}
const openRowMenu=async(label:string)=>{
 fireEvent.contextMenu(screen.getByRole('button',{name:`Select ${label}`}));
 return (await screen.findAllByRole('menuitem')).map(item=>item.textContent);
};
it('gives a feature row the viewport’s menu over its faces, not its part’s, and its Select is the row’s own click',async()=>{
 const menu=featureMenuSetup(refs());
 expect(await openRowMenu('Cut extrude 1')).toEqual(['Add to prompt','Copy Reference','Select','Zoom to fit','Zoom to selection']);
 expect(menu.menuForReferences).toHaveBeenLastCalledWith(['o1.f1','o1.f2'],'Cut extrude 1');
 expect(menu.menuForNode).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('menuitem',{name:'Add to prompt'}));
 expect(menu.add).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({referenceIds:['o1.f1','o1.f2'],copyText:'case.step#o1.f1,o1.f2'}));
 await waitFor(()=>expect(screen.queryByRole('menu')).toBeNull());
 await openRowMenu('Cut extrude 1');
 fireEvent.click(screen.getByRole('menuitem',{name:'Select'}));
 expect(menu.onSelect).toHaveBeenCalledExactlyOnceWith(['o1.f1','o1.f2']);
 expect(menu.select).not.toHaveBeenCalled();
});
it('asks for a feature row’s faces when its menu opens, and fills the menu in when they arrive',async()=>{
 const menu=featureMenuSetup([]);
 menu.onLoadTopology.mockClear();
 await openRowMenu('Cut extrude 1');
 expect(screen.getByRole('menuitem',{name:'Add to prompt'}).getAttribute('aria-disabled')).toBe('true');
 expect(menu.onLoadTopology).toHaveBeenCalledWith(['o1']);
 menu.rerender(refs());
 await waitFor(()=>expect(screen.getByRole('menuitem',{name:'Add to prompt'}).getAttribute('aria-disabled')).toBeNull());
 expect(menu.menuForReferences).toHaveBeenLastCalledWith(['o1.f1','o1.f2'],'Cut extrude 1');
});

const repeatedDescriptor={components:{c:{surf:'components/c.surf'},d:{surf:'components/d.surf'}},occurrences:[
 {id:'p1',component:'c',name:'Planter'},{id:'p2',component:'c',name:'Planter'},{id:'lid',component:'d',name:'Lid'}]};
const repeatedRoot={id:'document',nodeType:'assembly',name:'deck',children:[
 partNode('p1','plant_1_01'),partNode('p2','plant_1_02'),partNode('lid','lid')]};
const repeatedModeling={descriptor:repeatedDescriptor,results:{},error:null,retryFailed:vi.fn()};

it('folds repeated parts into one row and selects every instance it stands for',()=>{
 const onSelectTreeNode=vi.fn();
 render(<ModelingTreeView modeling={repeatedModeling} stepRoot={repeatedRoot} active partControls={{expandedTreeNodeIds:[],onSelectTreeNode}}/>);
 // One row for the repeat, the unrepeated part untouched, and neither instance drawn yet.
 expect(screen.getByRole('button',{name:'Select plant_1 (2)'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Select lid'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Select plant_1_01'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Expand plant_1 (2)'}));
 expect(screen.getByRole('button',{name:'Select plant_1_01'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Select plant_1_02'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Select plant_1 (2)'}));
 expect(onSelectTreeNode.mock.calls).toEqual([['p1',{multiSelect:false}],['p2',{multiSelect:true}]]);
});

it('a folded row reads as selected only when the selection is what it stands for',()=>{
 const props={modeling:repeatedModeling,stepRoot:repeatedRoot,active:true};
 const {rerender}=render(<ModelingTreeView {...props} selectedPartIds={['p1']}/>);
 expect(screen.getByRole('button',{name:'Select plant_1 (2)'}).getAttribute('aria-pressed')).toBe('false');
 rerender(<ModelingTreeView {...props} selectedPartIds={['p1','p2']}/>);
 expect(screen.getByRole('button',{name:'Select plant_1 (2)'}).getAttribute('aria-pressed')).toBe('true');
});
