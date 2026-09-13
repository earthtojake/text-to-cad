/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CreateTaskModal } from './create-task-modal';
import { createReadyCreateTaskState } from './create-task-modal.fixtures';

afterEach(cleanup);

describe('CreateTaskModal', () => {
  it('renders a complete ready snapshot and reports Project intent', () => {
    const onIntent = vi.fn();
    render(<CreateTaskModal state={createReadyCreateTaskState()} onIntent={onIntent} />);

    expect(screen.getByRole('combobox', { name: /project: emdash/i })).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Create' })).not.toBeNull();

    fireEvent.click(screen.getByRole('combobox', { name: /project: emdash/i }));

    expect(onIntent).toHaveBeenCalledWith({
      type: 'overlay.changed',
      overlay: { kind: 'project' },
    });
  });

  it('keeps the controlled Project combobox open', async () => {
    function Harness() {
      const [state, setState] = useState(createReadyCreateTaskState);
      return (
        <CreateTaskModal
          state={state}
          onIntent={(intent) => {
            if (intent.type === 'overlay.changed') {
              setState((current) => ({ ...current, overlay: intent.overlay }));
            }
          }}
        />
      );
    }

    render(<Harness />);
    fireEvent.click(screen.getByRole('combobox', { name: /project: emdash/i }));

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Search Project' })).not.toBeNull()
    );
  });

  it('initially focuses an editable Prompt', async () => {
    render(<CreateTaskModal state={createReadyCreateTaskState()} onIntent={() => {}} />);

    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId('prompt-editor')));
  });

  it('keeps unavailable Create focusable and recovers the first blocker', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.create = {
      kind: 'unavailable',
      blockers: [
        {
          id: 'project',
          message: 'Select a Project.',
          target: { kind: 'project' },
        },
      ],
    };

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    const create = screen.getByRole('button', { name: 'Create' });
    expect(create.getAttribute('aria-disabled')).toBe('true');
    expect(screen.getByRole('alert').textContent).toBe('');
    fireEvent.click(create);

    expect(onIntent).not.toHaveBeenCalledWith({ type: 'create.requested' });
    expect(document.activeElement).toBe(screen.getByRole('combobox', { name: /project: emdash/i }));
    expect(screen.getByRole('alert').textContent).toContain('Select a Project.');
  });

  it('focuses the Prompt when it is the first Create blocker', () => {
    const state = createReadyCreateTaskState();
    state.create = {
      kind: 'unavailable',
      blockers: [{ id: 'prompt', message: 'Enter a Prompt.', target: { kind: 'prompt' } }],
    };
    render(<CreateTaskModal state={state} onIntent={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(document.activeElement).toBe(screen.getByTestId('prompt-editor'));
  });

  it('truncates Task names at 256 graphemes without splitting composed Unicode', () => {
    const onIntent = vi.fn();
    render(<CreateTaskModal state={createReadyCreateTaskState()} onIntent={onIntent} />);

    const taskName = screen.getByRole('textbox', { name: 'Task name' });
    fireEvent.change(taskName, { target: { value: `${'a'.repeat(255)}e\u0301tail` } });

    expect(onIntent).toHaveBeenCalledWith({
      type: 'task-name.changed',
      value: `${'a'.repeat(255)}e\u0301`,
      wasTruncated: true,
    });
  });

  it('emits Create and attachment intents from the current controlled snapshot', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.prompt.value = 'Use this context';
    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    fireEvent.click(screen.getByRole('button', { name: 'Attach files' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(onIntent).toHaveBeenCalledWith({
      type: 'prompt.attachment-picker-requested',
      insertion: {
        baseValue: 'Use this context',
        range: { from: 0, to: 0 },
      },
    });
    expect(onIntent).toHaveBeenCalledWith({ type: 'create.requested' });
  });

  it('keeps recoverable Workspace failures inside the popup', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.overlay = { kind: 'workspace-settings', nested: 'none' };
    if (state.workspace.kind === 'inspectable') {
      state.workspace.detail = {
        kind: 'unavailable',
        preset: 'use-existing',
        reason: 'Existing Workspaces could not be inspected.',
        recoverable: true,
      };
    }

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    expect(screen.getByText('Existing Workspaces could not be inspected.')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onIntent).toHaveBeenCalledWith({
      type: 'workspace.retry-requested',
      target: 'detail',
    });
  });

  it('renders Task name generation errors and reports retry intent', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.taskName = {
      kind: 'generation-error',
      value: '',
      message: 'Task name generation failed.',
      retryable: true,
    };

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    expect(screen.getByText('Task name generation failed.')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Task name generation' }));
    expect(onIntent).toHaveBeenCalledWith({ type: 'task-name.generation-retry-requested' });
  });

  it('reports Workspace search queries and list recovery intents', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.overlay = { kind: 'workspace-settings', nested: 'existing-workspace' };
    if (state.workspace.kind === 'inspectable') {
      state.workspace.selectedPreset = 'use-existing';
      state.workspace.detail = {
        kind: 'ready',
        detail: {
          preset: 'use-existing',
          workspace: {
            availability: { kind: 'available' },
            query: 'feature',
            selection: { kind: 'none' },
            options: {
              kind: 'error',
              message: 'Existing Workspaces could not be loaded.',
              retryable: true,
            },
          },
        },
      };
    }

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    const search = screen.getByRole('combobox', { name: 'Search Workspace' });
    expect(search.getAttribute('value')).toBe('feature');
    fireEvent.change(search, { target: { value: 'other' } });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onIntent).toHaveBeenCalledWith({
      type: 'workspace.existing-query-changed',
      query: 'other',
    });
    expect(onIntent).toHaveBeenCalledWith({
      type: 'workspace.retry-requested',
      target: 'existing-workspaces',
    });
  });

  it('lets users inspect why a Create From type is unsupported', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.overlay = { kind: 'create-from', nested: 'none' };
    state.origin.issue = {
      kind: 'unsupported',
      reason: 'Issue integrations are unavailable.',
    };

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    fireEvent.click(screen.getByRole('tab', { name: 'Issue' }));
    expect(onIntent).toHaveBeenCalledWith({ type: 'origin.kind-changed', kind: 'issue' });
  });

  it('uses the searchable Create From list to report a Branch selection', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.overlay = { kind: 'create-from', nested: 'none' };

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    expect(screen.getByRole('combobox', { name: 'Search Branches' })).not.toBeNull();
    fireEvent.click(screen.getByRole('option', { name: /main/i }));
    expect(onIntent).toHaveBeenCalledWith({
      type: 'origin.selected',
      origin: { kind: 'branch', id: 'main' },
    });
  });

  it('does not open an unavailable issue-provider selector', () => {
    const onIntent = vi.fn();
    const state = createReadyCreateTaskState();
    state.overlay = { kind: 'create-from', nested: 'none' };
    state.origin.activeKind = 'issue';
    if (state.origin.issue.kind === 'available') {
      state.origin.issue.provider = {
        ...state.origin.issue.provider,
        availability: { kind: 'unavailable', reason: 'Reconnect the integration.' },
      };
    }

    render(<CreateTaskModal state={state} onIntent={onIntent} />);

    fireEvent.click(screen.getByRole('combobox', { name: 'Issue provider' }));
    expect(onIntent).not.toHaveBeenCalledWith({
      type: 'overlay.changed',
      overlay: { kind: 'create-from', nested: 'issue-provider' },
    });
  });
});
