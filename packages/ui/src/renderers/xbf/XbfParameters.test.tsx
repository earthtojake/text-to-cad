import React from 'react';
import { act, cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FlatPanel from '../../../dist/renderers/kit/shell/FlatPanel.js';
import XbfParametersSection, { useXbfParameters } from '../../../dist/renderers/xbf/XbfParametersSection.js';
import { xbfPanelSections } from '../../../dist/renderers/xbf/XbfRenderer.js';
import QuickEdit from '../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

// The Parameters tab of an engine document's panel: a model's declared numbers as the structure
// serves them, edited as drafts, saved in one request through the client, said once to the agent.

Object.assign(globalThis, { React });
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView ||= () => {};
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const ID = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
// The model's own two, ranged and not, one of another module's, and one its code computes.
const structureOf = ({ wall = 2, holes = 6 } = {}) => ({ parameters: [
  { name: 'wall', value: wall, kind: 'float', min: 1, max: 5, step: 0.5, unit: 'mm', writable: true, reason: null, source: 'bracket.py' },
  { name: 'holes', value: holes, kind: 'int', min: null, max: null, step: null, unit: null, writable: true, reason: null, source: 'bracket.py' },
  { name: 'pitch', value: 30, kind: 'float', min: null, max: null, step: null, unit: 'deg', writable: false, reason: 'shared', source: 'lib/spec.py' },
  { name: 'gap', value: 0.5, kind: 'float', min: 0, max: 1, step: null, unit: null, writable: false, reason: 'expression', source: 'bracket.py' },
] });
const modelDocument = (structure: object) => ({ source: { kind: 'model', doc: ID }, structure });
const resource = { kind: 'cad-model', path: ID } as const;
const face = { resource, target: { kind: 'cad-selector', selectors: ['base/f:base.extrude1.2'] } } as const;

function Tab({ client, document, copied = null }: { client: any, document: any, copied?: string[] | null }) {
  const parameters = useXbfParameters({ client, document });
  const host = React.useMemo(() => testHost({ clipboard: { writeText: async (text: string | Promise<string>) => { copied?.push(await text); },
    readText: async () => '', writeImage: async () => {} } }), [copied]);
  return <ViewerHostContext.Provider value={host}>
    <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<XbfParametersSection parameters={parameters} />} tab="parameters" onTabChange={() => {}} width={240} maxWidth={480}
      onWidthChange={() => {}} focusSearch={0} />
    {copied ? <div data-slot="cad-file-view"><QuickEdit resource={resource} references={[face]} notes={parameters.notes} /></div> : null}
  </ViewerHostContext.Provider>;
}

const tab = () => document.querySelector<HTMLElement>('[data-flat-panel-section="parameters"]')!;
const rows = () => [...tab().querySelectorAll<HTMLElement>('[data-parameter]')].map(row => [row.getAttribute('data-parameter'),
  row.getAttribute('data-parameter-control'), row.querySelector<HTMLInputElement>('input')?.value ?? row.querySelector('[data-parameter-value]')?.textContent,
  row.querySelector('[data-parameter-reason]')?.textContent ?? null]);
const valueField = (name: string) => within(tab()).getByLabelText(`${name} value`) as HTMLInputElement;
const save = () => within(tab()).getByRole('button', { name: /^(Save|Saving…)$/ }) as HTMLButtonElement;
const reset = () => within(tab()).getByRole('button', { name: 'Reset' }) as HTMLButtonElement;
const status = () => tab().querySelector('[data-parameters-status]')!.textContent;
async function type(user: ReturnType<typeof userEvent.setup>, name: string, text: string) {
  await user.clear(valueField(name));
  await user.type(valueField(name), `${text}{Enter}`);
}

it('is a slider over a declared range, a number field without one, and a value with one line of why where it cannot be written', () => {
  render(<Tab client={{ setModelParameters: vi.fn() }} document={modelDocument(structureOf())} />);
  expect(document.querySelector<HTMLElement>('[role=tablist]')!.hidden).toBe(true); // one tab is no tabs
  expect(rows()).toEqual([
    ['wall', 'slider', '2.0 mm', null],
    ['holes', 'number', '6', null],
    ['pitch', 'none', '30°', 'Declared in lib/spec.py: change it there.'],
    ['gap', 'none', '0.50', 'Set by an expression in the code, not a number.'],
  ]);
  // The slider spans the declared range, by the declared step; nothing is drafted, so nothing is to save.
  const thumb = within(tab()).getByRole('slider', { name: 'wall' });
  expect([thumb.getAttribute('aria-valuemin'), thumb.getAttribute('aria-valuemax'), thumb.getAttribute('aria-valuenow')]).toEqual(['1', '5', '2']);
  expect([save().disabled, reset().disabled, status()]).toEqual([true, true, '']);
});

