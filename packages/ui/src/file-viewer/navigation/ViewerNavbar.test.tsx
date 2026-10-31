import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewerNavbar } from '../../../dist/file-viewer/navigation/ViewerNavbar.js';
import { MODEL_ROWS, modelRows } from '../../../dist/file-viewer/navigation/ModelList.js';
import { ControlUsageProvider } from '../../../dist/usage/controls.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FILE = '/home/me/models/a.step';
const MODEL = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
const chevron = () => document.querySelector('[data-file-name] svg.lucide-chevron-down');
const glyph = () => document.querySelector('[data-file-name] [data-glyph]')?.getAttribute('data-glyph');
const now = Date.now() / 1000;
const ROWS = [
  { path: FILE, name: 'a.step', kind: 'file', opened: now - 2 * 3600, updated: now - 30 * 86400, missing: false },
  { path: MODEL, name: 'bracket', kind: 'model', opened: null, updated: now - 5 * 60, missing: false },
  { path: '/home/me/models/gone.stl', name: 'gone.stl', kind: 'file', opened: now - 3 * 86400, updated: null, missing: true },
];
const explorer = (list = async () => []) => ({ source: { list: vi.fn(list), search: vi.fn(async () => ({ paths: [], truncated: false })) }, onOpen: vi.fn() });
const recent = (rows = ROWS) => ({ list: vi.fn(async () => rows), onOpen: vi.fn() });

it('shows the name alone, with no glyph, and a chevron where it opens the name menu; a plain name has none', () => {
  const { rerender } = render(<ViewerNavbar file={FILE} explorer={explorer()} />);
  const trigger = document.querySelector('[data-file-name]')!;
  expect(trigger.tagName).toBe('BUTTON');
  expect(trigger.textContent).toBe('a.step');
  expect(glyph()).toBeUndefined();
  expect([...trigger.querySelectorAll('svg')]).toEqual([chevron()]);
  expect(chevron()?.getAttribute('aria-hidden')).toBe('true');
  expect(chevron()?.getAttribute('class')).toContain('shrink-0');
  rerender(<ViewerNavbar file={FILE} explorer={null} />);
  expect(document.querySelector('[data-file-name]')!.tagName).toBe('SPAN');
  expect(chevron()).toBeNull();
  rerender(<ViewerNavbar file={MODEL} name="bracket" kind="model" explorer={null} />);
  expect([document.querySelector('[data-file-name]')!.textContent, document.querySelector('[data-file-name] svg')]).toEqual(['bracket', null]);
});

it('opens Models and Files as two tabs sized to their labels, on Files over a file and on Models over a model', async () => {
  const user = userEvent.setup();
  render(<ViewerNavbar file={FILE} explorer={explorer()} recent={recent()} />);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!);
  const menu = document.querySelector<HTMLElement>('[data-file-explorer]')!;
  const tabs = within(menu).getAllByRole('tab');
  expect(tabs.map(tab => [tab.textContent, tab.getAttribute('aria-selected')])).toEqual([['Models', 'false'], ['Files', 'true']]);
  // The tabs as wide as their labels, not the menu; the menu the explorer's natural width.
  expect(within(menu).getByRole('tablist').className).toMatch(/\bw-fit\b/);
  expect(menu.className).toContain('w-[17.5rem]');
  // Files is the explorer itself: its breadcrumb and filter.
  expect(document.querySelector('[data-file-explorer] [data-folder-explorer]')).not.toBeNull();
  expect(screen.getByRole('textbox', { name: 'Filter files' })).toBeTruthy();
  cleanup();
  render(<ViewerNavbar file={MODEL} name="bracket" kind="model" explorer={{ ...explorer(), folder: '/home/me/models' }} recent={recent()} />);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!);
  expect(screen.getByRole('tab', { name: 'Models' }).getAttribute('aria-selected')).toBe('true');
  expect(await screen.findByText('bracket', { selector: '[data-model-row] *' })).toBeTruthy();
});

