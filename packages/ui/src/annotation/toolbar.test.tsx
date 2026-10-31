import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useAnnotationSession } from './session.js';
import { ANNOTATION_COLORS, AnnotationToolbar, annotationColors } from './toolbar.jsx';

afterEach(cleanup);

let session: ReturnType<typeof useAnnotationSession>;
const history = { canUndo: false, canRedo: false, undo() {}, redo() {} };
function Panel({ family = 'pencil', colorScheme = 'light', placements = true }: { family?: 'pencil' | 'shapes', colorScheme?: 'light' | 'dark', placements?: boolean }) {
  session = useAnnotationSession(family);
  return <AnnotationToolbar annotation={session} history={history} colorScheme={colorScheme} placements={placements} />;
}
const open = async (name: string) => {
  fireEvent.pointerDown(screen.getByRole('button', { name }), { button: 0, ctrlKey: false });
  return screen.findByRole('menu', { name });
};
const label = (element: Element) => element.getAttribute('role') === 'separator' ? '|' : element.getAttribute('aria-label');

it("the drawing controls are ONE row of two sections: the tool's own tools, a rule, then Color, Stroke width, Placement and Clear", () => {
  render(<Panel />);
  const row = screen.getByRole('toolbar', { name: 'Annotation controls' });
  expect([...row.children].map(label)).toEqual(['Pencil tools', '|', 'Annotation style']);
  // Never a column of rows: one line, wrapping only where a phone has no room.
  expect(row.className.split(/\s+/)).toContain('flex-nowrap');
  expect(row.className.split(/\s+/)).not.toContain('flex-col');
  expect(within(screen.getByRole('group', { name: 'Annotation style' })).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Colour', 'Stroke width', 'Placement', 'Clear annotations']);
  // Undo and Redo are the keyboard's alone.
  expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
});

it("the row starts with the tools of Pencil (the pen first, pressed) or of Shapes (the line first), the chosen one pressed; choosing draws with it", () => {
  const pencil = render(<Panel family="pencil" />);
  const tools = () => within(screen.getByRole('group', { name: /tools$/ })).getAllByRole('button').map(button => [button.getAttribute('aria-label'), button.getAttribute('aria-pressed')]);
  expect(tools()).toEqual([['Pen', 'true'], ['Highlighter', 'false'], ['Eraser', 'false']]);
  fireEvent.click(screen.getByRole('button', { name: 'Highlighter' }));
  expect([session.tool, session.pencil, session.shape]).toEqual(['highlighter', 'highlighter', 'rectangle']);
  expect(tools()).toEqual([['Pen', 'false'], ['Highlighter', 'true'], ['Eraser', 'false']]);
  pencil.unmount();
  render(<Panel family="shapes" />);
  expect(screen.getByRole('group', { name: 'Shapes tools' })).toBeTruthy();
  expect(tools()).toEqual([['Rectangle', 'true'], ['Line', 'false'], ['Arrow', 'false'], ['Ellipse', 'false'], ['Text', 'false']]);
  fireEvent.click(screen.getByRole('button', { name: 'Ellipse' }));
  expect([session.tool, session.shape, session.pencil]).toEqual(['ellipse', 'ellipse', 'freedraw']);
});

it("each drawing kind keeps its own style on the row: the pen's red, the highlighter's yellow, Shapes' red; changing one leaves the others", async () => {
  render(<Panel />);
  const swatch = () => screen.getByRole('button', { name: 'Colour' }).querySelector('span')!.style.backgroundColor;
  const checked = async () => [...(await open('Colour')).querySelectorAll('[data-checked]')].map(item => item.getAttribute('aria-label'));
  expect(await checked()).toEqual(['Neon red']);
  fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
  fireEvent.click(screen.getByRole('button', { name: 'Highlighter' }));
  expect(await checked()).toEqual(['Neon yellow']);
  fireEvent.click(within(screen.getByRole('menu', { name: 'Colour' })).getByRole('menuitem', { name: 'Neon cyan' }));
  expect(swatch()).toBe('rgb(0, 229, 255)');
  fireEvent.click(screen.getByRole('button', { name: 'Pen' }));
  expect(swatch()).toBe('rgb(255, 45, 85)');
  expect(session.styles.highlighter.color).toBe('#00e5ff');
});

it('the Eraser greys out Color, Stroke width and Placement, still on the row; Clear annotations stays as it was', () => {
  render(<Panel />);
  const disabled = () => ['Colour', 'Stroke width', 'Placement', 'Clear annotations'].map(name => screen.getByRole('button', { name }).hasAttribute('disabled'));
  expect(disabled()).toEqual([false, false, false, true]);
  fireEvent.click(screen.getByRole('button', { name: 'Eraser' }));
  expect(disabled()).toEqual([true, true, true, true]);
  act(() => session.add([{ id: 'a', kind: 'stroke', points: new Float32Array(6), color: '#ff2d55', width: 2 } as any]));
  expect(disabled()).toEqual([true, true, true, false]);
  fireEvent.click(screen.getByRole('button', { name: 'Pen' }));
  expect(disabled()).toEqual([false, false, false, false]);
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

it("Stroke width's button is a straight line at the current weight; its menu has no heading, a row per weight, the line at that weight alone, the current one checked", async () => {
  render(<Panel />);
  const weight = (element: Element | null) => element?.querySelector('svg[data-stroke-weight]')?.getAttribute('data-stroke-weight');
  expect(weight(screen.getByRole('button', { name: 'Stroke width' }))).toBe('2');
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

it("a phone's row is the same row, wrapping only where the view has no room for it", () => {
  render(<Panel />);
  const classes = screen.getByRole('toolbar', { name: 'Annotation controls' }).className.split(/\s+/);
  expect(classes).toEqual(expect.arrayContaining(['flex-nowrap', 'data-[touch]:flex-wrap']));
});
