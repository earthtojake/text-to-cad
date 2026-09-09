import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import StepDesignTree from './StepDesignTree.jsx';
Object.assign(globalThis, { React });
afterEach(cleanup);
const result = {status:'ready',source:'case.py',parameters:[{name:'WALL',value:1.8,expression:'1.8'}],features:[{id:'extrude',label:'Extrude · body',type:'extrude',line:5,parameters:[{name:'depth',value:10,expression:'DEPTH'}],children:[{id:'sketch',label:'Sketch',type:'sketch',parameters:[],children:[]}]}]};
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
  expect(screen.getByText(/Source order, not evaluated build history/)).toBeTruthy();
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
