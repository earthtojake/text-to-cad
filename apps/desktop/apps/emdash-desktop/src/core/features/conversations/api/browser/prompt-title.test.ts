import { describe, expect, it } from 'vitest';
import { BLANK_CHAT_TITLE, hasBlankChatTitle, titleFromPrompt } from './prompt-title';

describe('titleFromPrompt', () => {
  it('uses the first non-empty line with whitespace collapsed', () => {
    expect(titleFromPrompt('\n\n  Design a   snap-fit   enclosure  \nmore')).toBe(
      'Design a snap-fit enclosure'
    );
  });

  it('cuts long prompts at a word boundary with an ellipsis', () => {
    const title = titleFromPrompt(
      'Design a compact planetary gearbox for the robot joint in README.md as a cadgen assembly'
    );
    expect(title).toBe('Design a compact planetary gearbox for the robot…');
    expect(title!.length).toBeLessThanOrEqual(49);
  });

  it('drops leading markdown markers and trailing punctuation before the ellipsis', () => {
    expect(
      titleFromPrompt('## Build me a bracket, please, with four holes and a flange today')
    ).toBe('Build me a bracket, please, with four holes and…');
  });

  it('returns null for empty input', () => {
    expect(titleFromPrompt('   \n\t')).toBeNull();
  });
});

describe('hasBlankChatTitle', () => {
  it('treats the birth title and empty titles as blank', () => {
    expect(hasBlankChatTitle(BLANK_CHAT_TITLE)).toBe(true);
    expect(hasBlankChatTitle('New chat 2')).toBe(true);
    expect(hasBlankChatTitle('New chat about gears')).toBe(false);
    expect(hasBlankChatTitle('  ')).toBe(true);
    expect(hasBlankChatTitle(undefined)).toBe(true);
    expect(hasBlankChatTitle('Gearbox')).toBe(false);
  });
});
