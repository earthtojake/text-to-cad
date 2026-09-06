import { describe, expect, it } from 'vitest';
import { createTextMatcher, matchesQuery } from './matching';

describe('matchesQuery', () => {
  it('returns true for empty query', () => {
    expect(matchesQuery('anything', '')).toBe(true);
    expect(matchesQuery('anything', '   ')).toBe(true);
  });

  it('matches substrings case-insensitively', () => {
    expect(matchesQuery('Hello World', 'hello')).toBe(true);
    expect(matchesQuery('Hello World', 'WORLD')).toBe(true);
    expect(matchesQuery('Hello World', 'lo wo')).toBe(true);
  });

  it('returns false when not a substring', () => {
    expect(matchesQuery('Hello World', 'xyz')).toBe(false);
  });
});

describe('createTextMatcher', () => {
  interface Item {
    name: string;
    description: string;
  }

  const items: Item[] = [
    { name: 'Claude Sonnet', description: 'Fast coding agent' },
    { name: 'OpenAI Codex', description: 'Code generation' },
    { name: 'Gemini', description: 'Google AI' },
  ];

  it('matches against a single field', () => {
    const match = createTextMatcher<Item>((i) => i.name);
    expect(match(items[0]!, 'claude')).toBe(true);
    expect(match(items[0]!, 'SONNET')).toBe(true);
    expect(match(items[0]!, 'codex')).toBe(false);
  });

  it('matches against multiple fields', () => {
    const match = createTextMatcher<Item>((i) => [i.name, i.description]);
    expect(match(items[0]!, 'fast')).toBe(true);
    expect(match(items[1]!, 'generation')).toBe(true);
    expect(match(items[2]!, 'google')).toBe(true);
    expect(match(items[2]!, 'xyz')).toBe(false);
  });

  it('returns true for empty query', () => {
    const match = createTextMatcher<Item>((i) => i.name);
    expect(match(items[0]!, '')).toBe(true);
    expect(match(items[0]!, '  ')).toBe(true);
  });

  it('fuzzy mode matches non-contiguous chars in order', () => {
    const match = createTextMatcher<Item>((i) => i.name, { mode: 'fuzzy' });
    expect(match(items[0]!, 'cnt')).toBe(true); // c...n...t in "Claude Sonnet"
    expect(match(items[0]!, 'zz')).toBe(false);
  });

  it('fuzzy mode requires chars in order', () => {
    const match = createTextMatcher<Item>((i) => i.name, { mode: 'fuzzy' });
    // 'da' vs 'Claude': c-l-a-u-d-e — 'a' comes before 'd' so 'da' fails
    expect(match({ name: 'Claude', description: '' }, 'da')).toBe(false);
    // 'ad' works: a(aude) then d(e)
    expect(match({ name: 'Claude', description: '' }, 'ad')).toBe(true);
  });
});
