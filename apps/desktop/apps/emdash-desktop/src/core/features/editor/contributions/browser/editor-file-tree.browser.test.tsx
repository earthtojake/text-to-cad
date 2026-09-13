import type { FileTreeHeaderContext } from '@emdash/ui/react/components';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { FileTreeHeaderBar } from './editor-file-tree';
import '@emdash/ui/style.css';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('FileTreeHeaderBar layout', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    host.style.width = '720px';
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('reserves enough inline space for the search icon', async () => {
    const context: FileTreeHeaderContext = {
      targetPath: '',
      startDraft: vi.fn(),
      collapseAll: vi.fn(),
      expandAll: vi.fn(),
    };

    await act(async () => {
      root.render(
        <FileTreeHeaderBar
          context={context}
          searchQuery="const"
          setSearchQuery={vi.fn()}
          setSearchInputRef={vi.fn()}
          onRefresh={vi.fn()}
          isRefreshing={false}
        />
      );
    });

    const input = host.querySelector<HTMLInputElement>('[aria-label="Search"]');
    const icon = input?.parentElement?.querySelector<SVGSVGElement>('svg');
    expect(input).not.toBeNull();
    expect(icon).not.toBeNull();

    const inputBox = input!.getBoundingClientRect();
    const iconBox = icon!.getBoundingClientRect();
    const textStart = inputBox.left + Number.parseFloat(getComputedStyle(input!).paddingLeft);

    expect(textStart).toBeGreaterThanOrEqual(iconBox.right + 2);
    expect(host.querySelector('[aria-label="Clear search"]')).not.toBeNull();
  });

  it('uses compact search geometry in a tab-aligned header row', async () => {
    const context: FileTreeHeaderContext = {
      targetPath: '',
      startDraft: vi.fn(),
      collapseAll: vi.fn(),
      expandAll: vi.fn(),
    };

    await act(async () => {
      root.render(
        <FileTreeHeaderBar
          context={context}
          searchQuery=""
          setSearchQuery={vi.fn()}
          setSearchInputRef={vi.fn()}
          onRefresh={vi.fn()}
          isRefreshing={false}
        />
      );
    });

    const header = host.firstElementChild;
    const input = host.querySelector<HTMLInputElement>('[aria-label="Search"]');
    expect(header).not.toBeNull();
    expect(input).not.toBeNull();

    expect(header).toHaveClass('h-[41px]', 'bg-background-secondary');
    expect(getComputedStyle(input!).height).toBe('28px');
    expect(input).toHaveClass('focus-visible:bg-transparent');
  });
});
