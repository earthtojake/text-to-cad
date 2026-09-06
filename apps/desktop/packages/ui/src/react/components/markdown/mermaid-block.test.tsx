/**
 * @vitest-environment jsdom
 */
import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MermaidBlock } from './mermaid-block';

const VALID_SOURCE = 'graph TD\n  A --> B';

describe('MermaidBlock', () => {
  it('renders the diagram SVG synchronously', () => {
    const { container } = render(<MermaidBlock source={VALID_SOURCE} />);
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('expands without triggering parent click handlers', () => {
    const onParentClick = vi.fn();
    const { container, baseElement } = render(
      <div onClick={onParentClick}>
        <MermaidBlock source={VALID_SOURCE} />
      </div>
    );

    const button = container.querySelector<HTMLButtonElement>(
      'button[aria-label="Expand Mermaid diagram"]'
    );
    expect(button).not.toBeNull();

    fireEvent.click(button!);

    expect(onParentClick).not.toHaveBeenCalled();
    expect(baseElement.querySelector('[aria-label="Mermaid diagram"]')).not.toBeNull();
  });

  it('expands linked diagram nodes instead of following their SVG anchors', () => {
    const onParentClick = vi.fn();
    const { container } = render(
      <div onClick={onParentClick}>
        <MermaidBlock source={VALID_SOURCE} />
      </div>
    );

    const preview = container.querySelector<HTMLDivElement>(
      '[aria-label="Expand Mermaid diagram preview"]'
    );
    expect(preview).not.toBeNull();

    const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
    fireEvent(preview!.querySelector('svg')!, clickEvent);

    expect(clickEvent.defaultPrevented).toBe(true);
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it.each(['Enter', ' '])('expands the preview with keyboard key "%s"', (key) => {
    const onParentKeyDown = vi.fn();
    const { container, baseElement } = render(
      <div onKeyDown={onParentKeyDown}>
        <MermaidBlock source={VALID_SOURCE} />
      </div>
    );

    const preview = container.querySelector<HTMLDivElement>(
      '[aria-label="Expand Mermaid diagram preview"]'
    );
    expect(preview).not.toBeNull();

    fireEvent.keyDown(preview!, { key });

    expect(onParentKeyDown).not.toHaveBeenCalled();
    expect(baseElement.querySelector('[aria-label="Mermaid diagram"]')).not.toBeNull();
  });

  it('shows the error state with the source dump for invalid diagrams', () => {
    const { container } = render(<MermaidBlock source={'not a diagram %%%'} />);
    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert!.textContent).toContain('Unable to render Mermaid diagram.');
    expect(alert!.textContent).toContain('not a diagram %%%');
  });
});
