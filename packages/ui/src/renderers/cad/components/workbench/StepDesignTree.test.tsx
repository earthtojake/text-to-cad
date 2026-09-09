import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import StepDesignTree from './StepDesignTree.jsx';
Object.assign(globalThis, { React });
afterEach(cleanup);
const result = {status:'ready',source:'case.py',parameters:[{name:'WALL',value:1.8,expression:'1.8'}],features:[{id:'extrude',label:'Extrude · body',type:'extrude',line:5,parameters:[{name:'depth',value:10,expression:'DEPTH'}],children:[{id:'sketch',label:'Sketch',type:'sketch',parameters:[],children:[]}]}]};
it('supplies labelled feature context to the shared viewer action without a separate sidebar button', async () => {
  const descriptor={area:1,center:[0,0,0],bbox:{min:[0,0,0],max:[1,1,0]}};
  const onHighlight=vi.fn();
  const client={requestDesignOutline:vi.fn().mockResolvedValue({...result,geometryLinks:{schema:1,faces:[descriptor],lines:{'5':[0]}}})};
  const props={client,file:'case.step',onHighlight};
  const {rerender}=render(<StepDesignTree {...props} references={[{id:'f7',selectorType:'face',pickData:descriptor}]} />);
  fireEvent.click(await screen.findByText('Extrude · body'));
  expect(onHighlight).toHaveBeenLastCalledWith({faceIds:['f7'],partIds:[]},'Extrude · body');
  expect(screen.queryByRole('button',{name:'Add to prompt',exact:true})).toBeNull();
  rerender(<StepDesignTree {...props} references={[]} />);
  expect(onHighlight).toHaveBeenLastCalledWith({faceIds:[],partIds:[]},'Extrude · body');
});
it('shows source parameters read-only and navigates nested operations with arrows', async () => {
  render(<StepDesignTree client={{requestDesignOutline:vi.fn().mockResolvedValue(result)}} file="case.step" label="case.step" />);
  const tree = screen.getByRole('tree', {name:'Features'});
  await screen.findByText('Extrude · body');
  const row = screen.getByRole('treeitem', {name:/Extrude/});
  fireEvent.click(row);
  expect(screen.getByRole('region', {name:'Feature properties'}).textContent).toContain('10');
  fireEvent.keyDown(row, {key:'ArrowRight'});
  expect(screen.getByText('Sketch')).toBeTruthy();
  fireEvent.keyDown(row, {key:'ArrowRight'});
  expect(document.activeElement?.textContent).toContain('Sketch');
  fireEvent.keyDown(document.activeElement!, {key:'ArrowLeft'});
  expect(document.activeElement).toBe(row);
  expect(tree.querySelectorAll('input,textarea,select').length).toBe(0);
  expect(screen.queryByText(/Source order, not evaluated build history/)).toBeNull();
});
it('aborts the old file and ignores its late source response', async () => {
  let resolveOld: (value: unknown) => void = () => {};
  let oldSignal: AbortSignal;
  const client = {requestDesignOutline:vi.fn((file, {signal}) => {
    if(file === 'old.step') {oldSignal=signal;return new Promise(resolve => {resolveOld=resolve;});}
    return Promise.resolve({status:'unavailable',features:[],parameters:[]});
  })};
  const {rerender} = render(<StepDesignTree client={client} file="old.step" label="old.step" />);
  rerender(<StepDesignTree client={client} file="new.step" label="new.step" />);
  await screen.findByText('Imported geometry');
  expect(oldSignal!.aborted).toBe(true);
  resolveOld(result);
  await waitFor(() => expect(screen.queryByText('Extrude · body')).toBeNull());
  expect(screen.getByText('new.step')).toBeTruthy();
});

it('previews associated faces on click and keyboard selection, then clears on Escape and unmount', async () => {
  const descriptor={area:1,center:[0,0,0],bbox:{min:[0,0,0],max:[1,1,0]}};
  const onHighlight=vi.fn();
  const client={requestDesignOutline:vi.fn().mockResolvedValue({...result,geometryLinks:{schema:1,faces:[descriptor],lines:{'5':[0]}}})};
  const {unmount}=render(<StepDesignTree client={client} file="case.step" label="case.step" references={[{id:'f7',selectorType:'face',pickData:descriptor}]} onHighlight={onHighlight} />);
  const text=await screen.findByText('Extrude · body');
  expect(onHighlight.mock.lastCall?.[0]).toBeNull();
  fireEvent.click(text);
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toEqual({faceIds:['f7'],partIds:[]}));
  onHighlight.mockClear();
  fireEvent.click(text);
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toEqual({faceIds:['f7'],partIds:[]}));
  fireEvent.keyDown(text.closest('[role="treeitem"]')!,{key:'Escape'});
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toBeNull());
  fireEvent.keyDown(screen.getByRole('treeitem',{name:'Parameters',exact:true}),{key:'ArrowDown'});
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toEqual({faceIds:['f7'],partIds:[]}));
  unmount();
  expect(onHighlight.mock.lastCall?.[0]).toBeNull();
});

