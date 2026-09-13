import { describe, expect, it } from 'vitest';
import { normalizeLatexDelimiters } from './markdown-latex';

describe('normalizeLatexDelimiters', () => {
  it('normalizes common LaTeX inline and display delimiters', () => {
    expect(normalizeLatexDelimiters('Inline \\(x^2\\) and display:\n\\[\nx^2\n\\]')).toBe(
      'Inline $x^2$ and display:\n$$\nx^2\n$$\n'
    );
  });

  it('puts dollar display math delimiters on their own lines', () => {
    expect(normalizeLatexDelimiters('Before\n$$a\n\n\\iff\n\nb$$\nAfter')).toBe(
      'Before\n$$\na\n\n\\iff\n\nb\n$$\n\nAfter'
    );
  });

  it('separates adjacent display math blocks in prose', () => {
    expect(normalizeLatexDelimiters('Für $x=1$: $$ 8=3A $$$$ A=\\frac{8}{3} $$ Weiter')).toBe(
      'Für $x=1$:\n$$\n8=3A\n$$\n$$\nA=\\frac{8}{3}\n$$\n Weiter'
    );
  });

  it('does not rewrite delimiters inside code spans or fenced code blocks', () => {
    const content = ['`\\(x\\)`', '', '```md', '\\[', 'x', '\\]', '```', '', '\\(y\\)'].join('\n');

    expect(normalizeLatexDelimiters(content)).toBe(
      ['`\\(x\\)`', '', '```md', '\\[', 'x', '\\]', '```', '', '$y$'].join('\n')
    );
  });

  it('leaves unmatched delimiters untouched', () => {
    expect(normalizeLatexDelimiters('Broken \\(x')).toBe('Broken \\(x');
  });
});
