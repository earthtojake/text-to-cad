import React from 'react';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it} from 'vitest';
import {StepReferenceSection} from '../../../../../dist/renderers/cad/components/workbench/StepReferenceSection.js';
Object.assign(globalThis,{React});
afterEach(cleanup);
const arc={id:'o1.e1',normalizedSelector:'o1.e1',selectorType:'edge',pickData:{curveType:'circle',length:7.8,params:{radius:5,sweepRadians:Math.PI/2,center:[0,0,0]},center:[3,3,0]}};
it('puts arc dimensions first and keeps analytic center coordinates collapsed',()=>{
 render(<StepReferenceSection references={[arc]}/>);
 expect(screen.getByText('Diameter Ø')).toBeTruthy();expect(screen.getByText('Sweep angle')).toBeTruthy();expect(screen.getByText('90 °')).toBeTruthy();
 const details=screen.getByText('Details').closest('details')!;expect(details.open).toBe(false);
 fireEvent.click(screen.getByText('Details'));expect(details.open).toBe(true);expect(screen.getByText('Center')).toBeTruthy();
});
it('keeps selection totals while browsing individual selected edges',()=>{
 const refs=[3,4].map((length,i)=>({id:`o1.e${i}`,selectorType:'edge',normalizedSelector:`o1.e${i}`,pickData:{curveType:'line',length}}));
 render(<StepReferenceSection references={refs}/>);
 expect(screen.getByText('Total length')).toBeTruthy();expect(screen.getByText('7 mm')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Previous element'}));expect(screen.getByText('7 mm')).toBeTruthy();
 expect(screen.getByText('3 mm')).toBeTruthy();
});
it('resets coordinate disclosure when the selected reference changes',()=>{
 const {rerender}=render(<StepReferenceSection references={[arc]}/>);
 fireEvent.click(screen.getByText('Details'));rerender(<StepReferenceSection references={[{...arc,id:'o1.e2'}]}/>);
 expect(screen.getByText('Details').closest('details')!.open).toBe(false);
});
