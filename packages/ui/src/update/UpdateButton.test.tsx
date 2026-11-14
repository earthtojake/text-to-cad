import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { I18nProvider } from '../i18n/index.js';
import { UpdateButton, readNotice, updatePrompt } from './index.js';

const NOTICE = { version: '0.11.11', latest: '0.11.12' };
const PROMPT = 'A new version of the text-to-cad plugin is available (v0.11.12). Update it from https://github.com/earthtojake/text-to-cad';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function open() {
  await userEvent.setup().click(screen.getByRole('button', { name: 'Update available: v0.11.12' }));
  return screen.findByRole('dialog', { name: /Update available/ });
}

it('the prompt is one English text, and a notice is read only in its shape', () => {
  expect(updatePrompt(NOTICE)).toBe(PROMPT);
  expect([readNotice(NOTICE), readNotice(undefined), readNotice({ latest: '0.11.12' }), readNotice('0.11.12')])
    .toEqual([NOTICE, null, null, null]);
});

it('opens the popover from its button: the versions, the line, the prompt; Copy prompt where nothing sends, copying exactly the prompt', async () => {
  const copy = vi.fn(async () => {});
  render(<UpdateButton notice={NOTICE} copy={copy} />);
  const card = await open();
  expect(card.querySelector('[data-update-versions]')?.textContent).toBe('v0.11.11 → v0.11.12');
  expect(card.textContent).toContain('A new version of the text-to-cad plugin is available. Send a message to your agent asking it to update:');
  expect(card.querySelector('[data-update-prompt]')?.textContent).toBe(PROMPT);
  expect(screen.queryByRole('button', { name: 'Send to agent' })).toBeNull();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy prompt' })); });
  expect(copy).toHaveBeenCalledExactlyOnceWith(PROMPT);
  expect(screen.getByRole('status').textContent).toBe("Copied. Paste it into your agent's chat.");
  // Both copies say so, and are spent: the prompt's own icon and the button.
  expect(screen.getAllByRole('button', { name: 'Copied' }).map(button => [(button as HTMLButtonElement).disabled, Boolean(button.closest('[data-update-prompt]'))]))
    .toEqual([[true, true], [true, false]]);
});

it('sends exactly the prompt where the host takes messages, and closes; a refused send falls back to Copy prompt', async () => {
  const send = vi.fn(async () => {});
  render(<UpdateButton notice={NOTICE} send={send} copy={async () => {}} />);
  await open();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send to agent' })); });
  expect(send).toHaveBeenCalledExactlyOnceWith(PROMPT);
  expect(screen.queryByRole('dialog')).toBeNull();
  cleanup();
  const copy = vi.fn(async () => {});
  render(<UpdateButton notice={NOTICE} send={async () => { throw new Error('refused'); }} copy={copy} />);
  await open();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send to agent' })); });
  expect(screen.getByRole('status').textContent).toBe('It could not be sent to the chat. Copy the prompt instead.');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy prompt' })); });
  expect(copy).toHaveBeenCalledExactlyOnceWith(PROMPT);
});

it('is reached and closed from the keyboard: Enter or Space opens it, Escape closes it and gives focus back', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  render(<UpdateButton notice={NOTICE} copy={async () => {}} />);
  const user = userEvent.setup();
  const button = screen.getByRole('button', { name: 'Update available: v0.11.12' });
  await user.tab();
  expect(document.activeElement).toBe(button);
  await user.keyboard('{Enter}');
  expect(await screen.findByRole('dialog')).toBeTruthy();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(button);
  await user.keyboard(' ');
  expect(await screen.findByRole('dialog')).toBeTruthy();
});

it('reads in the locale around it; the prompt stays English', async () => {
  render(<I18nProvider locale="ja"><UpdateButton notice={NOTICE} copy={async () => {}} /></I18nProvider>);
  await userEvent.setup().click(screen.getByRole('button', { name: 'アップデートがあります: v0.11.12' }));
  const card = await screen.findByRole('dialog');
  expect(card.textContent).toContain('text-to-cad プラグインの新しいバージョンがあります');
  expect(card.querySelector('[data-update-prompt]')?.textContent).toBe(PROMPT);
});
