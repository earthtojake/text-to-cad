import type { GitChange } from '@emdash/core/runtimes/git/api';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChangesListItem } from '@core/features/source-control/browser/diff-view/changes-panel/components/changes-list-item';
import { portablePath } from '@core/primitives/desktop-runtime/api';

const change: GitChange = {
  path: portablePath('src/example.ts'),
  status: 'modified',
  additions: 2,
  deletions: 1,
};

describe('ChangesListItem', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);
    vi.stubGlobal('MouseEvent', dom.window.MouseEvent);
    vi.stubGlobal('PointerEvent', dom.window.PointerEvent);

    container = dom.window.document.getElementById('root') as HTMLDivElement;
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    vi.unstubAllGlobals();
    dom.window.close();
  });

  it('selects via checkbox without opening the diff row', () => {
    const onOpen = vi.fn();
    const onToggleSelect = vi.fn();

    act(() => {
      root.render(
        React.createElement(ChangesListItem, {
          change,
          onClick: onOpen,
          onToggleSelect,
        })
      );
    });

    const checkbox = container.querySelector('[aria-label="Select example.ts"]');
    expect(checkbox).not.toBeNull();

    act(() => {
      checkbox?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    expect(onToggleSelect).toHaveBeenCalledWith('src/example.ts');
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('does not trigger row pointer activation from the checkbox', () => {
    const onOpen = vi.fn();

    act(() => {
      root.render(
        React.createElement(ChangesListItem, {
          change,
          onPointerDown: onOpen,
          onToggleSelect: vi.fn(),
        })
      );
    });

    const checkbox = container.querySelector('[aria-label="Select example.ts"]');
    expect(checkbox).not.toBeNull();

    act(() => {
      checkbox?.dispatchEvent(new dom.window.PointerEvent('pointerdown', { bubbles: true }));
    });

    expect(onOpen).not.toHaveBeenCalled();
  });

  it('opens the diff row when clicking the file row outside the checkbox', () => {
    const onOpen = vi.fn();

    act(() => {
      root.render(
        React.createElement(ChangesListItem, {
          change,
          onClick: onOpen,
          onToggleSelect: vi.fn(),
        })
      );
    });

    const row = container.querySelector('button');
    expect(row).not.toBeNull();

    act(() => {
      row?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('renders the active diff highlight', () => {
    act(() => {
      root.render(React.createElement(ChangesListItem, { change, isActive: true }));
    });

    expect(container.querySelector('button')?.classList.contains('bg-background-2')).toBe(true);
  });
});
