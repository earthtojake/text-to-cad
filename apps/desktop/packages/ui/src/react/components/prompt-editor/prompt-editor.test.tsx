/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { createRef, useEffect, useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PromptEditor } from './prompt-editor';
import type { MentionItem, PromptEditorRef } from './types';

afterEach(cleanup);

describe('PromptEditor', () => {
  it('keeps the Chat submit and clear behavior by default', async () => {
    const editorRef = createRef<PromptEditorRef>();
    const onSubmit = vi.fn();
    const { getByTestId } = render(<PromptEditor ref={editorRef} onSubmit={onSubmit} />);
    await waitFor(() => expect(editorRef.current).not.toBeNull());
    act(() => editorRef.current?.setText('Draft prompt'));

    const editor = getByTestId('prompt-editor');
    fireEvent.keyDown(editor, { key: 'Enter', shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(editor.querySelector('br:not(.ProseMirror-trailingBreak)')).not.toBeNull();

    act(() => editorRef.current?.setText('Draft prompt'));
    fireEvent.keyDown(editor, { key: 'Enter' });

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith('Draft prompt');
    expect(editorRef.current?.getText()).toBe('');
  });

  it('reconciles controlled serialized values without echoing them as changes', async () => {
    const editorRef = createRef<PromptEditorRef>();
    const onChange = vi.fn();

    function ControlledEditor({ externalValue }: { externalValue: string }) {
      const [value, setValue] = useState(externalValue);
      useEffect(() => setValue(externalValue), [externalValue]);
      return (
        <PromptEditor
          ref={editorRef}
          value={value}
          onChange={(nextValue) => {
            onChange(nextValue);
            setValue(nextValue);
          }}
        />
      );
    }

    const { getByTestId, rerender } = render(<ControlledEditor externalValue="Initial prompt" />);

    await waitFor(() => expect(editorRef.current?.getText()).toBe('Initial prompt'));
    expect(onChange).not.toHaveBeenCalled();
    const editorElement = getByTestId('prompt-editor');

    act(() => editorRef.current?.setText('Typed prompt'));
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith('Typed prompt');

    rerender(<ControlledEditor externalValue="Typed prompt" />);

    expect(getByTestId('prompt-editor')).toBe(editorElement);
    expect(onChange).toHaveBeenCalledOnce();

    rerender(<ControlledEditor externalValue="Replacement prompt" />);

    await waitFor(() => expect(editorRef.current?.getText()).toBe('Replacement prompt'));
    expect(getByTestId('prompt-editor')).toBe(editorElement);
    expect(onChange).toHaveBeenCalledOnce();
  });

  it('preserves an exact controlled mention token in serialized output', async () => {
    const editorRef = createRef<PromptEditorRef>();
    const mentions: MentionItem[] = [
      {
        id: 'requirements',
        kind: 'file',
        label: 'requirements.md',
        name: 'requirements.md',
        serializedText: '@requirements.md',
      },
    ];

    render(
      <PromptEditor
        ref={editorRef}
        value="Read @requirements.md before coding"
        mentions={mentions}
      />
    );

    await waitFor(() =>
      expect(editorRef.current?.getText()).toBe('Read @requirements.md before coding')
    );
  });

  it('submits only on Mod+Enter and retains content when configured for create mode', async () => {
    const editorRef = createRef<PromptEditorRef>();
    const onSubmit = vi.fn();
    const { getByTestId } = render(
      <PromptEditor
        ref={editorRef}
        submitShortcut="mod-enter"
        clearOnSubmit={false}
        onSubmit={onSubmit}
      />
    );
    await waitFor(() => expect(editorRef.current).not.toBeNull());
    act(() => editorRef.current?.setText('Draft prompt'));

    const editor = getByTestId('prompt-editor');
    fireEvent.keyDown(editor, { key: 'Enter' });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(editor.querySelectorAll('p')).toHaveLength(2);

    act(() => editorRef.current?.setText('Draft prompt'));
    const modKey = navigator.platform.includes('Mac') ? { metaKey: true } : { ctrlKey: true };
    fireEvent.keyDown(editor, { key: 'Enter', ...modKey });

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith('Draft prompt');
    expect(editorRef.current?.getText()).toBe('Draft prompt');
  });

  it('does not submit from the keyboard when the shortcut is disabled', async () => {
    const editorRef = createRef<PromptEditorRef>();
    const onSubmit = vi.fn();
    const { getByTestId } = render(
      <PromptEditor ref={editorRef} submitShortcut="none" onSubmit={onSubmit} />
    );
    await waitFor(() => expect(editorRef.current).not.toBeNull());
    act(() => editorRef.current?.setText('Draft prompt'));

    const editor = getByTestId('prompt-editor');
    fireEvent.keyDown(editor, { key: 'Enter' });
    const modKey = navigator.platform.includes('Mac') ? { metaKey: true } : { ctrlKey: true };
    fireEvent.keyDown(editor, { key: 'Enter', ...modKey });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('keeps async mention and command sources available', async () => {
    const editorRef = createRef<PromptEditorRef>();
    const searchMentions = vi.fn().mockResolvedValue([]);
    const queryCommands = vi.fn().mockResolvedValue([]);
    const { getByTestId } = render(
      <PromptEditor
        ref={editorRef}
        mentionProvider={{ search: searchMentions }}
        queryCommands={queryCommands}
      />
    );
    await waitFor(() => expect(editorRef.current).not.toBeNull());
    const editor = getByTestId('prompt-editor');

    act(() => editorRef.current?.setText('@file'));
    fireEvent.focus(editor);
    const mentionRange = document.createRange();
    mentionRange.selectNodeContents(editor.querySelector('p')!);
    mentionRange.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(mentionRange);
    fireEvent(document, new Event('selectionchange'));

    await waitFor(() => expect(searchMentions).toHaveBeenCalledWith('file'));

    act(() => editorRef.current?.setText('/help'));
    const commandRange = document.createRange();
    commandRange.selectNodeContents(editor.querySelector('p')!);
    commandRange.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(commandRange);
    fireEvent(document, new Event('selectionchange'));

    await waitFor(() => expect(queryCommands).toHaveBeenCalledWith('help'));
  });
});
