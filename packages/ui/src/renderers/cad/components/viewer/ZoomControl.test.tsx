import React from 'react';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {ZoomControl} from '../../../../../dist/renderers/cad/components/viewer/ZoomControl.js';

afterEach(cleanup);

it('shows a static zoom readout beside step and reset buttons',()=>{
 const change=vi.fn(),reset=vi.fn();
 const {rerender}=render(<ZoomControl zoomPercent={125} onZoomPercentChange={change} onZoomReset={reset}/>);
 const readout=screen.getByLabelText('Zoom level percent');
 expect(readout.tagName.toLowerCase()).toBe('span');
 expect(readout.textContent).toBe('125%');
 expect(screen.queryByRole('textbox',{name:'Zoom level percent'})).toBeNull();
 expect(screen.getByRole('group',{name:'Zoom controls'}).contains(readout)).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Zoom out'}));
 fireEvent.click(screen.getByRole('button',{name:'Zoom in'}));
 expect(change.mock.calls.map(([value])=>value)).toEqual([115,135]);
 fireEvent.click(screen.getByRole('button',{name:'Reset view'}));
 expect(reset).toHaveBeenCalledOnce();
 rerender(<ZoomControl zoomPercent={143.7} onZoomPercentChange={change} onZoomReset={reset}/>);
 expect(screen.getByLabelText('Zoom level percent').textContent).toBe('144%');
});
