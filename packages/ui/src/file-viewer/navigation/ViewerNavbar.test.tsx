import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewerNavbar } from '../../../dist/file-viewer/navigation/ViewerNavbar.js';
import { ControlUsageProvider } from '../../../dist/usage/controls.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FILE = '/home/me/models/a.step';
const MODEL = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
const name = () => document.querySelector('[data-file-name]')!;
const fileMenu = (extra = {}) => ({ platform: 'darwin' as const, capabilities: new Set(['copy-path'] as const), onAction: vi.fn(), ...extra });

// The ⋯ menu, opened as a press opens it.
async function openMenu() {
  await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  return screen.findByRole('menu');
}

it('shows the name alone, with no glyph and no menu of its own: moving between documents is the Project list\'s', () => {
  const { rerender } = render(<ViewerNavbar file={FILE} />);
  expect([name().tagName, name().textContent, name().querySelector('svg')]).toEqual(['SPAN', 'a.step', null]);
  // A model's document is named by its name, never by its id; until the name is known, its place is empty.
  rerender(<ViewerNavbar file={MODEL} name="bracket" />);
  expect(name().textContent).toBe('bracket');
  rerender(<ViewerNavbar file={MODEL} />);
  expect(name().textContent).toBe('');
  expect(document.querySelector('[data-navbar-project]')).toBeNull();
});

it("puts the project's name and a slash before the document's, muted, the project's giving way first, and a press on it goes to the home at it, counted", () => {
  const reports: { control: string; count: number }[][] = [];
  const onOpen = vi.fn();
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ViewerNavbar file={FILE} project={{ name: 'heart-tag', onOpen }} /></ControlUsageProvider>);
  const crumb = document.querySelector('[data-navbar-project]')!;
  const button = within(crumb as HTMLElement).getByRole('button', { name: 'Show heart-tag on Home' });
  expect([button.textContent, crumb.textContent, button.className.includes('text-muted-foreground')]).toEqual(['heart-tag', 'heart-tag/', true]);
  // Before the name, in the row's order; the name keeps its width, the project's name shrinks.
  expect(crumb.compareDocumentPosition(name()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect([crumb.className.includes('min-w-0'), name().className.includes('shrink-0'), name().className.includes('max-w-[65%]')]).toEqual([true, true, true]);
  fireEvent.click(button);
  expect(onOpen).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(reports.flat()).toEqual([{ control: 'project_crumb', count: 1, seconds: 0 }]);
});

it("ends a document's ⋯ in Import its folder as a project where the host can, after the rest, disabled while its source is gone, counted", async () => {
  const reports: { control: string; count: number }[][] = [];
  const onImportFolder = vi.fn();
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ViewerNavbar file={FILE} fileMenu={fileMenu({ onImportFolder })} /></ControlUsageProvider>);
  const menu = await openMenu();
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Import its folder as a project…']);
  expect(within(menu).getAllByRole('separator')).toHaveLength(1);
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: 'Import its folder as a project…' })); });
  expect(onImportFolder).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(reports.flat()).toEqual([{ control: 'file_import_folder', count: 1, seconds: 0 }]);
  // A ⋯ with it alone, and with no separator; a source gone draws it disabled.
  render(<ViewerNavbar file={FILE} fileMenu={fileMenu({ capabilities: new Set(), onImportFolder, sourceMissing: true })} />);
  const alone = await openMenu();
  expect(within(alone).queryByRole('separator')).toBeNull();
  expect(within(alone).getByRole('menuitem', { name: 'Import its folder as a project…' }).getAttribute('data-disabled')).toBe('');
});
