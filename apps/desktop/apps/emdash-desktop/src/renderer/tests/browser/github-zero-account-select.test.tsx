import '@emdash/ui/style.css';
import { Select } from '@emdash/ui/react/primitives';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GITHUB_CONNECT_ACCOUNT_OPTION,
  GITHUB_INFERRED_NONE_OPTION,
  GitHubZeroAccountSelectItems,
} from '@core/features/projects/contributions/browser/github-account-select';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

/**
 * Zero-account picker state (spec: github-git-settings §5): with no accounts
 * connected the project settings account select offers only "Inferred (none)"
 * plus a Connect entry — no explicit-none sentinel, no dead account list.
 */
describe('GitHubZeroAccountSelectItems', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  async function renderOpenSelect(onValueChange: (value: string) => void) {
    await act(async () => {
      root.render(
        <Select.Root
          open
          value={GITHUB_INFERRED_NONE_OPTION}
          onValueChange={(value) => {
            if (typeof value === 'string') onValueChange(value);
          }}
        >
          <Select.Trigger>GitHub account</Select.Trigger>
          <Select.Content>
            <GitHubZeroAccountSelectItems />
          </Select.Content>
        </Select.Root>
      );
    });
  }

  function items(): HTMLElement[] {
    return [...document.querySelectorAll<HTMLElement>('[data-slot="select-item"]')];
  }

  function press(element: HTMLElement) {
    const init = { bubbles: true, cancelable: true };
    element.dispatchEvent(new PointerEvent('pointerdown', init));
    element.dispatchEvent(new MouseEvent('mousedown', init));
    element.dispatchEvent(new PointerEvent('pointerup', init));
    element.dispatchEvent(new MouseEvent('mouseup', init));
    element.dispatchEvent(new MouseEvent('click', init));
  }

  it('offers only Inferred (none) plus a Connect entry', async () => {
    await renderOpenSelect(vi.fn());

    const labels = items().map((item) => item.textContent ?? '');
    expect(labels).toHaveLength(2);
    expect(labels[0]).toContain('Inferred (none)');
    expect(labels[0]).toContain('No account connected');
    expect(labels[1]).toContain('Connect GitHub account');
  });

  it('selecting the Connect entry reports the connect option value', async () => {
    const onValueChange = vi.fn();
    await renderOpenSelect(onValueChange);

    const connectItem = items().find((item) =>
      item.textContent?.includes('Connect GitHub account')
    );
    if (!connectItem) throw new Error('connect entry not rendered');
    await act(async () => press(connectItem));

    expect(onValueChange).toHaveBeenCalledWith(GITHUB_CONNECT_ACCOUNT_OPTION);
  });
});
