import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ModelingTreeView from '../../../../../dist/renderers/step/components/workbench/ModelingTree.js';

Object.assign(globalThis,{React});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const refs=(o='o1')=>[1,2].map(n=>({id:`${o}.f${n}`,selectorType:'face',occurrenceId:o,normalizedSelector:`${o}.f${n}`}));
const partNode=(id:string,name:string,componentId?:string)=>({id,nodeType:'part',name,leafPartIds:[id],children:[],...(componentId?{componentId}:{})});
const assemblyRoot={id:'document',nodeType:'assembly',name:'tom',children:[{id:'arm',nodeType:'assembly',name:'Arm',leafPartIds:['arm.wrist'],children:[partNode('arm.wrist','Wrist','c')]},partNode('base','Base','c')]};

it('double-click isolates subassemblies and components',()=>{
 const onFocusTreeNode=vi.fn();
 render(<ModelingTreeView stepRoot={assemblyRoot} active partControls={{isAssemblyView:true,expandedTreeNodeIds:['arm'],onFocusTreeNode}}/>);
 fireEvent.doubleClick(screen.getByRole('button',{name:'Select Arm',exact:true}));
 expect(onFocusTreeNode).toHaveBeenLastCalledWith('arm');
 fireEvent.doubleClick(screen.getByRole('button',{name:'Select Wrist',exact:true}));
 expect(onFocusTreeNode).toHaveBeenLastCalledWith('arm.wrist');
 expect(onFocusTreeNode).toHaveBeenCalledTimes(2);
});

it('starts the compact tree immediately below the filter and keeps disclosure separate from selection',()=>{
 const onSelectTreeNode=vi.fn(),onToggleTreeNode=vi.fn(),onLoadTopology=vi.fn();
 const controls={expandedTreeNodeIds:[],onSelectTreeNode,onToggleTreeNode};
 const props={stepRoot:assemblyRoot,active:true,onLoadTopology,partControls:controls};
 const {rerender}=render(<ModelingTreeView {...props}/>);
 expect(screen.queryByRole('button',{name:'Select tom'})).toBeNull();
 const filter=screen.getByRole('textbox',{name:'Filter model'}).parentElement!.parentElement!;
 expect(screen.queryByLabelText('Model tree summary')).toBeNull();
 const select=screen.getByRole('button',{name:'Select Arm'});
 expect(select.parentElement?.style.height).toBe('24px'); // the dense tree's rows
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

it('a part is a leaf in every mode: nothing opens under it, and only its assemblies have a disclosure',()=>{
 const props={stepRoot:assemblyRoot,active:true,partControls:{expandedTreeNodeIds:['arm','arm.wrist','base']}};
 const {rerender}=render(<ModelingTreeView {...props}/>);
 expect(screen.getByRole('button',{name:'Collapse Arm'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:/^(Expand|Collapse) (Wrist|Base)$/})).toBeNull();
 for(const mode of ['parts','faces','edges']){
  rerender(<ModelingTreeView {...props} mode={mode} partControls={{expandedTreeNodeIds:[]}}/>);
  // The mode holds every assembly open, locked; a part has no disclosure to hold.
  expect(screen.getByRole('button',{name:'Select Wrist'})).toBeTruthy();
  expect([...document.querySelectorAll('[data-disclosure-locked]')].map(mark=>(mark as HTMLElement).dataset.disclosureLocked)).toEqual(['open']);
  expect(screen.queryByRole('button',{name:/^(Expand|Collapse) /})).toBeNull();
 }
});

it('reveals a picked face at its part\'s row, opening the part\'s owners',()=>{
 const onToggleTreeNode=vi.fn();
 const props={stepRoot:assemblyRoot,active:true,selectedReferences:refs('arm.wrist')};
 const {rerender}=render(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds:[],onToggleTreeNode}}/>);
 expect(onToggleTreeNode).toHaveBeenCalledWith('arm');
 rerender(<ModelingTreeView {...props} partControls={{expandedTreeNodeIds:['arm'],onToggleTreeNode}}/>);
 expect(screen.getByRole('button',{name:'Select Wrist'}).getAttribute('aria-pressed')).toBe('true');
 expect(screen.getByRole('button',{name:'Select Base'}).getAttribute('aria-pressed')).toBe('false');
});