it('a file document, a model no worker holds, and a host that cannot save show every value read-only, said once', () => {
  const read = () => [rows().map(row => row[1]), tab().querySelector('[data-parameters-actions]'),
    [...tab().querySelectorAll('[data-parameter-reason]')].map(line => line.textContent)];
  const fileStructure = { parameters: structureOf().parameters.map(parameter => ({ ...parameter, writable: false, reason: 'file', source: null })) };
  const { rerender } = render(<Tab client={{ setModelParameters: vi.fn() }} document={{ source: { kind: 'xbf', doc: ID }, structure: fileStructure }} />);
  expect(read()).toEqual([['none', 'none', 'none', 'none'], null, ['Recorded in the file: read-only.']]);
  const unheld = { parameters: structureOf().parameters.map(parameter => ({ ...parameter, writable: false, reason: 'no_worker' })) };
  rerender(<Tab client={{ setModelParameters: vi.fn() }} document={modelDocument(unheld)} />);
  expect(read()).toEqual([['none', 'none', 'none', 'none'], null, ['Run the model’s script again to change these here.']]);
  // A host whose client has no way to save (the method left out): the model's own values, with no Save.
  rerender(<Tab client={{}} document={modelDocument(structureOf())} />);
  expect(read()[0]).toEqual(['none', 'none', 'none', 'none']);
  expect(read()[1]).toBeNull();
  expect(read()[2]).toEqual(['This view can’t save parameters.', 'Declared in lib/spec.py: change it there.', 'Set by an expression in the code, not a number.']);
});

it('edits are drafts until Save, which sends only the changed values in one request, busy meanwhile; Reset drops them', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  let answer!: (value: unknown) => void;
  const setModelParameters = vi.fn(() => new Promise(resolve => { answer = resolve; }));
  render(<Tab client={{ setModelParameters }} document={modelDocument(structureOf())} />);
  // A slider moved is a draft: nothing is sent while it moves.
  fireEvent.keyDown(within(tab()).getByRole('slider', { name: 'wall' }), { key: 'ArrowRight' });
  expect([valueField('wall').value, status(), setModelParameters.mock.calls.length]).toEqual(['2.5 mm', '1 unsaved', 0]);
  await user.click(reset());
  expect([valueField('wall').value, status(), save().disabled]).toEqual(['2.0 mm', '', true]);
  // A whole number for an integer parameter; a value typed back to the document's is no draft.
  await type(user, 'holes', '7.6');
  await type(user, 'wall', '3');
  await type(user, 'wall', '2');
  await type(user, 'wall', '3.5');
  expect([valueField('holes').value, valueField('wall').value, status()]).toEqual(['8', '3.5 mm', '2 unsaved']);
  await user.click(save());
  expect(setModelParameters.mock.calls).toEqual([[ID, { holes: 8, wall: 3.5 }]]);
  // While it is out: every control and both buttons off, Save says so.
  expect([save().textContent, save().disabled, save().getAttribute('aria-busy'), reset().disabled, valueField('holes').disabled, valueField('wall').disabled,
    within(tab()).getByRole('slider', { name: 'wall' }).hasAttribute('data-disabled')]).toEqual(['Saving…', true, 'true', true, true, true, true]);
  await act(async () => answer({ id: ID, written: [], rebuilt: [] }));
  expect(save().textContent).toBe('Save');
});

