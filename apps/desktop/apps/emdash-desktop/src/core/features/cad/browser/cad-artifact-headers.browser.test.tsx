import '@emdash/ui/style.css';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import '../../../../renderer/index.css';
import { CadDrawingPanel } from './cad-drawing-panel';
import { CadSourcePanel } from './cad-source-panel';

const { discard } = vi.hoisted(() => ({ discard: vi.fn() }));

vi.mock('@core/features/editor/contributions/browser/use-embedded-source-editor', () => ({
  useEmbeddedSourceEditor: () => ({
    entry: { dirty: true, status: { kind: 'ready' } },
    editorHostRef: { current: null },
    save: vi.fn(async () => ({ success: true })),
    discard,
    loading: false,
  }),
}));

vi.mock('./use-cad-source-rebuild', () => ({
  useCadSourceRebuild: () => ({
    rebuildSource: vi.fn(async () => ({ success: true })),
    rebuilding: false,
    runInProgress: false,
  }),
}));

vi.mock('@core/primitives/theme/browser', () => ({
  useTheme: () => ({ effectiveTheme: 'light' }),
}));

vi.mock('@core/manifests/browser/modal-api', () => ({
  useOpenModal: () => vi.fn(),
}));

vi.mock('@core/features/workbench/api/browser/task-composition-context', () => ({
  useWorkspace: () => ({ sshConnectionId: null }),
}));

vi.mock('@core/features/files/api/browser/client', () => ({
  getFilesClient: async () => ({
    fs: {
      readBytes: () => new Promise(() => {}),
      readText: () => new Promise(() => {}),
    },
  }),
}));

vi.mock('@core/features/workbench/api/browser/open-with-os', () => ({
  openWithOS: vi.fn(),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('compact CAD artifact headers', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    host.style.width = '420px';
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
    discard.mockClear();
  });

  it('keeps rebuild visible and moves source utilities into the overflow menu', async () => {
    await act(async () => {
      root.render(
        <CadSourcePanel
          resource={
            {
              workspacePath: '/tmp/project',
              setWorkspaceMode: vi.fn(),
            } as never
          }
          task={{ getRemoteConnectionId: () => undefined } as never}
          sourcePath="/tmp/project/a-very-long-model-recipe-name.py"
        />
      );
    });

    const saveButton = [...host.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Save'
    );
    const discardButton = [...host.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Discard'
    );
    const more = host.querySelector<HTMLButtonElement>('[aria-label="More source actions"]');

    expect(page.getByRole('button', { name: 'Rebuild & view' })).toBeVisible();
    expect(saveButton).not.toBeUndefined();
    expect(saveButton!.checkVisibility()).toBe(false);
    expect(discardButton).not.toBeUndefined();
    expect(discardButton!.checkVisibility()).toBe(false);
    expect(more).not.toBeNull();
    expect(more!.checkVisibility()).toBe(true);

    await act(async () => {
      await page.getByRole('button', { name: 'More source actions' }).click();
    });
    expect(page.getByRole('menuitem', { name: 'Save source' })).toBeVisible();
    expect(page.getByRole('menuitem', { name: 'Discard changes' })).toBeVisible();
  });

  it('keeps drawing update visible and moves file utilities into the overflow menu', async () => {
    await act(async () => {
      root.render(
        <CadDrawingPanel
          drawings={[
            { name: 'bracket.svg', path: '/tmp/bracket.svg', role: 'drawing' },
            { name: 'bracket.pdf', path: '/tmp/bracket.pdf', role: 'drawing' },
            { name: 'bracket.dxf', path: '/tmp/bracket.dxf', role: 'drawing' },
          ]}
          regenerating={false}
          onRegenerate={vi.fn()}
        />
      );
    });

    const directPdf = [...host.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'PDF'
    );
    const directOpen = [...host.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Open SVG'
    );
    const more = host.querySelector<HTMLButtonElement>('[aria-label="More drawing actions"]');

    expect(page.getByRole('button', { name: 'Update' })).toBeVisible();
    expect(directPdf).not.toBeUndefined();
    expect(directPdf!.checkVisibility()).toBe(false);
    expect(directOpen).not.toBeUndefined();
    expect(directOpen!.checkVisibility()).toBe(false);
    expect(more).not.toBeNull();
    expect(more!.checkVisibility()).toBe(true);

    await act(async () => {
      await page.getByRole('button', { name: 'More drawing actions' }).click();
    });
    expect(page.getByRole('menuitem', { name: 'Open PDF' })).toBeVisible();
    expect(page.getByRole('menuitem', { name: 'Open DXF' })).toBeVisible();
    expect(page.getByRole('menuitem', { name: 'Open SVG' })).toBeVisible();
  });
});