it('lists models alone on Models, by last activity, each row its glyph, name and age, the one on screen marked, and a row opens its model', async () => {
  const user = userEvent.setup();
  const other = { path: '7a2d3b5f-2c3d-6e4f-9a5b-0123456789ab', name: 'arm', kind: 'model', opened: now - 3 * 3600, updated: null, missing: true };
  const menu = recent([...ROWS, other]);
  render(<ViewerNavbar file={MODEL} name="bracket" kind="model" explorer={explorer()} recent={menu} />);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!);
  await screen.findByText('arm');
  const rows = [...document.querySelectorAll<HTMLElement>('[data-model-row]')];
  // No file: a.step and gone.stl are Files' and the Home's.
  expect(rows.map(row => [row.querySelector('[data-glyph]')?.getAttribute('data-glyph'), row.textContent])).toEqual([
    ['model', 'bracket5m ago'], ['model', 'arm3h ago']]);
  expect(rows.map(row => row.getAttribute('aria-current'))).toEqual(['true', null]);
  expect((rows[1] as HTMLButtonElement).disabled).toBe(true);
  // No footer, no extra rows: the Home is one click away.
  expect(document.querySelector('[data-model-list] [data-model-row]:last-of-type')).toBe(rows[1]);
  // Down from the menu walks into the rows.
  fireEvent.keyDown(document.querySelector('[data-file-explorer]')!, { key: 'ArrowDown' });
  expect(document.activeElement).toBe(rows[0]);
  await user.click(rows[0]);
  expect(menu.onOpen).toHaveBeenCalledWith(MODEL);
  expect(document.querySelector('[data-file-explorer]')).toBeNull();
});

it('filters Models under "Filter models...", which has the keyboard on opening, Down taking it into the rows and Up back', async () => {
  const user = userEvent.setup();
  const rows = [...ROWS, { path: '7a2d3b5f-2c3d-6e4f-9a5b-0123456789ab', name: 'arm plate', kind: 'model', opened: now - 3600, updated: null, missing: false }];
  const reports: { control: string; count: number }[][] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ViewerNavbar file={MODEL} name="bracket" kind="model" explorer={explorer()} recent={recent(rows)} /></ControlUsageProvider>);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!);
  await screen.findByText('arm plate');
  const filter = screen.getByRole('textbox', { name: 'Filter models' });
  expect([filter.getAttribute('placeholder'), document.activeElement]).toEqual(['Filter models...', filter]);
  const names = () => [...document.querySelectorAll('[data-model-row]')].map(row => row.querySelector('[data-model-age]')!.previousElementSibling!.textContent);
  expect(names()).toEqual(['bracket', 'arm plate']);
  await user.keyboard('ARM');
  expect(names()).toEqual(['arm plate']);
  await user.keyboard('{ArrowDown}');
  expect(document.activeElement).toBe(document.querySelector('[data-model-row]'));
  await user.keyboard('{ArrowUp}');
  expect(document.activeElement).toBe(filter);
  await user.clear(filter);
  await user.keyboard('gone');
  // a.step and gone.stl are files: nothing of Models matches.
  expect([names(), screen.getByText('No models match').tagName]).toEqual([[], 'P']);
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, count }) => [control, count]));
  expect(said).toEqual({ models: 1, models_filter: 2 });
});

it('keeps Models to the eight latest, and a menu with one of the two has no tabs', async () => {
  const many = Array.from({ length: 12 }, (_, index) => ({ path: `/m/${index}`, name: `m${index}`, kind: 'model', opened: index, updated: null }));
  expect(modelRows([...many, { path: '/m/a.step', name: 'a.step', kind: 'file', opened: 99, updated: null }]).map(row => row.name))
    .toEqual(['m11', 'm10', 'm9', 'm8', 'm7', 'm6', 'm5', 'm4']);
  expect(MODEL_ROWS).toBe(8);
  const user = userEvent.setup();
  render(<ViewerNavbar file={MODEL} name="bracket" kind="model" recent={recent()} />);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!);
  await screen.findByText('bracket', { selector: '[data-model-row] *' });
  expect(screen.queryByRole('tab')).toBeNull();
});

it('starts a model\'s Files in the folder it is handed (where the explorer was last, else home)', async () => {
  const user = userEvent.setup();
  const files = explorer(async () => [{ path: '/home/me/models/b.step', name: 'b.step', kind: 'file' }]);
  render(<ViewerNavbar file={MODEL} name="bracket" kind="model" explorer={{ ...files, folder: '/home/me/models' }} recent={recent()} />);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!);
  await act(async () => { await user.click(screen.getByRole('tab', { name: 'Files' })); });
  await screen.findByText('b.step');
  expect(files.source.list).toHaveBeenCalledWith('/home/me/models', expect.anything());
});

it("counts the name menu's tabs as a person sees them, Models and Files (the explorer), and a row opened from Models", async () => {
  const user = userEvent.setup();
  const reports: { control: string; count: number }[][] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ViewerNavbar file={MODEL} name="bracket" kind="model" explorer={explorer()} recent={recent()} /></ControlUsageProvider>);
  await user.click(document.querySelector<HTMLElement>('[data-file-name]')!); // opens on Models
  await user.click(screen.getByRole('tab', { name: 'Files' }));
  await user.click(screen.getByRole('tab', { name: 'Models' }));
  await user.click((await screen.findByText('bracket', { selector: '[data-model-row] *' })).closest('button')!);
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, count }) => [control, count]));
  expect(said).toEqual({ models: 2, explorer: 1, models_open: 1 });
});
