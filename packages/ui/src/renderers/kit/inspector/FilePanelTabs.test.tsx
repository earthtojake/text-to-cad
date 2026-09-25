import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it } from 'vitest';
import FilePanelTabs from '../../../../dist/renderers/kit/inspector/FilePanelTabs.js';
afterEach(cleanup);
// The selected tab is the owner's: this stands in for the shell that holds it.
function Owned({ sections, initial = '' }: { sections: object[]; initial?: string }) {
  const [selected, setSelected] = React.useState(initial);
  return <><button onClick={() => setSelected('position')}>Reveal Position</button>
    <FilePanelTabs sections={sections} active selected={selected} onSelectedChange={setSelected} /></>;
}
for (const title of ['Features', 'Links']) it(`${title} and Position have separate persistent tabs and tool reveal selects Position`, async () => {
  const user = userEvent.setup();
  const sections = [{ id: title.toLowerCase(), title, role: 'model', content: <input aria-label="Filter" /> },
    { id: 'position', title: 'Position', role: 'position', content: <input aria-label="Joint value" defaultValue="0" /> }];
  render(<Owned sections={sections} />);
  expect(screen.getByRole('tab', { name: title }).getAttribute('aria-selected')).toBe('true');
  expect(screen.queryByRole('button', { name: /Collapse/ })).toBeNull();
  await user.type(screen.getByLabelText('Filter'), 'arm');
  await user.click(screen.getByRole('tab', { name: 'Position' }));
  expect(screen.queryByRole('textbox', { name: 'Filter' })).toBeNull();
  expect(screen.getByRole('textbox', { name: 'Joint value' })).toBeTruthy();
  await user.click(screen.getByRole('tab', { name: title }));
  expect((screen.getByRole('textbox', { name: 'Filter' }) as HTMLInputElement).value).toBe('arm');
  await user.click(screen.getByRole('button', { name: 'Reveal Position' }));
  expect(screen.getByRole('tab', { name: 'Position' }).getAttribute('aria-selected')).toBe('true');
});
it('the selected tab is its owner\'s, so a remounted panel opens on the tab that was chosen', async () => {
  const user = userEvent.setup();
  const sections = [{ id: 'links', title: 'Links', role: 'model', content: 'Tree' }, { id: 'position', title: 'Position', role: 'position', content: 'Joints' }];
  let chosen = '';
  const { unmount } = render(<FilePanelTabs sections={sections} active selected="" onSelectedChange={(value: string) => { chosen = value; }} />);
  await user.click(screen.getByRole('tab', { name: 'Position' }));
  expect(chosen).toBe('position');
  unmount();
  render(<FilePanelTabs sections={sections} active selected={chosen} onSelectedChange={() => {}} />);
  expect(screen.getByRole('tab', { name: 'Position' }).getAttribute('aria-selected')).toBe('true');
});
it('does not add tabs without position controls', () => {
  render(<FilePanelTabs sections={[{id:'features',title:'Features',role:'model',content:'Tree'}]} active />);
  expect(screen.queryByRole('tablist')).toBeNull();
});
it('the tabs come from what each section says it is, never from the id a renderer gave it', async () => {
  const user = userEvent.setup();
  // Any ids: the kit knows no renderer's section names.
  const sections = [{ id: 'tree', title: 'Tree', role: 'model', content: 'Rows' }, { id: 'notes', title: 'Notes', content: 'Text' },
    { id: 'joints', title: 'Joints', role: 'position', content: 'Sliders' }];
  let chosen = '';
  const { rerender } = render(<FilePanelTabs sections={sections} active selected="" onSelectedChange={(value: string) => { chosen = value; }} />);
  expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['Tree', 'Joints']);
  expect(screen.getByText('Text')).toBeTruthy();
  await user.click(screen.getByRole('tab', { name: 'Joints' }));
  expect(chosen).toBe('joints');
  rerender(<FilePanelTabs sections={sections} active selected="joints" onSelectedChange={() => {}} />);
  expect(screen.getByRole('tab', { name: 'Joints' }).getAttribute('aria-selected')).toBe('true');
  cleanup();
  // Ids that USED to mean something to the kit mean nothing without a role.
  render(<FilePanelTabs sections={[{ id: 'features', title: 'Features', content: 'Tree' }, { id: 'position', title: 'Position', content: 'Joints' }]} active />);
  expect(screen.queryByRole('tablist')).toBeNull();
  cleanup();
  render(<FilePanelTabs sections={[{ id: 'tree', title: 'Tree', role: 'model', content: 'Rows' }, { id: 'position', title: 'Position', content: 'Joints' }]} active />);
  expect(screen.queryByRole('tablist')).toBeNull();
});
