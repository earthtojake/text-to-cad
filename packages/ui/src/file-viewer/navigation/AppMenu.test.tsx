import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AppMenu } from '../../../dist/file-viewer/navigation/AppMenu.js';
import { ViewerMobileContext } from '../../../dist/file-viewer/responsive.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('on a phone the Language row opens its choices in place, closed by default, and a choice closes them again', async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  render(<ViewerMobileContext.Provider value={true}>
    <AppMenu trigger={<button type="button">Menu</button>} language={{ locale: 'en', inferred: 'en', choice: null, onChoiceChange: change }} />
  </ViewerMobileContext.Provider>);
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  const row = document.querySelector<HTMLElement>('[data-menu-language]')!;
  // The same row as on a desktop: its name, then the language in force and a chevron.
  expect([row.textContent, row.getAttribute('aria-expanded'), document.querySelectorAll('[data-language-option]').length]).toEqual(['LanguageEnglish', 'false', 0]);
  fireEvent.click(row);
  expect(row.getAttribute('aria-expanded')).toBe('true');
  expect([...document.querySelectorAll('[data-language-option]')].map(option => option.textContent))
    .toEqual(['Automatic (English)', 'English', '简体中文', '繁體中文', '日本語', '한국어']);
  fireEvent.click(screen.getByRole('menuitemradio', { name: '日本語' }));
  expect(change.mock.calls).toEqual([['ja']]);
  expect([row.getAttribute('aria-expanded'), document.querySelectorAll('[data-language-option]').length, Boolean(document.querySelector('[data-app-menu]'))])
    .toEqual(['false', 0, true]);
});