it('groups assembly operations by part and selects global and operation parameters without editing values', async () => {
  const box={min:[0,0,0],max:[1,1,1]};
  const onHighlight=vi.fn();
  const client={requestDesignOutline:vi.fn().mockResolvedValue({...result,
    geometryLinks:{schema:1,parts:[{name:'Body',bbox:box}],partLines:{'5':[0]}},
    features:[{...result.features[0],parameters:[{name:'depth',value:10,expression:'WALL',sourceParameters:['WALL']}]}],
  })};
  render(<StepDesignTree client={client} file="case.step" parts={[{id:'body-7',name:'Body',bounds:box}]} onHighlight={onHighlight} />);
  const part=await screen.findByRole('treeitem',{name:'Body',exact:true});
  fireEvent.keyDown(part,{key:'ArrowRight'});
  fireEvent.click(screen.getByText('Extrude · body'));
  fireEvent.click(screen.getByRole('button',{name:'Highlight depth'}));
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toEqual({faceIds:[],partIds:['body-7']}));
  expect(screen.getByRole('button',{name:'Highlight depth'}).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByText('Parameters'));
  fireEvent.click(screen.getByRole('button',{name:'Highlight WALL'}));
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toEqual({faceIds:[],partIds:['body-7']}));
  expect(screen.getByRole('treeitem',{name:'WALL: 1.8',exact:true}).getAttribute('aria-selected')).toBe('true');
  fireEvent.keyDown(screen.getByRole('button',{name:'Highlight WALL'}),{key:'Escape'});
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toBeNull());
  expect(document.querySelectorAll('input,textarea,select').length).toBe(0);
});

it('uses existing part visibility and isolate actions without selecting or editing an operation', async () => {
  const box={min:[0,0,0],max:[1,1,1]};
  const client={requestDesignOutline:vi.fn().mockResolvedValue({...result,geometryLinks:{schema:1,parts:[{name:'Body',bbox:box}],partLines:{'5':[0]}}})};
  const actions={onIsolate:vi.fn(),onToggleVisibility:vi.fn(),onExitIsolate:vi.fn(),onExitAllIsolate:vi.fn(),hiddenIds:[],focusedIds:[]};
  const props={client,file:'case.step',parts:[{id:'o1',name:'Body',bounds:box}]};
  const {rerender}=render(<StepDesignTree {...props} partActions={actions} />);
  fireEvent.click(await screen.findByRole('button',{name:'Hide Body'}));
  expect(actions.onToggleVisibility).toHaveBeenCalledWith('o1');
  expect(screen.queryByRole('region',{name:'Feature properties'})).toBeNull();
  rerender(<StepDesignTree {...props} partActions={{...actions,hiddenIds:['o1']}} />);
  expect(screen.getByRole('button',{name:'Show Body'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Isolate Body'}));
  expect(actions.onIsolate).toHaveBeenCalledWith('o1');
  rerender(<StepDesignTree {...props} partActions={{...actions,focusedIds:['o1']}} />);
  fireEvent.click(screen.getByRole('button',{name:'Exit isolate for Body'}));
  expect(actions.onExitIsolate).toHaveBeenCalledWith('o1');
  fireEvent.click(screen.getByRole('button',{name:'Exit isolate',exact:true}));
  expect(actions.onExitAllIsolate).toHaveBeenCalled();
});

it('shows real imported parts and their dimensions without inventing source operations or parameters', async () => {
  const onHighlight=vi.fn();
  render(<StepDesignTree client={{requestDesignOutline:vi.fn().mockResolvedValue({status:'unavailable',features:[],parameters:[]})}} file="imported.step"
    parts={[{id:'o1',name:'Imported bracket',bounds:{min:[-5,2,0],max:[5,8,3]}}]} onHighlight={onHighlight} />);
  fireEvent.click(await screen.findByRole('button',{name:'Expand Imported geometry',exact:true}));
  fireEvent.click(screen.getByRole('treeitem',{name:'Imported bracket',exact:true}));
  expect(screen.getByRole('region',{name:'Feature properties'}).textContent).toContain('10 × 6 × 3 mm');
  expect(screen.queryByText('Source parameters')).toBeNull();
  expect(screen.queryByText('Face area')).toBeNull();
  await waitFor(()=>expect(onHighlight.mock.lastCall?.[0]).toEqual({faceIds:[],partIds:['o1']}));
  expect(onHighlight).toHaveBeenLastCalledWith({faceIds:[],partIds:['o1']},'Imported bracket');
});