it('a refusal keeps the drafts and says what its code means; a code it does not know, the engine\'s own words', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const refusal = (code: string, message: string, hint = '') => Object.assign(new Error(message), { code, hint });
  const setModelParameters = vi.fn()
    .mockRejectedValueOnce(refusal('script_changed', 'bracket.py changed since it last ran', 'run it first'))
    .mockRejectedValueOnce(refusal('out_of_range', 'wall takes 1 to 5, not 9'))
    .mockRejectedValueOnce(refusal('locked', 'the script is locked by another save', 'try again'));
  render(<Tab client={{ setModelParameters }} document={modelDocument(structureOf())} />);
  await type(user, 'holes', '9');
  const said = async () => {
    await user.click(save());
    await waitFor(() => expect(within(tab()).getByRole('alert')).toBeTruthy());
    const alert = within(tab()).getByRole('alert');
    return [alert.getAttribute('data-parameters-error'), [...alert.querySelectorAll('p')].map(line => line.textContent), valueField('holes').value, status()];
  };
  expect(await said()).toEqual(['script_changed', ['The script changed since it last ran. Run it again, then save.'], '9', '1 unsaved']);
  // A refusal that names what is wrong keeps the engine's sentence under the tab's.
  expect(await said()).toEqual(['out_of_range', ['A value is outside its parameter’s range.', 'wall takes 1 to 5, not 9'], '9', '1 unsaved']);
  expect(await said()).toEqual(['unknown', ['the script is locked by another save', 'try again'], '9', '1 unsaved']);
  expect(setModelParameters.mock.calls.map(call => call[1])).toEqual([{ holes: 9 }, { holes: 9 }, { holes: 9 }]);
  // An edit clears what was said.
  await type(user, 'holes', '10');
  expect(within(tab()).queryByRole('alert')).toBeNull();
});

it('a save answered changes nothing on screen until the rebuilt document holds the values, and then the drafts are gone', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const setModelParameters = vi.fn(async () => ({ id: ID, rebuilt: [ID],
    written: [{ name: 'wall', from: 2, to: 3, file: '/home/someone/parts/bracket.py', line: 7 }, { name: 'holes', from: 6, to: 8, file: '/home/someone/parts/bracket.py', line: 8 }] }));
  const client = { setModelParameters };
  const { rerender } = render(<Tab client={client} document={modelDocument(structureOf())} />);
  await type(user, 'wall', '3');
  await type(user, 'holes', '8');
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Saved'));
  // Answered: the values stay on their controls, awaited, and are not sent again.
  expect([valueField('wall').value, valueField('holes').value, save().disabled]).toEqual(['3.0 mm', '8', true]);
  // A new version that holds one of them: that draft goes, the other is still awaited.
  rerender(<Tab client={client} document={modelDocument(structureOf({ wall: 3 }))} />);
  expect([valueField('wall').value, valueField('holes').value, status()]).toEqual(['3.0 mm', '8', '1 unsaved']);
  rerender(<Tab client={client} document={modelDocument(structureOf({ wall: 3, holes: 8 }))} />);
  expect([valueField('wall').value, valueField('holes').value, status(), save().disabled]).toEqual(['3.0 mm', '8', 'Saved', true]);
  expect(setModelParameters).toHaveBeenCalledTimes(1);
});

it('the next Quick Edit carries what was saved, once, by the script\'s name; a later one does not', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const copied: string[] = [];
  const setModelParameters = vi.fn(async (_id: string, values: Record<string, number>) => ({ id: ID, rebuilt: [ID],
    written: Object.entries(values).map(([name, to]) => ({ name, from: name === 'wall' ? 2 : 6, to, file: '/home/someone/parts/bracket.py', line: 7 })) }));
  render(<Tab client={{ setModelParameters }} document={modelDocument(structureOf())} copied={copied} />);
  await type(user, 'wall', '2.5');
  await user.click(save());
  await waitFor(() => expect(status()).toBe('Saved'));
  const copy = async (count: number) => {
    fireEvent.click(document.querySelector<HTMLElement>('[data-quick-edit-action="copy"]')!);
    await waitFor(() => expect(copied).toHaveLength(count));
  };
  await copy(1);
  await copy(2);
  const block = 'Saved from the viewer since your last edit: wall 2 -> 2.5 (bracket.py)';
  // After what the person wrote (nothing here) and before the file: said once, then not again.
  expect(copied[0]).toBe(`${block}\n\n${copied[1]}`);
  expect(copied[1]).not.toContain('Saved from the viewer');
  expect(copied[1]).toContain(ID);
  expect(copied.join('\n')).not.toContain('/home/someone');
});

it('the panel is there for a single part with parameters, as it is for an assembly or a mechanism', () => {
  expect(xbfPanelSections({ assembly: false, posable: false, parameters: 2 })).toEqual(['parameters']);
  expect(xbfPanelSections({ assembly: false, posable: false, parameters: 0 })).toEqual([]);
  expect(xbfPanelSections({ assembly: true, posable: true, parameters: 1 })).toEqual(['model', 'position', 'parameters']);
  expect(xbfPanelSections({ assembly: true, posable: false, parameters: 0 })).toEqual(['model']);
});
