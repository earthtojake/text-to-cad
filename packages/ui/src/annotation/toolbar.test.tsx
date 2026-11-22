import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useAnnotationSession } from './session.js';
import { ANNOTATION_COLORS, AnnotationToolbar, annotationColors, drawStripTool } from './toolbar.jsx';
import FloatingToolBar from '../../dist/renderers/kit/tools/FloatingToolBar.js';
import { useI18n } from '@cad/ui/i18n';
import { ViewerHostContext } from '../host/context.js';
import { testHost } from '../host/testing/host.js';

afterEach(cleanup);

let session: ReturnType<typeof useAnnotationSession>;
const history = { canUndo: false, canRedo: false, undo() {}, redo() {} };
// As a view draws them: the strip's one Draw tool over both drawing modes, and the row under it.
function Panel({ family = 'pencil', colorScheme = 'light', placements = true }: { family?: 'pencil' | 'shapes', colorScheme?: 'light' | 'dark', placements?: boolean }) {
  const { t } = useI18n();
  const [mode, setMode] = React.useState<string>(family);
  session = useAnnotationSession(mode as 'pencil' | 'shapes');
  const draw = drawStripTool({ toolMode: mode, annotation: session, takeFamily: setMode, t });
  return <>
    <FloatingToolBar tools={[draw]} />
    <AnnotationToolbar annotation={session} history={history} colorScheme={colorScheme} placements={placements} takeFamily={setMode} />
  </>;
}
const open = async (name: string) => {
  fireEvent.pointerDown(screen.getByRole('button', { name }), { button: 0, ctrlKey: false });
  return screen.findByRole('menu', { name });
};
// A tool chosen: its button in the row.
const choose = async (name: string) => fireEvent.click(within(screen.getByRole('toolbar', { name: 'Annotation controls' })).getByRole('button', { name }));
const label = (element: Element) => element.getAttribute('role') === 'separator' ? '|' : element.getAttribute('aria-label');

