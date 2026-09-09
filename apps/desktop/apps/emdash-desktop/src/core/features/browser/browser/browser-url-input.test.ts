import { describe, expect, it } from 'vitest';
import { browserUrlInputText } from './browser-url-input';

describe('browserUrlInputText', () => {
  it('hides the internal blank page URL from the toolbar input', () => {
    expect(browserUrlInputText('about:blank')).toBe('');
  });

  it('keeps navigable URLs visible in the toolbar input', () => {
    expect(browserUrlInputText('http://localhost:3000/')).toBe('http://localhost:3000/');
  });
});
