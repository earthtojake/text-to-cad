import { describe, expect, it } from 'vitest';
import {
  appendInitialConversationText,
  buildFinalPrompt,
} from '@core/features/tasks/browser/create-task-modal/initial-conversation-text';

describe('appendInitialConversationText', () => {
  it('uses the selected text when the prompt is empty', () => {
    expect(appendInitialConversationText('', 'Review this worktree.')).toBe(
      'Review this worktree.'
    );
  });

  it('appends selected text to existing prompt content', () => {
    expect(appendInitialConversationText('Existing instructions.', 'Review this worktree.')).toBe(
      'Existing instructions.\nReview this worktree.'
    );
  });

  it('ignores empty selected text', () => {
    expect(appendInitialConversationText('Existing instructions.', '   ')).toBe(
      'Existing instructions.'
    );
  });
});

describe('buildFinalPrompt', () => {
  it('returns only the user prompt when there is no issue context', () => {
    expect(buildFinalPrompt(null, 'Fix the bug.')).toBe('Fix the bug.');
  });

  it('prepends issue context before user text', () => {
    expect(buildFinalPrompt('Provider: Linear | Identifier: ENG-1', 'Fix the bug.')).toBe(
      'Provider: Linear | Identifier: ENG-1\n\nFix the bug.'
    );
  });

  it('returns only the issue context when user prompt is empty', () => {
    expect(buildFinalPrompt('Provider: Linear | Identifier: ENG-1', '')).toBe(
      'Provider: Linear | Identifier: ENG-1'
    );
  });

  it('returns undefined when both issue context and user prompt are empty', () => {
    expect(buildFinalPrompt(null, '')).toBeUndefined();
    expect(buildFinalPrompt('', '  ')).toBeUndefined();
  });

  it('trims whitespace from both parts', () => {
    expect(buildFinalPrompt('  context  ', '  prompt  ')).toBe('context\n\nprompt');
  });
});
