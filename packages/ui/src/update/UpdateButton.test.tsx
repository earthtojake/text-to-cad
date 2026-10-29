import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { UpdateButton, useUpdateNotice, type UpdateCall, type UpdateNotice, type UpdateStart } from './index.js';

const NOTICE = { latest: '0.9.0', version: '0.8.1', text: 'A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)',
  command: 'curl -fsSL https://texttocad.dev/install.sh | sh',
  prompt: 'Run `curl -fsSL https://texttocad.dev/install.sh | sh` to update text-to-cad to 0.9.0 (on Windows: `irm https://www.texttocad.dev/install.ps1 | iex`)',
  instructions: 'https://www.texttocad.dev/install' };
const auto = (state: NonNullable<UpdateNotice['auto']>['state'], more: Partial<NonNullable<UpdateNotice['auto']>> = {}): UpdateNotice =>
  ({ ...NOTICE, auto: { state, release: '0.9.0', ...more } });

function Host({ call = async () => ({ notice: NOTICE }), initial = NOTICE, send, copy = vi.fn(async () => {}), onLink = vi.fn(), update }: {
  call?: UpdateCall; initial?: UpdateNotice | null; send?: (prompt: string) => Promise<void>; copy?: (text: string) => Promise<void>; onLink?: (url: string) => void;
  update?: UpdateStart;
}) {
  const notice = useUpdateNotice(call, initial);
  return notice ? <UpdateButton notice={notice} send={send} copy={copy} onLink={onLink} update={update} /> : <p>No notice</p>;
}

async function openCard(title = 'Update available') {
  fireEvent.click(await screen.findByRole('button', { name: 'Update to 0.9.0' }));
  return screen.findByRole('dialog', { name: title });
}

/** What the card offers to do: its command block, its button and its link. */
function actions(card: HTMLElement) {
  return [card.querySelector('[data-update-command]') !== null,
    screen.queryByRole('button', { name: /Send to agent|Copy command/ }) !== null,
    screen.queryByRole('link', { name: 'Manual installation' }) !== null];
}

afterEach(() => { cleanup(); vi.useRealTimers(); });

it('is a blue button that opens the card with the install command; Send to agent posts the prompt and closes it, and the button stays', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const send = vi.fn(async () => {});
  render(<Host call={call} send={send} />);
  expect((await screen.findByRole('button', { name: 'Update to 0.9.0' })).className).toContain('bg-blue-500');
  const card = await openCard();
  expect(card.textContent).toContain('A new version of text-to-cad is available. Update with this command:');
  expect(card.querySelector('[data-update-command]')?.textContent).toBe(NOTICE.command);
  const sendButton = screen.getByRole('button', { name: 'Send to agent' });
  expect(sendButton.querySelector('svg')).toBeTruthy(); // its icon first, as Quick Edit's
  await act(async () => { fireEvent.click(sendButton); });
  expect(send).toHaveBeenCalledWith(NOTICE.prompt);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('button', { name: 'Update to 0.9.0' })).toBeTruthy();
  expect(call).toHaveBeenCalledOnce(); // as the card opened; there is no answer to keep
});

