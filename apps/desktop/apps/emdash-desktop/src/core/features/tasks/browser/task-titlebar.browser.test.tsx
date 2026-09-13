import '@emdash/ui/style.css';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { WorkspacePanelControls } from './task-titlebar';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('WorkspacePanelControls', () => {
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

  it('uses direct panel buttons instead of a dropdown', async () => {
    const onProjectTreeChange = vi.fn();
    const onFilesChange = vi.fn();
    const onChatChange = vi.fn();

    await act(async () => {
      root.render(
        <WorkspacePanelControls
          isProjectTreeOpen={false}
          isFilesOpen={false}
          isChatOpen={false}
          showFiles
          showChat
          onProjectTreeChange={onProjectTreeChange}
          onFilesChange={onFilesChange}
          onChatChange={onChatChange}
        />
      );
    });

    expect(page.getByRole('button', { name: 'Choose visible panels' }).query()).toBeNull();
    expect(page.getByRole('button', { name: 'Show threads' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Show chat' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Show files' })).toBeVisible();

    await page.getByRole('button', { name: 'Show files' }).click();
    expect(onFilesChange).toHaveBeenCalledOnce();
    await page.getByRole('button', { name: 'Show chat' }).click();
    expect(onChatChange).toHaveBeenCalledWith(true);
  });

  it('exposes each open panel as a pressed hide action', async () => {
    await act(async () => {
      root.render(
        <WorkspacePanelControls
          isProjectTreeOpen
          isFilesOpen
          isChatOpen
          showFiles
          showChat
          onProjectTreeChange={vi.fn()}
          onFilesChange={vi.fn()}
          onChatChange={vi.fn()}
        />
      );
    });

    for (const name of ['Hide threads', 'Hide chat', 'Hide files']) {
      const locator = page.getByRole('button', { name });
      expect(locator).toHaveAttribute('aria-pressed', 'true');
      expect(locator).toHaveAttribute('data-variant', 'ghost');
      const button = locator.query() as HTMLButtonElement;
      expect(getComputedStyle(button).width).toBe('28px');
      expect(getComputedStyle(button).height).toBe('28px');
    }
  });
});
