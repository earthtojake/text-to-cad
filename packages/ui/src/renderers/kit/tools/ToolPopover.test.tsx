import React, { useState } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ToolPopover from '../../../../dist/renderers/kit/tools/ToolPopover.js';
import FloatingToolBar from '../../../../dist/renderers/kit/tools/FloatingToolBar.js';
import SelectionFilterMenu, { SelectModeMenu } from '../../../../dist/renderers/step/components/workbench/SelectionFilterMenu.js';
import { DrawingToolbar } from '../../../../dist/drawing/toolbar.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('Draw keeps settings actions open but closes on a tool choice or outside click', async () => {
  const user = userEvent.setup();
  const drawing = { ready: true, tool: 'freedraw', color: '#ff2d55', hasContent: true, canUndo: true, canRedo: true,
    selectTool: vi.fn(), selectColor: vi.fn(), undo: vi.fn(), redo: vi.fn(), clear: vi.fn() };
  function Harness() {
    const [active, setActive] = useState(false), [open, setOpen] = useState(false);
    return <><button>Outside</button><FloatingToolBar tools={[{ id: 'draw', label: 'Draw', active, icon: null,
      secondPressOpensMenu: true, onSelect: () => setActive(true),
      menu: trigger => <ToolPopover trigger={trigger} label="Drawing controls" open={open} onOpenChange={setOpen}>
        <DrawingToolbar drawing={drawing} layout="panel" onToolSelect={() => setOpen(false)} onClear={() => setOpen(false)} />
      </ToolPopover> }]} /></>;
  }
  render(<Harness />);
  const draw = screen.getByRole('button', { name: 'Draw', exact: true });
  await user.click(draw.querySelector('[data-tool-menu-corner]')!);
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(draw);
  await user.click(screen.getByRole('button', { name: 'Undo' }));
  await user.click(screen.getByRole('button', { name: 'Redo' }));
  expect(drawing.undo).toHaveBeenCalledOnce();
  expect(drawing.redo).toHaveBeenCalledOnce();
  expect(screen.getByRole('menu')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Line', exact: true }));
  expect(drawing.selectTool).toHaveBeenCalledWith('line');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(draw);
  await user.click(screen.getByRole('button', { name: 'Outside' }));
  expect(screen.queryByRole('menu')).toBeNull();
});

it('ephemeral tool options dismiss on a choice, outside press, or repeated trigger press', async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  function Harness() {
    const [active, setActive] = useState(false);
    return <><button>Outside</button><FloatingToolBar tools={[{ id: 'select', label: 'Select', active, icon: null,
      secondPressOpensMenu: true, onSelect: () => setActive(true),
      menu: trigger => <SelectionFilterMenu trigger={trigger} value="all" onChange={changed}
        options={[{ id: 'all', label: 'All' }, { id: 'faces', label: 'Faces' }]} /> }]} /></>;
  }
  render(<Harness />);
  const select = screen.getByRole('button', { name: 'Select', exact: true });
  await user.click(select);
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(select);
  expect(screen.getByRole('menu')).toBeTruthy();
  await user.click(screen.getByRole('menuitemradio', { name: 'Faces' }));
  expect(changed).toHaveBeenCalledWith('faces');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(select);
  await user.click(screen.getByRole('button', { name: 'Outside' }));
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(select);
  await user.click(select);
  expect(screen.queryByRole('menu')).toBeNull();
});

it('a corner press selects first and only opens options when already selected', async () => {
  const user = userEvent.setup();
  const activate = vi.fn();
  function Harness() {
    const [active, setActive] = useState(false);
    return <FloatingToolBar tools={[{ id: 'tool', label: 'Tool', active, icon: null,
      secondPressOpensMenu: true, onSelect: () => { activate(); setActive(true); },
      menu: trigger => <ToolPopover trigger={trigger} label="Tool options">Options</ToolPopover> }]} />;
  }
  render(<Harness />);
  const button = screen.getByRole('button', { name: 'Tool', exact: true });
  await user.click(button.querySelector('[data-tool-menu-corner]')!);
  expect(activate).toHaveBeenCalledOnce();
  expect(button.getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(button.querySelector('[data-tool-menu-corner]')!);
  expect(screen.getByRole('menu')).toBeTruthy();
  await user.hover(button);
  expect(screen.queryByRole('tooltip')).toBeNull();
});

it('the Select mode menu offers Parts only in an assembly, keeps inapplicable options disabled, and a tick leaves it open', async () => {
  const user = userEvent.setup();
  const connectedChange = vi.fn();
  function Harness({ assembly, mode }: { assembly: boolean, mode: string }) {
    return <FloatingToolBar tools={[{ id: 'select', label: 'Select', active: true, icon: null, secondPressOpensMenu: true, onSelect: () => {},
      menu: trigger => <SelectModeMenu trigger={trigger} mode={mode} assembly={assembly} onModeChange={() => {}}
        connected={{ edgeChain: false, tangentFaces: true }} onConnectedChange={connectedChange} /> }]} />;
  }
  const view = render(<Harness assembly={false} mode="faces" />);
  await user.click(screen.getByRole('button', { name: 'Select', exact: true }));
  expect(screen.getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['All', 'Faces', 'Edges']);
  const chain = screen.getByRole('menuitemcheckbox', { name: 'Edge chain' });
  expect(chain.getAttribute('aria-disabled')).toBe('true');
  expect(screen.getByRole('menuitemcheckbox', { name: 'Tangent faces' }).getAttribute('aria-checked')).toBe('true');
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Tangent faces' }));
  expect(connectedChange).toHaveBeenCalledWith('tangentFaces', false);
  expect(screen.getByRole('menu')).toBeTruthy();
  await user.keyboard('{Escape}');
  view.rerender(<Harness assembly mode="all" />);
  await user.click(screen.getByRole('button', { name: 'Select', exact: true }));
  expect(screen.getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['All', 'Parts', 'Faces', 'Edges']);
  expect(screen.getByRole('menuitemcheckbox', { name: 'Edge chain' }).getAttribute('aria-disabled')).toBeNull();
});
