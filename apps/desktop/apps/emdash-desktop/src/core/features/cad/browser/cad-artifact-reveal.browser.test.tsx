import { observable, runInAction } from 'mobx';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationManagerStore } from '@core/features/conversations/api/browser/conversation-manager';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { useCadArtifactReveal } from './cad-artifact-reveal';
import { cadTurnLedger } from './cad-turn-ledger';

const mocks = vi.hoisted(() => ({
  listCadArtifacts: vi.fn(),
  validateCadModel: vi.fn(),
  openFile: vi.fn(),
  announce: vi.fn(),
}));
vi.mock('@core/features/browser/api/browser/client', () => ({
  getBrowserClient: async () => mocks,
}));
vi.mock('@core/features/workbench/api/browser/open-file', () => ({ openFile: mocks.openFile }));
vi.mock('@emdash/ui/react/primitives', () => ({ toast: { info: mocks.announce } }));

let root: Root;
let host: HTMLDivElement;
let taskNumber = 0;
const tracked = () => false;

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  cadTurnLedger.turns.clear();
  mocks.validateCadModel.mockResolvedValue({ success: true });
  mocks.listCadArtifacts.mockResolvedValue({
    success: true,
    artifacts: [{ path: 'models/part.step', mtimeMs: Date.now() - 2_000 }],
    truncated: false,
  });
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.useRealTimers();
});

async function mount(hasOpenCadTab = false) {
  const pane = observable({
    resolvedTabs: (hasOpenCadTab ? [{ kind: 'cad' }] : []) as Array<{
      kind: string;
      isActive?: boolean;
      isPreview?: boolean;
      resource?: { path: string };
    }>,
  });
  const task = {
    projectId: 'project',
    taskId: `task-${++taskNumber}`,
    workspace: { path: `/workspace-${taskNumber}` },
    paneLayout: { groups: [{ pane }] },
  };
  mocks.openFile.mockImplementation((ref, options) => {
    runInAction(() => {
      pane.resolvedTabs = [
        {
          kind: 'cad',
          isActive: true,
          isPreview: options.preview,
          resource: { path: nativePathFromHost(ref.path) },
        },
      ];
    });
    return true;
  });
  const conversations = {
    conversations: observable.map([['conversation', observable({ status: 'working' })]]),
  } as unknown as ConversationManagerStore;
  function Reveal() {
    useCadArtifactReveal(task, conversations, tracked);
    return null;
  }
  await act(async () => root.render(<Reveal />));
  return task;
}

async function advance(ms: number) {
  await act(async () => vi.advanceTimersByTimeAsync(ms));
}

describe('CAD output during an active conversation', () => {
  it('opens a validated STEP before the turn ends and only reveals it once', async () => {
    await mount();
    await advance(750);
    expect(mocks.validateCadModel).toHaveBeenCalledOnce();
    expect(mocks.openFile).toHaveBeenCalledOnce();
    expect(mocks.openFile.mock.calls[0]?.[1]).toMatchObject({ target: 'artifact' });
    await advance(4_000);
    expect(mocks.openFile).toHaveBeenCalledOnce();
    expect(mocks.validateCadModel).toHaveBeenCalledOnce();
  });

  it('retries a recent write and an invalid intermediate STEP before opening it', async () => {
    mocks.listCadArtifacts.mockResolvedValueOnce({
      success: true,
      artifacts: [{ path: 'models/part.step', mtimeMs: Date.now() + 500 }],
      truncated: false,
    });
    mocks.validateCadModel.mockResolvedValueOnce({ success: false, error: 'incomplete STEP' });
    await mount();
    await advance(750);
    expect(mocks.validateCadModel).not.toHaveBeenCalled();
    await advance(2_000);
    expect(mocks.openFile).not.toHaveBeenCalled();
    await advance(2_000);
    expect(mocks.openFile).toHaveBeenCalledOnce();
  });

  it('announces a new model without replacing the selected CAD tab', async () => {
    await mount(true);
    await advance(750);
    expect(mocks.openFile).not.toHaveBeenCalled();
    expect(mocks.announce).toHaveBeenCalledOnce();
    expect(mocks.announce.mock.calls[0]?.[1].action.label).toBe('Open');
  });

  it('does not open a model when navigation happens during validation', async () => {
    let complete!: (result: { success: boolean }) => void;
    mocks.validateCadModel.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        })
    );
    await mount();
    await advance(750);
    await act(async () => root.render(null));
    complete({ success: true });
    await advance(2_000);
    expect(mocks.openFile).not.toHaveBeenCalled();
    expect(mocks.announce).not.toHaveBeenCalled();
  });

  it('advances the preview through first-build parts and the finished assembly', async () => {
    await mount();
    await advance(750);
    for (const path of ['models/lid.step', 'models/assembly.step']) {
      mocks.listCadArtifacts.mockResolvedValue({
        success: true,
        artifacts: [{ path, mtimeMs: Date.now() - 2_000 }],
        truncated: false,
      });
      await advance(2_000);
    }
    expect(mocks.openFile).toHaveBeenCalledTimes(3);
    expect(mocks.openFile.mock.calls.every(([, options]) => options.preview === true)).toBe(true);
  });

  it.each(['pin', 'select', 'close'])(
    'stops following when the user chooses to %s',
    async (choice) => {
      const task = await mount();
      await advance(750);
      await act(async () => {
        runInAction(() => {
          const pane = task.paneLayout.groups[0]!.pane;
          if (choice === 'close') pane.resolvedTabs = [];
          else if (choice === 'pin') pane.resolvedTabs[0]!.isPreview = false;
          else pane.resolvedTabs[0]!.isActive = false;
        });
      });
      mocks.listCadArtifacts.mockResolvedValue({
        success: true,
        artifacts: [{ path: 'models/assembly.step', mtimeMs: Date.now() - 2_000 }],
        truncated: false,
      });
      await advance(2_000);
      expect(mocks.openFile).toHaveBeenCalledOnce();
      expect(mocks.announce.mock.calls.at(-1)?.[1].action.label).toBe('Open');
    }
  );
});
