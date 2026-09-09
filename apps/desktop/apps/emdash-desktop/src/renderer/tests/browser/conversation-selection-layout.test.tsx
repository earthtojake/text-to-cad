import { Checkbox } from '@emdash/ui/react/primitives';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationSelectionControl } from '@core/features/conversations/browser/conversation-selection-control';

function horizontalCenter(element: Element) {
  const box = element.getBoundingClientRect();
  return box.left + box.width / 2;
}

describe('ConversationSelectionControl layout', () => {
  let container: HTMLDivElement;
  let root: Root;
  let style: HTMLStyleElement;

  beforeEach(() => {
    style = document.createElement('style');
    style.textContent = `
      .relative { position: relative; }
      .absolute { position: absolute; }
      .inset-0 { inset: 0; }
      .flex { display: flex; }
      .h-full { height: 100%; }
      .w-7 { width: 1.75rem; }
      .shrink-0 { flex-shrink: 0; }
      .items-center { align-items: center; }
      .justify-center { justify-content: center; }
      .size-4 { width: 1rem; height: 1rem; }
    `;
    document.head.append(style);

    container = document.createElement('div');
    container.style.font = '12px sans-serif';
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    style.remove();
  });

  it('centers the checkbox on the timestamp position', () => {
    act(() => {
      root.render(
        <div style={{ display: 'flex', height: 32, alignItems: 'center' }}>
          <ConversationSelectionControl
            label="Select conversation"
            selected={false}
            onToggle={vi.fn()}
          >
            <span data-testid="timestamp" className="flex h-full items-center">
              3d
            </span>
          </ConversationSelectionControl>
        </div>
      );
    });

    const timestamp = container.querySelector<HTMLElement>('[data-testid="timestamp"]');
    const checkbox = container.querySelector<HTMLElement>('[aria-label="Select conversation"]');
    expect(timestamp).not.toBeNull();
    expect(checkbox).not.toBeNull();

    const timestampRange = document.createRange();
    timestampRange.selectNodeContents(timestamp!);
    const timestampBox = timestampRange.getBoundingClientRect();
    const timestampCenter = timestampBox.left + timestampBox.width / 2;
    const checkboxCenter = horizontalCenter(checkbox!);

    expect(Math.abs(timestampCenter - checkboxCenter)).toBeLessThanOrEqual(0.5);
  });

  it('aligns row and section checkboxes with the add-action column', () => {
    act(() => {
      root.render(
        <div style={{ width: 240 }}>
          <div style={{ display: 'flex', height: 32, justifyContent: 'flex-end' }}>
            <span data-testid="add-action" className="flex h-full w-7 items-center justify-center">
              +
            </span>
          </div>
          <div style={{ display: 'flex', height: 32, justifyContent: 'flex-end' }}>
            <span className="flex h-full w-7 items-center justify-center">
              <Checkbox aria-label="Select section" />
            </span>
          </div>
          <div style={{ display: 'flex', height: 32, justifyContent: 'flex-end' }}>
            <ConversationSelectionControl label="Select conversation" selected onToggle={vi.fn()} />
          </div>
        </div>
      );
    });

    const addAction = container.querySelector<HTMLElement>('[data-testid="add-action"]');
    const sectionCheckbox = container.querySelector<HTMLElement>('[aria-label="Select section"]');
    const rowCheckbox = container.querySelector<HTMLElement>('[aria-label="Select conversation"]');
    expect(addAction).not.toBeNull();
    expect(sectionCheckbox).not.toBeNull();
    expect(rowCheckbox).not.toBeNull();

    const expectedCenter = horizontalCenter(addAction!);
    expect(Math.abs(horizontalCenter(sectionCheckbox!) - expectedCenter)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(horizontalCenter(rowCheckbox!) - expectedCenter)).toBeLessThanOrEqual(0.5);
  });
});
