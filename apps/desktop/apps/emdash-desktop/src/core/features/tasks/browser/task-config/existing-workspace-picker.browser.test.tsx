import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectWorkspaceOption } from '@core/features/tasks/api/browser/create-task-modal/project-workspace-options';
import { ExistingWorkspacePicker } from './existing-workspace-picker';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ExistingWorkspacePicker', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.body.replaceChildren();
  });

  it('shows unlinked registry workspaces and keeps missing rows disabled', async () => {
    const onSelect = vi.fn();
    await act(async () => {
      root.render(
        <ExistingWorkspacePicker
          workspaces={[
            workspaceOption({
              key: 'project-1\0workspace-unlinked',
              workspaceId: 'workspace-unlinked',
              path: '/repo/workspace-unlinked',
            }),
            workspaceOption({
              key: 'project-1\0workspace-missing',
              workspaceId: 'workspace-missing',
              path: '/repo/workspace-missing',
              disabledReason: 'This workspace path is no longer available.',
            }),
          ]}
          isLoading={false}
          selectedWorkspaceId={null}
          onSelect={onSelect}
        />
      );
    });

    const trigger = host.querySelector<HTMLElement>('[data-slot="combobox-trigger"]');
    expect(trigger).not.toBeNull();
    await act(async () => trigger?.click());

    const options = [...document.querySelectorAll<HTMLElement>('[role="option"]')];
    const unlinked = options.find((option) => option.textContent?.includes('workspace-unlinked'));
    const missing = options.find((option) => option.textContent?.includes('workspace-missing'));
    expect(unlinked).toBeDefined();
    expect(missing?.hasAttribute('data-disabled')).toBe(true);
    expect(missing?.textContent).toContain('This workspace path is no longer available.');

    await act(async () => unlinked?.click());
    expect(onSelect).toHaveBeenCalledWith('workspace-unlinked');
  });
});

function workspaceOption(overrides: Partial<ProjectWorkspaceOption>): ProjectWorkspaceOption {
  return {
    key: 'project-1\0workspace-1',
    workspaceId: 'workspace-1',
    kind: 'worktree',
    path: '/repo/workspace-1',
    branchName: null,
    linesAdded: null,
    linesDeleted: null,
    taskName: null,
    isLive: false,
    linkedTaskCount: 0,
    ...overrides,
  };
}
