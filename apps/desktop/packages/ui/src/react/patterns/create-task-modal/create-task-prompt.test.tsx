/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CreateTaskPromptState } from './create-task-modal.types';
import { CreateTaskPrompt, replaceSavedPromptQuery } from './create-task-prompt';

const editableState: CreateTaskPromptState = {
  value: 'Investigate the issue',
  editability: { kind: 'editable' },
  intake: { kind: 'available' },
  completionOpen: false,
  completionQuery: '',
  savedPrompts: { kind: 'empty' },
  resources: [],
};

afterEach(cleanup);

describe('CreateTaskPrompt', () => {
  it('replaces the active saved Prompt query when the same query appears more than once', () => {
    expect(
      replaceSavedPromptQuery(
        '/review first, then /review second',
        '/review',
        'Inspect this change',
        0
      )
    ).toBe('Inspect this change first, then /review second');
  });

  it('renders a controlled document and reports Mod+Enter without clearing it', () => {
    const onIntent = vi.fn();

    render(<CreateTaskPrompt state={editableState} onIntent={onIntent} />);

    const editor = screen.getByTestId('prompt-editor');
    expect(editor.textContent).toContain('Investigate the issue');

    fireEvent.keyDown(editor, { key: 'Enter', ctrlKey: true });

    expect(onIntent).toHaveBeenCalledWith({ type: 'prompt.create-attempted' });
    expect(editor.textContent).toContain('Investigate the issue');
  });

  it('keeps a disabled draft legible and explains why it is read-only', () => {
    render(
      <CreateTaskPrompt
        state={{
          ...editableState,
          editability: { kind: 'read-only', reason: 'Select an Agent that supports Prompt input.' },
        }}
        onIntent={() => {}}
      />
    );

    expect(screen.getByTestId('prompt-editor').textContent).toContain('Investigate the issue');
    expect(screen.getByText('Select an Agent that supports Prompt input.')).not.toBeNull();
  });

  it('reports Mod+Enter for an empty document so the host can recover its blocker', () => {
    const onIntent = vi.fn();
    render(<CreateTaskPrompt state={{ ...editableState, value: '' }} onIntent={onIntent} />);

    fireEvent.keyDown(screen.getByTestId('prompt-editor'), { key: 'Enter', ctrlKey: true });

    expect(onIntent).toHaveBeenCalledWith({ type: 'prompt.create-attempted' });
  });

  it('reports resource identity for retry, view, and remove actions', () => {
    const onIntent = vi.fn();
    render(
      <CreateTaskPrompt
        state={{
          ...editableState,
          resources: [
            {
              id: 'image-1',
              kind: 'image',
              name: 'reference.png',
              previewSrc: '/reference.png',
              status: { kind: 'retryable-error', message: 'Upload failed' },
            },
          ],
        }}
        onIntent={onIntent}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'View reference.png' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retry reference.png' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove reference.png' }));

    expect(onIntent).toHaveBeenCalledWith({
      type: 'prompt.image-view-requested',
      resourceId: 'image-1',
    });
    expect(onIntent).toHaveBeenCalledWith({
      type: 'prompt.resource-retry-requested',
      resourceId: 'image-1',
    });
    expect(onIntent).toHaveBeenCalledWith({
      type: 'prompt.resource-remove-requested',
      resourceId: 'image-1',
    });
  });

  it('restores serialized file tokens as inline pending mentions', async () => {
    const { container } = render(
      <CreateTaskPrompt
        state={{
          ...editableState,
          value: 'Read @requirements.md before coding',
          resources: [
            {
              id: 'requirements',
              kind: 'file',
              name: 'requirements.md',
              mentionToken: '@requirements.md',
              status: { kind: 'pending', message: 'Indexing…', progress: null },
            },
          ],
        }}
        onIntent={() => {}}
      />
    );

    await waitFor(() => {
      const mention = container.querySelector('[data-mention-id="requirements"]');
      expect(mention?.textContent).toContain('requirements.md');
      expect(mention?.getAttribute('data-mention-pending')).toBe('true');
    });
  });

  it('renders saved Prompt recovery through the semantic retry intent', () => {
    const onIntent = vi.fn();
    render(
      <CreateTaskPrompt
        state={{
          ...editableState,
          completionOpen: true,
          savedPrompts: {
            kind: 'error',
            message: 'Saved Prompts could not be loaded.',
            retryable: true,
          },
        }}
        onIntent={onIntent}
      />
    );

    expect(screen.getByRole('alert').textContent).toContain('Saved Prompts could not be loaded.');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onIntent).toHaveBeenCalledWith({ type: 'prompt.saved-prompts-retry-requested' });
  });
});