it('does not inherit isolate restrictions from an unavailable ancestor into the isolated subtree',()=>{
 const controls={expandedTreeNodeIds:['arm'],selectableNodeIds:['arm.wrist'],focusedNodeIds:['arm.wrist'],isAssemblyView:true};
 const props={stepRoot:assemblyRoot,active:true,partControls:controls};
 const {rerender}=render(<ModelingTreeView {...props}/>);
 expect(screen.getByRole('button',{name:'Select Arm'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Wrist'}).hasAttribute('disabled')).toBe(false);
 rerender(<ModelingTreeView {...props} partControls={{...controls,hiddenPartIds:['arm.wrist']}}/>);
 expect(screen.getByRole('button',{name:'Select Wrist'}).hasAttribute('disabled')).toBe(true);
});

it('reveals selection once, allows subsequent scrolling/collapse, and honors a new explicit reveal',()=>{
 const scroll=vi.fn();
 const previous=HTMLElement.prototype.scrollIntoView;
 HTMLElement.prototype.scrollIntoView=scroll;
 try{
  const props={stepRoot:assemblyRoot,active:true,selectedPartIds:['arm.wrist']};
  const {rerender}=render(<ModelingTreeView {...props}/>);
  expect(screen.getByRole('button',{name:'Select Wrist'})).toBeTruthy();
  expect(scroll).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button',{name:'Collapse Arm'}));
  expect(screen.queryByRole('button',{name:'Select Wrist'})).toBeNull();
  rerender(<ModelingTreeView {...props} stepRoot={{...assemblyRoot}}/>);
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button',{name:'Select Wrist'})).toBeNull();
  rerender(<ModelingTreeView {...props} activeTreeNodeScrollKey={1}/>);
  expect(screen.getByRole('button',{name:'Select Wrist'})).toBeTruthy();
  expect(scroll).toHaveBeenCalledTimes(2);
 }finally{HTMLElement.prototype.scrollIntoView=previous;}
});

// Model search: a flat ranked view over the same presented tree, never a
// filter over its expansion (see packages/ui/src/renderers/kit/inspector/modelTreeSearch.js).
const wheelsRoot={id:'document',nodeType:'assembly',name:'doc',children:[partNode('w1','Left Wheel','c'),partNode('w2','Right Wheel','c'),partNode('w3','Rear Wheel','c')]};
// Feeds a hit's selection back as selectedPartIds/expandedTreeNodeIds, the way a
// real host does, so the reveal effect's ancestor-expansion can be observed.
function ControlledSearch({onSelectTreeNode,onToggleTreeNode,...props}:any){
 const [expandedTreeNodeIds,setExpanded]=React.useState<string[]>([]);
 const [selectedPartIds,setSelectedPartIds]=React.useState<string[]>([]);
 const toggle=(id:string)=>{onToggleTreeNode?.(id);setExpanded(current=>current.includes(id)?current:[...current,id]);};
 const select=(id:string,options:any)=>{onSelectTreeNode?.(id,options);setSelectedPartIds([id]);};
 return <ModelingTreeView {...props} selectedPartIds={selectedPartIds} partControls={{...props.partControls,expandedTreeNodeIds,onToggleTreeNode:toggle,onSelectTreeNode:select}}/>;
}

it('finds a nested part inside a collapsed subassembly, showing its owner path, without touching expansion',async()=>{
 const onToggleTreeNode=vi.fn(),onLoadTopology=vi.fn();
 render(<ModelingTreeView stepRoot={assemblyRoot} active onLoadTopology={onLoadTopology} partControls={{expandedTreeNodeIds:[],onToggleTreeNode}}/>);
 expect(screen.queryByRole('button',{name:'Select Wrist'})).toBeNull();
 fireEvent.change(screen.getByRole('textbox',{name:'Filter model'}),{target:{value:'Wrist'}});
 await screen.findByRole('list',{name:'Model search results'});
 const hit=screen.getByRole('button',{name:'Select Wrist'});
 expect(hit.title).toBe(''); // no native tooltip competing with the shared hint
 expect(within(hit).getByText('Arm')).toBeTruthy();
 expect(onToggleTreeNode).not.toHaveBeenCalled();
 expect(onLoadTopology).not.toHaveBeenCalled();
});

it('expands a search hit’s collapsed ancestor once selected, then restores it collapsed and pressed after clearing',async()=>{
 const onSelectTreeNode=vi.fn(),onToggleTreeNode=vi.fn();
 render(<ControlledSearch stepRoot={assemblyRoot} active onSelectTreeNode={onSelectTreeNode} onToggleTreeNode={onToggleTreeNode}/>);
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
});

it('disables a hidden search hit and one outside the isolate frontier, like the tree rows they mirror',async()=>{
 render(<ModelingTreeView stepRoot={wheelsRoot} active partControls={{expandedTreeNodeIds:[],hiddenPartIds:['w1'],selectableNodeIds:['w1','w3']}}/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Filter model'}),{target:{value:'Wheel'}});
 await screen.findByRole('list',{name:'Model search results'});
 expect(screen.getByRole('button',{name:'Select Left Wheel'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Right Wheel'}).hasAttribute('disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Select Rear Wheel'}).hasAttribute('disabled')).toBe(false);
});

it('clears the search on Escape and selects the second hit with ArrowDown then Enter',async()=>{
 const onSelectTreeNode=vi.fn();
 render(<ModelingTreeView stepRoot={wheelsRoot} active partControls={{expandedTreeNodeIds:[],onSelectTreeNode}}/>);
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

it('clears selection only from empty tree space, not a row or its controls',()=>{
 const clear=vi.fn(),select=vi.fn();
 render(<ModelingTreeView stepRoot={assemblyRoot} active onClearSelection={clear} partControls={{onSelectTreeNode:select}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Select Base'}));
 expect(select).toHaveBeenCalledOnce();expect(clear).not.toHaveBeenCalled();
 fireEvent.click(screen.getByLabelText('Model tree area'));
 expect(clear).toHaveBeenCalledOnce();
});

const repeatedRoot={id:'document',nodeType:'assembly',name:'deck',children:[
 partNode('p1','plant_1_01','c'),partNode('p2','plant_1_02','c'),partNode('lid','lid','d')]};

it('folds repeated parts into one row and selects every instance it stands for',()=>{
 const onSelectTreeNode=vi.fn();
 render(<ModelingTreeView stepRoot={repeatedRoot} active partControls={{expandedTreeNodeIds:[],onSelectTreeNode}}/>);
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
 const props={stepRoot:repeatedRoot,active:true};
 const {rerender}=render(<ModelingTreeView {...props} selectedPartIds={['p1']}/>);
 expect(screen.getByRole('button',{name:'Select plant_1 (2)'}).getAttribute('aria-pressed')).toBe('false');
 rerender(<ModelingTreeView {...props} selectedPartIds={['p1','p2']}/>);
 expect(screen.getByRole('button',{name:'Select plant_1 (2)'}).getAttribute('aria-pressed')).toBe('true');
});

it('joins touching selected rows into one block, isolates from the row, and the isolation bar ends an isolation', () => {
  const onFocusTreeNode=vi.fn(),onUnfocusTreeNode=vi.fn(),onExitAllIsolate=vi.fn();
  const controls={expandedTreeNodeIds:['arm'],isAssemblyView:true,hiddenPartIds:[],focusedNodeIds:[] as string[],
    onSelectTreeNode:vi.fn(),onToggleTreeNode:vi.fn(),onTogglePartVisibility:vi.fn(),onFocusTreeNode,onUnfocusTreeNode,onExitAllIsolate};
  const props={stepRoot:assemblyRoot,active:true,selectedPartIds:['arm.wrist','base'],partControls:controls};
  const {rerender}=render(<ModelingTreeView {...props}/>);
  const surface=(name:string)=>screen.getByRole('button',{name:`Select ${name}`}).parentElement!;
  // Wrist sits directly above Base: the block squares off where they meet, and only there.
  expect(surface('Wrist').style.borderBottomLeftRadius).toBe('0px');
  expect(surface('Wrist').style.borderTopLeftRadius).toBe('');
  expect(surface('Base').style.borderTopLeftRadius).toBe('0px');
  expect(surface('Arm').style.borderBottomLeftRadius).toBe('');
  // Isolate sits left of Hide on the row; isolated, it stays lit and the tree says so at the top.
  const actions=screen.getByRole('button',{name:'Isolate Base'}).parentElement!;
  expect([...actions.querySelectorAll('button')].map(button=>button.getAttribute('aria-label'))).toEqual(['Isolate Base','Hide Base']);
  fireEvent.click(screen.getByRole('button',{name:'Isolate Base'}));
  expect(onFocusTreeNode).toHaveBeenCalledWith('base');
  rerender(<ModelingTreeView {...props} partControls={{...controls,focusedNodeIds:['base']}}/>);
  expect(screen.getByRole('button',{name:'Exit isolate Base'}).getAttribute('aria-pressed')).toBe('true');
  const bar=screen.getByRole('status',{name:'Isolation'});
  expect(bar.textContent).toContain('Isolated: Base');
  fireEvent.click(within(bar).getByRole('button',{name:'Exit'}));
  expect(onExitAllIsolate).toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Exit isolate Base'}));
  expect(onUnfocusTreeNode).toHaveBeenCalledWith('base');
});
