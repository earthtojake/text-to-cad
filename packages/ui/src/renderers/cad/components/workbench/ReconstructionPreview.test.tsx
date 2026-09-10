import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ReconstructionPreview from '../../../../../dist/renderers/cad/components/workbench/ReconstructionPreview.js';
vi.mock('../../../../../dist/renderers/cad/components/workbench/ReconstructionViewport.js', () => ({ default: ({ frame, original }: any) => <div data-testid="preview-frame">{original ? 'original' : frame}</div> }));
Object.assign(globalThis,{React});
Element.prototype.scrollIntoView=vi.fn();
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers();});
const target={origin:'http://localhost',tree:'a'.repeat(64)};
const steps=[
 {id:'sketch',kind:'sketch',label:'Sketch 1',dependsOn:[],measurements:[]},
 {id:'base',kind:'extrude',label:'Base extrude',dependsOn:['sketch'],measurements:[['Depth',5,'mm']]},
 {id:'cut',kind:'cut',label:'Cut extrude',dependsOn:['base','sketch'],measurements:[]},
];
const props={target,file:'imported.step',component:'c',recipe:{schema:1},label:'Imported part',onClose:vi.fn()};
function respond(result:any){vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>result}));}
const verified={status:'verified',tree:target.tree,component:'c',proof:{passed:true},steps};
it('starts complete, follows inputs, compares original, and replays actual frames',async()=>{
 respond(verified);render(<ReconstructionPreview {...props}/>);
 expect(await screen.findByText('Final geometry matches')).toBeTruthy();
 expect(screen.getByTestId('preview-frame').textContent).toBe('2');
 fireEvent.click(screen.getByRole('button',{name:'Base extrude',exact:true}));
 expect(screen.getByTestId('preview-frame').textContent).toBe('1');
 fireEvent.click(screen.getByRole('button',{name:'Original STEP',exact:true}));
 expect(screen.getByTestId('preview-frame').textContent).toBe('original');
 fireEvent.change(screen.getByRole('slider',{name:'Build step'}),{target:{value:'0'}});
 expect(screen.getByTestId('preview-frame').textContent).toBe('0');
 vi.useFakeTimers();fireEvent.click(screen.getByRole('button',{name:'Play',exact:true}));
 await act(async()=>vi.advanceTimersByTime(1000));expect(screen.getByTestId('preview-frame').textContent).toBe('1');
 await act(async()=>vi.advanceTimersByTime(1000));expect(screen.getByTestId('preview-frame').textContent).toBe('2');
 expect(screen.getByRole('button',{name:'Replay',exact:true})).toBeTruthy();
});
it('never plays a rejected or mismatched proof',async()=>{
 respond({...verified,component:'another-part'});render(<ReconstructionPreview {...props}/>);
 expect((await screen.findByRole('alert')).textContent).toContain('does not match');
 expect(screen.queryByRole('slider')).toBeNull();
});
it('closing an unfinished verification aborts the request',async()=>{
 const fetch=vi.fn().mockImplementation(()=>new Promise(()=>{}));vi.stubGlobal('fetch',fetch);
 const {unmount}=render(<ReconstructionPreview {...props}/>);
 await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));const signal=fetch.mock.calls[0][1].signal;
 unmount();expect(signal.aborted).toBe(true);
});
