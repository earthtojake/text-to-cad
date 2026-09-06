import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  newProjectCommand,
  newTaskCommand,
  toggleThemeCommand,
} from '@core/features/workbench/contributions/commands';
import { windowScope } from '@core/manifests/browser/scope-catalog';
import { COMMAND_CATALOG } from '@core/manifests/shared/command-catalog';
import { detectPlatformContext } from '@core/primitives/keybindings/api';
import { KeybindingService } from '@core/primitives/keybindings/browser/keybinding-service';
import { modalStore } from '@core/primitives/modals/react/modal-store';
import { ThemeProvider } from '@core/primitives/theme/browser/theme-provider';
import type { ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { scopes } from '@core/primitives/view-scopes/browser';
import { KeybindingDispatcher } from '@renderer/lib/keybindings/keybinding-dispatcher';
import { ModalRenderer } from '@renderer/lib/modal/modal-renderer';

const PLATFORM = detectPlatformContext();

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

function dispatchEscape() {
  const target = document.activeElement ?? document.body;
  target.dispatchEvent(
    new KeyboardEvent('keydown', {
      key: 'Escape',
      code: 'Escape',
      bubbles: true,
      cancelable: true,
    })
  );
}

function dispatchNewShortcut(shiftKey: boolean) {
  const target = document.activeElement ?? document.body;
  target.dispatchEvent(
    new KeyboardEvent('keydown', {
      key: 'N',
      code: 'KeyN',
      ctrlKey: PLATFORM.os !== 'mac',
      metaKey: PLATFORM.os === 'mac',
      shiftKey,
      bubbles: true,
      cancelable: true,
    })
  );
}

function dispatchNewTask() {
  dispatchNewShortcut(false);
}

function dispatchNewProject() {
  dispatchNewShortcut(true);
}

function openConfirmModal(title: string) {
  return modalStore.open('confirmActionModal', {
    title,
    description: 'Escape routing test modal.',
    confirmLabel: 'Confirm',
  });
}

async function flushOpen() {
  // Let Base UI mount the popup and run its initial-focus pass.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
}

describe('Modal Escape routing', () => {
  let host: HTMLDivElement;
  let root: Root;
  let detachKeybindings: () => void;

  beforeEach(async () => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, PLATFORM),
      scopes,
      PLATFORM
    );
    detachKeybindings = dispatcher.attach(window);
    await act(async () => {
      root.render(
        <ThemeProvider theme="emlight" onThemeChange={vi.fn()}>
          <ModalRenderer />
        </ThemeProvider>
      );
    });
  });

  afterEach(async () => {
    detachKeybindings?.();
    for (const entry of [...modalStore.stack]) {
      modalStore.removeEntry(entry.key);
    }
    await act(async () => root.unmount());
    host.remove();
  });

  it('closes a freshly opened modal on Escape without a prior click', async () => {
    await act(async () => {
      void openConfirmModal('Fresh modal');
    });
    await flushOpen();
    expect(modalStore.isOpen).toBe(true);

    await act(async () => {
      dispatchEscape();
    });

    expect(modalStore.isOpen).toBe(false);
  });

  it('preserves window commands when a fresh modal activates before focus', async () => {
    const executeTheme = vi.fn();
    const implementation = Object.fromEntries(
      windowScope.commands.map((command) => [
        command.id,
        () => ({
          execute: command === toggleThemeCommand ? executeTheme : vi.fn(),
        }),
      ])
    ) as unknown as ViewScopeImpl<typeof windowScope>;
    const windowInstance = scopes.instantiate(windowScope(), { impl: implementation });
    scopes.activate(windowInstance);

    try {
      await act(async () => {
        void openConfirmModal('Capture origin');
      });
      await flushOpen();

      const bound = scopes.getActiveCommand(toggleThemeCommand, { belowActiveCapture: true });
      expect(bound?.availability.kind).toBe('enabled');
      bound?.execute(undefined, 'palette');
      expect(executeTheme).toHaveBeenCalledOnce();
    } finally {
      windowInstance.dispose();
    }
  });

  it('restores window shortcuts after the last modal closes', async () => {
    const executeNewTask = vi.fn();
    const executeNewProject = vi.fn();
    const implementation = Object.fromEntries(
      windowScope.commands.map((command) => [
        command.id,
        () => ({
          execute:
            command === newTaskCommand
              ? executeNewTask
              : command === newProjectCommand
                ? executeNewProject
                : vi.fn(),
        }),
      ])
    ) as unknown as ViewScopeImpl<typeof windowScope>;
    const windowInstance = scopes.instantiate(windowScope(), { impl: implementation });
    scopes.activate(windowInstance);

    try {
      await act(async () => {
        void openConfirmModal('Restore window');
      });
      await flushOpen();

      await act(async () => {
        dispatchEscape();
        await vi.waitFor(() => expect(modalStore.stack).toHaveLength(0));
      });

      expect(scopes.activePath).toEqual([windowInstance]);
      dispatchNewTask();
      dispatchNewProject();
      expect(executeNewTask).toHaveBeenCalledOnce();
      expect(executeNewProject).toHaveBeenCalledOnce();
    } finally {
      windowInstance.dispose();
    }
  });

  it('closes a modal on Escape after clicking inside it (control)', async () => {
    await act(async () => {
      void openConfirmModal('Clicked modal');
    });
    await flushOpen();

    const popup = document.querySelector<HTMLElement>('[data-slot="dialog-content"]');
    expect(popup).not.toBeNull();
    await act(async () => {
      popup!.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    });

    await act(async () => {
      dispatchEscape();
    });

    expect(modalStore.isOpen).toBe(false);
  });

  it('ignores Escape while a close guard is active', async () => {
    await act(async () => {
      void openConfirmModal('Guarded modal');
    });
    await flushOpen();

    await act(async () => {
      modalStore.setCloseGuard(true);
    });

    await act(async () => {
      dispatchEscape();
    });

    expect(modalStore.isOpen).toBe(true);
  });

  it('closes only the top modal of a stack, then the one beneath', async () => {
    await act(async () => {
      void openConfirmModal('Bottom modal');
    });
    await flushOpen();
    await act(async () => {
      void openConfirmModal('Top modal');
    });
    await flushOpen();
    expect(modalStore.stack).toHaveLength(2);
    const [bottomKey, topKey] = modalStore.stack.map((entry) => entry.key);

    await act(async () => {
      dispatchEscape();
    });

    // The top modal is closing (or already unmounted, depending on exit
    // animation timing); the bottom modal must be untouched and still open.
    const topEntry = modalStore.stack.find((entry) => entry.key === topKey);
    expect(topEntry?.closing ?? true).toBe(true);
    expect(modalStore.stack.find((entry) => entry.key === bottomKey)?.closing).toBe(false);
    expect(modalStore.isOpen).toBe(true);

    // Wait for the top modal to unmount so the one beneath becomes top again.
    await act(async () => {
      await vi.waitFor(() => {
        expect(modalStore.stack.map((entry) => entry.key)).toEqual([bottomKey]);
      });
    });
    await flushOpen();

    await act(async () => {
      dispatchEscape();
    });

    expect(modalStore.isOpen).toBe(false);
  });

  it('keeps the top capture active when the bottom modal unmounts first', async () => {
    const executeNewTask = vi.fn();
    const implementation = Object.fromEntries(
      windowScope.commands.map((command) => [
        command.id,
        () => ({ execute: command === newTaskCommand ? executeNewTask : vi.fn() }),
      ])
    ) as unknown as ViewScopeImpl<typeof windowScope>;
    const windowInstance = scopes.instantiate(windowScope(), { impl: implementation });
    scopes.activate(windowInstance);

    try {
      await act(async () => {
        void openConfirmModal('Bottom navigation modal');
      });
      await flushOpen();
      await act(async () => {
        void openConfirmModal('Top navigation modal');
      });
      await flushOpen();
      const [bottomKey, topKey] = modalStore.stack.map((entry) => entry.key);
      if (bottomKey === undefined || topKey === undefined) {
        throw new Error('Expected two modal entries');
      }

      await act(async () => {
        modalStore.removeEntry(bottomKey);
      });

      expect(modalStore.stack.map((entry) => entry.key)).toEqual([topKey]);
      dispatchNewTask();
      expect(executeNewTask).not.toHaveBeenCalled();

      await act(async () => {
        modalStore.removeEntry(topKey);
      });
      expect(scopes.activePath).toEqual([windowInstance]);
      dispatchNewTask();
      expect(executeNewTask).toHaveBeenCalledOnce();
    } finally {
      windowInstance.dispose();
    }
  });

  it('restores shortcuts after dismissAll completes navigation teardown', async () => {
    const executeNewTask = vi.fn();
    const implementation = Object.fromEntries(
      windowScope.commands.map((command) => [
        command.id,
        () => ({ execute: command === newTaskCommand ? executeNewTask : vi.fn() }),
      ])
    ) as unknown as ViewScopeImpl<typeof windowScope>;
    const windowInstance = scopes.instantiate(windowScope(), { impl: implementation });
    scopes.activate(windowInstance);

    try {
      await act(async () => {
        void openConfirmModal('Bottom navigation modal');
      });
      await flushOpen();
      await act(async () => {
        void openConfirmModal('Top navigation modal');
      });
      await flushOpen();

      await act(async () => {
        modalStore.dismissAll('navigation');
        await vi.waitFor(() => expect(modalStore.stack).toHaveLength(0));
      });

      expect(scopes.activePath).toEqual([windowInstance]);
      dispatchNewTask();
      expect(executeNewTask).toHaveBeenCalledOnce();
    } finally {
      windowInstance.dispose();
    }
  });
});
