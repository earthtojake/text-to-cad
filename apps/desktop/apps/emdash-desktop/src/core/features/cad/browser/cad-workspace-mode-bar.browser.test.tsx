import '@emdash/ui/style.css';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import '../../../../renderer/index.css';
import { CadWorkspaceModeBar } from './cad-workspace-mode-bar';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('CadWorkspaceModeBar', () => {
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

  it('shows artifact views and local actions directly without an output menu', async () => {
    const onChange = vi.fn();
    const onRefresh = vi.fn();
    const onAnnotate = vi.fn();
    const onCapture = vi.fn();
    const onAddOutput = vi.fn();
    await act(async () => {
      root.render(
        <CadWorkspaceModeBar
          modes={['3d', 'files', 'parameters', 'source']}
          activeMode="3d"
          onChange={onChange}
          onRefresh={onRefresh}
          onAnnotate={onAnnotate}
          onCapture={onCapture}
          onAddOutput={onAddOutput}
        />
      );
    });

    expect(page.getByRole('button', { name: /Output:/ }).query()).toBeNull();
    expect(page.getByRole('button', { name: 'More artifact actions' }).query()).toBeNull();
    expect(page.getByRole('tab', { name: '3D' })).toBeVisible();
    expect(page.getByRole('tab', { name: 'Analysis' }).query()).toBeNull();
    await page.getByRole('button', { name: 'Create engineering drawing' }).click();
    expect(onAddOutput).toHaveBeenCalledWith('drawing');
    await page.getByRole('tab', { name: 'Files' }).click();
    expect(onChange).toHaveBeenCalledWith('files');
    await page.getByRole('tab', { name: 'Source' }).click();
    expect(onChange).toHaveBeenCalledWith('source');
    await page.getByRole('tab', { name: 'Parameters' }).click();
    expect(onChange).toHaveBeenCalledWith('parameters');
    await page.getByRole('button', { name: 'Refresh model' }).click();
    expect(onRefresh).toHaveBeenCalledOnce();
    await page.getByRole('button', { name: 'Annotate model' }).click();
    expect(onAnnotate).toHaveBeenCalledOnce();
    await page.getByRole('button', { name: 'Copy screenshot to chat' }).click();
    expect(onCapture).toHaveBeenCalledOnce();
  });

  it('shows an existing drawing as a direct view and removes the create action', async () => {
    const onChange = vi.fn();
    await act(async () => {
      root.render(
        <CadWorkspaceModeBar
          modes={['3d', 'drawing', 'files', 'source']}
          activeMode="drawing"
          onChange={onChange}
        />
      );
    });

    expect(page.getByRole('button', { name: 'Create engineering drawing' }).query()).toBeNull();
    expect(page.getByRole('tab', { name: 'Drawing' })).toBeVisible();
    await page.getByRole('tab', { name: '3D' }).click();
    expect(onChange).toHaveBeenCalledWith('3d');
  });

  it('replaces direct artifact actions with the overflow menu in a compact pane', async () => {
    host.style.width = '320px';
    await act(async () => {
      root.render(
        <CadWorkspaceModeBar
          modes={['3d', 'source']}
          activeMode="3d"
          onChange={vi.fn()}
          onRefresh={vi.fn()}
          onAnnotate={vi.fn()}
          onCapture={vi.fn()}
        />
      );
    });

    const directAnnotate = host.querySelector<HTMLButtonElement>('[aria-label="Annotate model"]');
    const directCapture = host.querySelector<HTMLButtonElement>(
      '[aria-label="Copy screenshot to chat"]'
    );
    const directRefresh = host.querySelector<HTMLButtonElement>('[aria-label="Refresh model"]');
    const overflowMenu = host.querySelector<HTMLButtonElement>(
      '[aria-label="More artifact actions"]'
    );

    expect(directAnnotate).not.toBeNull();
    expect(directAnnotate!.checkVisibility()).toBe(false);
    expect(directCapture).not.toBeNull();
    expect(directCapture!.checkVisibility()).toBe(false);
    expect(directRefresh).not.toBeNull();
    expect(directRefresh!.checkVisibility()).toBe(true);
    expect(overflowMenu).not.toBeNull();
    expect(overflowMenu!.checkVisibility()).toBe(true);

    await page.getByRole('button', { name: 'More artifact actions' }).click();
    expect(page.getByRole('menuitem', { name: 'Annotate model' })).toBeVisible();
    expect(page.getByRole('menuitem', { name: 'Copy screenshot to chat' })).toBeVisible();
    expect(page.getByRole('menuitem', { name: 'Refresh model' }).query()).toBeNull();
  });
});
