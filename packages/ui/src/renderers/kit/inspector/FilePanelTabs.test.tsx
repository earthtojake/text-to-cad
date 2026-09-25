import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it } from 'vitest';
import FilePanelTabs from '../../../../dist/renderers/kit/inspector/FilePanelTabs.js';
afterEach(cleanup);
for (const title of ['Features', 'Links']) it(`${title} and Position have separate persistent tabs and tool reveal selects Position`, async () => {
  const user = userEvent.setup();
  const sections = [{ id: title.toLowerCase(), title, content: <input aria-label="Filter" /> },
    { id: 'position', title: 'Position', content: <input aria-label="Joint value" defaultValue="0" /> }];
  const { rerender } = render(<FilePanelTabs sections={sections} active />);
  expect(screen.getByRole('tab', { name: title }).getAttribute('aria-selected')).toBe('true');
  expect(screen.queryByRole('button', { name: /Collapse/ })).toBeNull();
  await user.type(screen.getByLabelText('Filter'), 'arm');
  await user.click(screen.getByRole('tab', { name: 'Position' }));
  expect(screen.queryByRole('textbox', { name: 'Filter' })).toBeNull();
  expect(screen.getByRole('textbox', { name: 'Joint value' })).toBeTruthy();
  await user.click(screen.getByRole('tab', { name: title }));
  expect((screen.getByRole('textbox', { name: 'Filter' }) as HTMLInputElement).value).toBe('arm');
  rerender(<FilePanelTabs sections={sections} active revealRequest={{ sectionId: 'position', key: 1 }} />);
  expect(screen.getByRole('tab', { name: 'Position' }).getAttribute('aria-selected')).toBe('true');
});
it('does not add tabs without position controls', () => {
  render(<FilePanelTabs sections={[{id:'features',title:'Features',content:'Tree'}]} active />);
  expect(screen.queryByRole('tablist')).toBeNull();
});