it('the command has a copy icon in its corner: it copies the command, and the card stays with a tick beside Send to agent', async () => {
  const send = vi.fn(async () => {});
  const copy = vi.fn(async () => {});
  render(<Host call={async () => ({ notice: NOTICE })} send={send} copy={copy} />);
  await openCard();
  const icon = screen.getByRole('button', { name: 'Copy' });
  expect(icon.textContent).toBe('');
  expect(icon.closest('[data-update-command]')?.textContent).toBe(NOTICE.command);
  expect(screen.queryByRole('button', { name: 'Copy command' })).toBeNull();
  await act(async () => { fireEvent.click(icon); });
  expect(copy).toHaveBeenCalledWith(NOTICE.command);
  expect(screen.getByRole('status').textContent).toBe('Copied. Run it in a terminal.');
  expect((screen.getByRole('button', { name: 'Copied' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Send to agent' }) as HTMLButtonElement).disabled).toBe(false);
  expect(send).not.toHaveBeenCalled();
});

it('copies the command where nothing can send the prompt, or once sending fails', async () => {
  const copy = vi.fn(async () => {});
  render(<Host call={async () => ({ notice: NOTICE })} send={async () => { throw new Error('refused'); }} copy={copy} />);
  await openCard();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send to agent' })); });
  expect(screen.getByRole('status').textContent).toBe('It could not be sent to the chat. Copy the command and run it in a terminal.');
  // The card's button copies now, in words, and the command keeps its corner icon.
  const copyButton = screen.getByRole('button', { name: 'Copy command' });
  expect([copyButton.querySelector('svg') !== null, copyButton.textContent, copyButton.closest('[data-update-command]')])
    .toEqual([true, 'Copy command', null]);
  expect(screen.getByRole('button', { name: 'Copy' }).closest('[data-update-command]')).not.toBeNull();
  await act(async () => { fireEvent.click(copyButton); });
  expect(copy).toHaveBeenCalledWith(NOTICE.command);
  expect(screen.getByRole('status').textContent).toBe('Copied. Run it in a terminal.');
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('links to manual installation through the host, and the card stays', async () => {
  const onLink = vi.fn();
  render(<Host call={async () => ({ notice: NOTICE })} onLink={onLink} />);
  await openCard();
  const link = screen.getByRole('link', { name: 'Manual installation' }) as HTMLAnchorElement;
  expect([link.href, link.target]).toEqual(['https://www.texttocad.dev/install', '_blank']);
  fireEvent.click(link);
  expect(onLink).toHaveBeenCalledWith('https://www.texttocad.dev/install');
  expect(screen.getByRole('dialog', { name: 'Update available' })).toBeTruthy();
});

it('draws with the page from what the host knew, and reads the server again only when the person comes back', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: null }));
  render(<Host call={call} />);
  // The first render: the button is there, and nothing was asked.
  expect(screen.getByRole('button', { name: 'Update to 0.9.0' })).toBeTruthy();
  expect(call).not.toHaveBeenCalled();
  await act(async () => { fireEvent.focus(window); });
  expect(call).toHaveBeenCalledOnce();
  expect(screen.getByText('No notice')).toBeTruthy(); // the install is current now
});

it('a release found after the page started shows once the person comes back', async () => {
  render(<Host initial={null} />);
  expect(screen.getByText('No notice')).toBeTruthy();
  await act(async () => { fireEvent.focus(window); });
  expect(await screen.findByRole('button', { name: 'Update to 0.9.0' })).toBeTruthy();
});

it('an update the engine will install, or is installing on its own, leaves nothing to do: no button', async () => {
  for (const notice of [auto('pending'), auto('updating', { stage: 'downloading' })]) {
    render(<Host initial={notice} call={async () => ({ notice })} update={vi.fn<UpdateStart>()} />);
    expect(screen.queryByRole('button', { name: 'Update to 0.9.0' })).toBeNull();
    cleanup();
  }
});

it('failed: the engine\'s error under its own title, Try again and the link, no command; a run that does not start says why', async () => {
  const notice = auto('failed', { error: 'The download was interrupted.' });
  const update = vi.fn<UpdateStart>(async () => ({ started: false, reason: 'Another update is running.' }));
  render(<Host initial={notice} call={async () => ({ notice })} send={vi.fn(async () => {})} update={update} />);
  const card = await openCard('Update failed');
  expect(card.querySelector('p[id$="-text"]')?.textContent).toBe('The download was interrupted.');
  expect(actions(card)).toEqual([false, false, true]);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Try again/ })); });
  expect(update).toHaveBeenCalledOnce();
  expect(screen.getByRole('status').textContent).toBe('Another update is running.');
  expect((screen.getByRole('button', { name: /Try again/ }) as HTMLButtonElement).disabled).toBe(false);
});

it('Try again follows its run, reading the notice every two seconds while it is under way and never after', async () => {
  let server = auto('failed', { error: 'The download was interrupted.' });
  const call = vi.fn<UpdateCall>(async () => ({ notice: server }));
  const update = vi.fn<UpdateStart>(async () => { server = auto('updating', { stage: 'downloading' }); return { started: true }; });
  render(<Host initial={server} call={call} update={update} />);
  const card = await openCard('Update failed');
  call.mockClear();
  vi.useFakeTimers();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Try again/ })); });
  expect(card.querySelector('p[id$="-text"]')?.textContent).toBe('Downloading v0.9.0…');
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(call).toHaveBeenCalledOnce();
  // The button would hide for an update under way; the card that started it stays.
  expect(screen.getByRole('dialog', { name: 'Updating' })).toBeTruthy();
  server = auto('updating', { stage: 'installing' });
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(card.querySelector('p[id$="-text"]')?.textContent).toBe('Installing v0.9.0…');
  // Failed again: the card says why, and Try again is there once more.
  server = auto('failed', { error: 'The disk is full.' });
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByRole('dialog', { name: 'Update failed' }).querySelector('p[id$="-text"]')?.textContent).toBe('The disk is full.');
  expect(screen.getByRole('button', { name: /Try again/ })).toBeTruthy();
  expect(call).toHaveBeenCalledTimes(3);
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
  expect(call).toHaveBeenCalledTimes(3);
});

it('a run that lands with this page current closes the card', async () => {
  let server: UpdateNotice | null = auto('failed');
  const update = vi.fn<UpdateStart>(async () => { server = auto('updating'); return { started: true }; });
  render(<Host initial={server} call={async () => ({ notice: server })} update={update} />);
  await openCard('Update failed');
  expect(screen.getByRole('dialog').querySelector('p[id$="-text"]')?.textContent).toBe('text-to-cad v0.9.0 could not install itself.');
  vi.useFakeTimers();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Try again/ })); });
  server = null;
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByText('No notice')).toBeTruthy();
});

it('opening the card reads the notice again, and the card shows what it says now', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: auto('failed', { error: 'The disk is full.' }) }));
  render(<Host initial={auto('failed')} call={call} />);
  await openCard('Update failed');
  expect(call).toHaveBeenCalledOnce();
  expect(await screen.findByText('The disk is full.')).toBeTruthy();
});