it("the drawing controls are one surface of two rows of seven: the tools that put ink down, then the Eraser, Colour, Stroke width, Placement, Undo, Redo and Clear, no rule", () => {
  render(<Panel />);
  const row = screen.getByRole('toolbar', { name: 'Annotation controls' });
  const rows = [...row.children];
  expect(rows.map(element => element.getAttribute('data-annotation-row'))).toEqual(['create', 'style']);
  // Stacked, left-aligned: the tools over what is drawn next.
  expect(row.className.split(/\s+/)).toEqual(expect.arrayContaining(['flex-col', 'items-start']));
  const names = (element: Element) => [...element.querySelectorAll('button')].map(button => button.getAttribute('aria-label'));
  expect(names(rows[0])).toEqual(['Pen', 'Highlighter', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text']);
  expect(names(rows[1])).toEqual(['Eraser', 'Colour', 'Stroke width', 'Placement', 'Undo', 'Redo', 'Clear annotations']);
  // No line style: every stroke is solid.
  expect(screen.queryByRole('button', { name: 'Line style' })).toBeNull();
});

it("Draw is one plain strip tool, its button the tool it draws with; the row's tools, each with its key, the one in hand pressed, choose it and take up its family", async () => {
  render(<Panel family="pencil" />);
  const button = () => screen.getByRole('button', { name: 'Draw' });
  expect([button().getAttribute('aria-pressed'), button().getAttribute('aria-keyshortcuts')]).toEqual(['true', 'P']);
  // No chevron, no menu.
  expect(screen.queryByRole('button', { name: 'Drawing tools' })).toBeNull();
  const tools = () => within(screen.getByRole('group', { name: 'Drawing tools' })).getAllByRole('button')
    .map(item => [item.getAttribute('aria-label'), item.getAttribute('aria-pressed'), item.getAttribute('aria-keyshortcuts')]);
  // In the order a person reaches for them: freehand, the shapes, text; then, on the second row, what changes ink already down.
  expect(tools()).toEqual([['Pen', 'true', 'P'], ['Highlighter', 'false', 'Shift+P'], ['Line', 'false', 'L'], ['Arrow', 'false', 'Shift+L'],
    ['Rectangle', 'false', 'R'], ['Ellipse', 'false', 'O'], ['Text', 'false', 'T']]);
  expect(within(screen.getByRole('group', { name: 'Editing tools' })).getAllByRole('button')
    .map(item => [item.getAttribute('aria-label'), item.getAttribute('aria-pressed'), item.getAttribute('aria-keyshortcuts')]))
    .toEqual([['Eraser', 'false', 'E']]);
  await choose('Highlighter');
  expect([session.tool, session.pencil, session.shape]).toEqual(['highlighter', 'highlighter', 'rectangle']);
  expect(button().getAttribute('aria-keyshortcuts')).toBe('Shift+P');
  // A shape chosen takes Shapes' mode up, Draw still the tool, the shape in hand.
  await choose('Ellipse');
  expect([session.tool, session.shape, session.pencil, session.lastFamily]).toEqual(['ellipse', 'ellipse', 'highlighter', 'shapes']);
  expect([button().getAttribute('aria-pressed'), button().getAttribute('aria-keyshortcuts')]).toEqual(['true', 'O']);
  expect(tools().filter(([, pressed]) => pressed === 'true').map(([name]) => name)).toEqual(['Ellipse']);
});

it("each drawing kind keeps its own style on the row: the pen's red, the highlighter's yellow, Shapes' red; changing one leaves the others", async () => {
  render(<Panel />);
  const swatch = () => screen.getByRole('button', { name: 'Colour' }).querySelector('span')!.style.backgroundColor;
  const checked = async () => [...(await open('Colour')).querySelectorAll('[data-checked]')].map(item => item.getAttribute('aria-label'));
  expect(await checked()).toEqual(['Neon red']);
  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
  await choose('Highlighter');
  expect(await checked()).toEqual(['Neon yellow']);
  fireEvent.click(within(screen.getByRole('menu', { name: 'Colour' })).getByRole('menuitem', { name: 'Neon cyan' }));
  expect(swatch()).toBe('rgb(0, 229, 255)');
  await choose('Pen');
  expect(swatch()).toBe('rgb(255, 45, 85)');
  expect(session.styles.highlighter.color).toBe('#00e5ff');
});

it('the Eraser greys out Color, Stroke width and Placement, still on the row; Clear annotations stays as it was', async () => {
  render(<Panel />);
  const disabled = () => ['Colour', 'Stroke width', 'Placement', 'Clear annotations'].map(name => screen.getByRole('button', { name }).hasAttribute('disabled'));
  expect(disabled()).toEqual([false, false, false, true]);
  await choose('Eraser');
  expect(disabled()).toEqual([true, true, true, true]);
  act(() => session.add([{ id: 'a', kind: 'stroke', points: new Float32Array(6), color: '#ff2d55', width: 2 } as any]));
  expect(disabled()).toEqual([true, true, true, false]);
  await choose('Pen');
  expect(disabled()).toEqual([false, false, false, false]);
});

const stroke = (id: string) => ({ id, kind: 'stroke', points: new Float32Array(6), color: '#ff2d55', width: 2 } as any);
const off = (name: string) => screen.getByRole('button', { name }).hasAttribute('disabled');

it('Undo and Redo, left of Clear, walk the history: off with none, an undo takes the stroke away and a redo puts it back', () => {
  render(<Panel />);
  expect([off('Undo'), off('Redo')]).toEqual([true, true]);
  act(() => session.add([stroke('a')]));
  expect([off('Undo'), off('Redo')]).toEqual([false, true]);
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
  expect([session.items.length, off('Undo'), off('Redo')]).toEqual([0, true, false]);
  fireEvent.click(screen.getByRole('button', { name: 'Redo' }));
  expect([session.items.map(item => item.id), off('Undo'), off('Redo')]).toEqual([['a'], false, true]);
  // Still there under the Eraser, which greys the style alone.
  fireEvent.click(within(screen.getByRole('toolbar', { name: 'Annotation controls' })).getByRole('button', { name: 'Eraser' }));
  expect([off('Undo'), off('Redo')]).toEqual([false, true]);
});

it("Undo's and Redo's keys are the viewer's, in their tooltips as the host's platform spells them", () => {
  render(<Panel />);
  const keys = () => ['Undo', 'Redo'].map(name => screen.getByRole('button', { name }).getAttribute('aria-keyshortcuts'));
  expect(keys()).toEqual(['Ctrl+Z', 'Ctrl+Y']);
  cleanup();
  render(<ViewerHostContext.Provider value={testHost({ environment: { platform: 'darwin' } } as any)}><Panel /></ViewerHostContext.Provider>);
  expect(keys()).toEqual(['⌘Z', 'Shift+⌘Z']);
});

it('a flat view (placements off) has no Placement', () => {
  render(<Panel placements={false} />);
  expect(screen.queryByRole('button', { name: 'Placement' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Stroke width' })).toBeTruthy();
});

it('Placement is a menu as the strip\'s are, a row per choice, the current one checked', async () => {
  render(<Panel />);
  expect(session.style.placement).toBe('surface');
  const menu = await open('Placement');
  expect(within(menu).getAllByRole('menuitemradio').map(item => [item.getAttribute('aria-label'), item.getAttribute('aria-checked')]))
    .toEqual([['On surface', 'true'], ['On plane', 'false']]);
  fireEvent.click(within(menu).getByRole('menuitemradio', { name: 'On plane' }));
  expect(session.style.placement).toBe('plane');
});

it("Stroke width's button is three lines, thin to thick, whatever the weight; its menu has no heading, a row per weight, the line at that weight alone, the current one checked", async () => {
  render(<Panel />);
  const weight = (element: Element | null) => element?.querySelector('svg[data-stroke-weight]')?.getAttribute('data-stroke-weight');
  const button = () => screen.getByRole('button', { name: 'Stroke width' });
  const lines = () => [...button().querySelectorAll('svg[data-glyph="stroke-width"] path')].map(path => Number(path.getAttribute('stroke-width')));
  expect(lines()).toEqual([1, 2, 3.5]);
  const menu = await open('Stroke width');
  expect(menu.querySelector('[data-slot=dropdown-menu-label]')).toBeNull();
  const items = within(menu).getAllByRole('menuitemradio');
  expect(items.map(item => [item.getAttribute('aria-label'), item.getAttribute('data-style-option'), item.getAttribute('aria-checked'), item.textContent, weight(item)]))
    .toEqual([['Thin', '1', 'false', '', '1'], ['Medium', '2', 'true', '', '2'], ['Bold', '4', 'false', '', '4'], ['Heavy', '6', 'false', '', '6']]);
  // A straight line (one horizontal segment), drawn at the weight itself.
  expect(items.map(item => Number(item.querySelector('svg')!.getAttribute('stroke-width')))).toEqual([1, 2, 4, 6]);
  expect(items[0].querySelector('svg path')!.getAttribute('d')).toMatch(/^M[\d.]+ [\d.]+h[\d.]+$/);
  fireEvent.click(within(menu).getByRole('menuitemradio', { name: 'Heavy' }));
  expect(session.style.strokeWidth).toBe(6);
  expect(lines()).toEqual([1, 2, 3.5]);
});

it('the colours are the neons and the one neutral that reads against the viewer: white in dark mode, black in light', () => {
  const labels = (scheme: 'light' | 'dark') => annotationColors(scheme).map(option => option.label);
  const neons = ANNOTATION_COLORS.slice(0, 7).map(option => option.label);
  expect([labels('dark'), labels('light')]).toEqual([[...neons, 'White'], [...neons, 'Black']]);
});

it('Color is a dropdown: its button the colour in hand, its menu, with no heading, a grid of the scheme\'s swatches, the current one marked, then a custom colour from the system picker', async () => {
  render(<Panel colorScheme="dark" />);
  let menu = await open('Colour');
  expect(menu.querySelector('[data-slot=dropdown-menu-label]')).toBeNull();
  const neons = ANNOTATION_COLORS.slice(0, 7).map(option => option.label);
  expect(within(menu).getAllByRole('menuitem').map(item => item.getAttribute('aria-label'))).toEqual([...neons, 'White', 'Custom colour']);
  expect([...menu.querySelectorAll('[data-checked]')].map(item => item.getAttribute('aria-label'))).toEqual(['Neon red']);
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Neon green' }));
  expect(session.style.color).toBe('#39ff14');
  menu = await open('Colour');
  expect([...menu.querySelectorAll('[data-checked]')].map(item => item.getAttribute('aria-label'))).toEqual(['Neon green']);
  // The picker's colour is taken as it closes.
  const picker = document.querySelector<HTMLInputElement>('input[type=color][data-color-picker]')!;
  picker.value = '#123456';
  fireEvent.change(picker);
  expect(session.style.color).toBe('#123456');
});

it("a phone's drawing tools wrap within their row where the view has no room; the second row stays under them", () => {
  render(<Panel />);
  expect(screen.getByRole('group', { name: 'Drawing tools' }).className.split(/\s+/)).toContain('flex-wrap');
  expect(document.querySelector('[data-annotation-row="style"]')!.className.split(/\s+/)).toContain('flex-wrap');
});
