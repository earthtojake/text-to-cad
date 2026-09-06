import { describe, expect, it } from 'vitest';
import { normalizeExternalHttpUrl } from './external-url';

describe('normalizeExternalHttpUrl', () => {
  it('removes terminal text after the URL', () => {
    expect(normalizeExternalHttpUrl('https://example.com/path (375')).toBe(
      'https://example.com/path'
    );
    expect(normalizeExternalHttpUrl('https://github.com/acme/repo/pull/593 (375')).toBe(
      'https://github.com/acme/repo/pull/593'
    );
    expect(normalizeExternalHttpUrl('https://example.com/path\t(375')).toBe(
      'https://example.com/path'
    );
  });

  it('joins URLs split by line breaks', () => {
    expect(normalizeExternalHttpUrl('https://example.com/long-\npath')).toBe(
      'https://example.com/long-path'
    );
    expect(
      normalizeExternalHttpUrl(
        'https://uploads.linear.app/d402fa9e-639b-4d1b-837a-c271947359e6/92132495-d5d\n  4-416f-806a-b47089d82878/ad04fc4b-50c0-4770-add5-2d182feb1d24'
      )
    ).toBe(
      'https://uploads.linear.app/d402fa9e-639b-4d1b-837a-c271947359e6/92132495-d5d4-416f-806a-b47089d82878/ad04fc4b-50c0-4770-add5-2d182feb1d24'
    );
  });

  it('does not join unrelated text on the next line', () => {
    expect(normalizeExternalHttpUrl('https://example.com/path\nStatus: Todo')).toBe(
      'https://example.com/path'
    );
    expect(normalizeExternalHttpUrl('https://example.com/path\n  Status: Todo')).toBe(
      'https://example.com/path'
    );
  });

  it('removes trailing punctuation commonly printed after URLs', () => {
    expect(normalizeExternalHttpUrl('https://example.com/path,')).toBe('https://example.com/path');
    expect(normalizeExternalHttpUrl('https://example.com/path).')).toBe('https://example.com/path');
  });

  it('preserves balanced trailing parentheses inside URLs', () => {
    expect(
      normalizeExternalHttpUrl('https://en.wikipedia.org/wiki/Lisp_(programming_language)')
    ).toBe('https://en.wikipedia.org/wiki/Lisp_(programming_language)');
  });

  it('preserves query strings and fragments', () => {
    expect(normalizeExternalHttpUrl('https://example.com/path?a=1&b=2#section')).toBe(
      'https://example.com/path?a=1&b=2#section'
    );
  });
});
