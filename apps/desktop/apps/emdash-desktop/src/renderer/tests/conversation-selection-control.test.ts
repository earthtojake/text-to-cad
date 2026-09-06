import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationSelectionControl } from '@core/features/conversations/browser/conversation-selection-control';

describe('ConversationSelectionControl', () => {
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

  function renderControl(
    onOpen: () => void,
    onToggle: (shiftKey: boolean) => void,
    onRangeStep?: (direction: -1 | 1) => void
  ) {
    act(() => {
      root.render(
        React.createElement(
          'div',
          { onClick: onOpen },
          React.createElement(
            ConversationSelectionControl,
            {
              label: 'Select Codex conversation',
              selected: false,
              onToggle,
              onRangeStep,
            },
            '2d'
          )
        )
      );
    });
  }

  it('selects without activating the conversation row', () => {
    const onOpen = vi.fn();
    const onToggle = vi.fn();
    renderControl(onOpen, onToggle);

    const checkbox = container.querySelector('[aria-label="Select Codex conversation"]');
    act(() => {
      checkbox?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    expect(onToggle).toHaveBeenCalledWith(false);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('forwards Shift selection without activating the conversation row', () => {
    const onOpen = vi.fn();
    const onToggle = vi.fn();
    renderControl(onOpen, onToggle);

    const checkbox = container.querySelector('[aria-label="Select Codex conversation"]');
    act(() => {
      checkbox?.dispatchEvent(
        new dom.window.PointerEvent('pointerdown', { bubbles: true, shiftKey: true })
      );
      checkbox?.dispatchEvent(
        new dom.window.MouseEvent('click', { bubbles: true, shiftKey: true })
      );
    });

    expect(onToggle).toHaveBeenCalledWith(true);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it.each([
    ['ArrowDown', 1],
    ['ArrowUp', -1],
  ] as const)(
    'forwards Shift+%s as a range step without activating the conversation row',
    (key, direction) => {
      const onOpen = vi.fn();
      const onToggle = vi.fn();
      const onRangeStep = vi.fn();
      renderControl(onOpen, onToggle, onRangeStep);

      const checkbox = container.querySelector('[aria-label="Select Codex conversation"]');
      act(() => {
        checkbox?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
      });

      const keydown = new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key,
        shiftKey: true,
      });
      act(() => {
        checkbox?.dispatchEvent(keydown);
      });

      expect(onToggle).toHaveBeenCalledWith(false);
      expect(onRangeStep).toHaveBeenCalledWith(direction);
      expect(keydown.defaultPrevented).toBe(true);
      expect(onOpen).not.toHaveBeenCalled();
    }
  );
});
