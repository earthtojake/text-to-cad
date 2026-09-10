import React from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useAutomaticReconstruction } from '../../../../../dist/renderers/cad/workbench/useAutomaticReconstruction.js';
Object.assign(globalThis,{React});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const target={origin:'http://localhost',tree:'a'.repeat(64)};
const recipe={schema:1};
function Harness(props:any){const {statuses}=useAutomaticReconstruction(props);return <pre data-testid="states">{JSON.stringify(statuses)}</pre>;}
function setup(){
 const calls:any[]=[];
 vi.stubGlobal('fetch',vi.fn().mockImplementation((_url:any,options:any)=>new Promise(resolve=>calls.push({options,resolve}))));
 const finish=async (i:number,ok=true)=>act(async()=>{
  const body=JSON.parse(calls[i].options.body);
  calls[i].resolve({ok,json:async()=>ok?{status:'verified',tree:body.tree,component:body.component,proof:{passed:true},frameCount:2}:{error:'Cannot verify this part'}});
 });
 return {calls,finish};
}
it('automatically verifies all candidates serially and does not restart an in-flight part when more arrive',async()=>{
 const {calls,finish}=setup();const base={target,file:'imported.step',enabled:true};
 const {rerender}=render(<Harness {...base} results={{c:{recipe},partial:{tree:[]}}}/>);
 await waitFor(()=>expect(calls).toHaveLength(1));
 expect(JSON.parse(calls[0].options.body)).toMatchObject({component:'c',preview:false});
 rerender(<Harness {...base} results={{c:{recipe},d:{recipe},partial:{tree:[]}}}/>);
 expect(calls).toHaveLength(1);expect(calls[0].options.signal.aborted).toBe(false);
 await finish(0);await waitFor(()=>expect(calls).toHaveLength(2));
 expect(JSON.parse(calls[1].options.body).component).toBe('d');await finish(1);
 await waitFor(()=>expect(document.body.textContent).toContain('ready'));
 expect(calls).toHaveLength(2);
});
it('continues after a rejected part and prioritizes the selected part without fabricating a recipe for partial geometry',async()=>{
 const {calls,finish}=setup();
 render(<Harness target={target} file="assembly.step" enabled results={{c:{recipe},d:{recipe},partial:{tree:[]}}} preferredComponent="d"/>);
 await waitFor(()=>expect(calls).toHaveLength(1));expect(JSON.parse(calls[0].options.body).component).toBe('d');
 await finish(0,false);await waitFor(()=>expect(calls).toHaveLength(2));await finish(1);
 await waitFor(()=>expect(document.body.textContent).toContain('failed'));
 expect(calls).toHaveLength(2);
});
it('aborts and ignores the old document response when a different STEP opens',async()=>{
 const {calls,finish}=setup();const results={c:{recipe}};
 const {rerender}=render(<Harness target={target} file="first.step" enabled results={results}/>);
 await waitFor(()=>expect(calls).toHaveLength(1));
 const second={...target,tree:'b'.repeat(64)};
 rerender(<Harness target={second} file="second.step" enabled results={results}/>);
 await waitFor(()=>expect(calls).toHaveLength(2));expect(calls[0].options.signal.aborted).toBe(true);
 await finish(0);expect(document.body.textContent).not.toContain('ready');
 await finish(1);await waitFor(()=>expect(document.body.textContent).toContain('ready'));
});

it('does not submit verification when the experiment is off',async()=>{
 const {calls}=setup();
 render(<Harness target={target} file="model.step" enabled={false} results={{c:{recipe}}}/>);
 await act(async()=>{});
 expect(calls).toHaveLength(0);
});
