import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { UpdateButton, useUpdateNotice, type UpdateCall } from './index.js';

const NOTICE = { latest: '0.9.0', version: '0.8.1', text: 'A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)',
  prompt: 'Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad',
  instructions: 'https://www.texttocad.dev/install' };

function Host({ call, send, copy = vi.fn(async () => {}), onLink = vi.fn() }: {
  call: UpdateCall; send?: (prompt: string) => Promise<void>; copy?: (prompt: string) => Promise<void>; onLink?: (url: string) => void;
}) {
  const notice = useUpdateNotice(call);
  return notice ? <UpdateButton notice={notice} send={send} copy={copy} onLink={onLink} /> : <p>No notice</p>;
}

async function openCard() {
  fireEvent.click(await screen.findByRole('button', { name: 'Update to 0.9.0' }));
  return screen.findByRole('dialog', { name: 'Update available' });
}

afterEach(cleanup);

it('is a blue button that opens the card; Send to agent posts the prompt and closes it, and the button stays', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const send = vi.fn(async () => {});
  render(<Host call={call} send={send} />);
  expect((await screen.findByRole('button', { name: 'Update to 0.9.0' })).className).toContain('bg-blue-500');
  const card = await openCard();
  expect(card.textContent).toContain('A new version of text-to-cad is available. Send a message to your agent asking it to update to the latest version:');
  const sendButton = screen.getByRole('button', { name: 'Send to agent' });
  expect(sendButton.querySelector('svg')).toBeTruthy(); // its icon first, as Quick Edit's
  await act(async () => { fireEvent.click(sendButton); });
  expect(send).toHaveBeenCalledWith(NOTICE.prompt);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('button', { name: 'Update to 0.9.0' })).toBeTruthy();
  expect(call).toHaveBeenCalledTimes(1); // a read, and no answer to keep
});

it('the prompt has a copy icon in its corner: it copies, and the card stays with a tick beside Send to agent', async () => {
  const send = vi.fn(async () => {});
  const copy = vi.fn(async () => {});
  render(<Host call={async () => ({ notice: NOTICE })} send={send} copy={copy} />);
  await openCard();
  const icon = screen.getByRole('button', { name: 'Copy' });
  expect(icon.textContent).toBe('');
  expect(icon.closest('[data-update-prompt]')?.textContent).toBe(NOTICE.prompt);
  expect(screen.queryByRole('button', { name: 'Copy prompt' })).toBeNull();
  await act(async () => { fireEvent.click(icon); });
  expect(copy).toHaveBeenCalledWith(NOTICE.prompt);
  expect(screen.getByRole('status').textContent).toBe("Copied. Paste it into your agent's chat.");
  expect((screen.getByRole('button', { name: 'Copied' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Send to agent' }) as HTMLButtonElement).disabled).toBe(false);
  expect(send).not.toHaveBeenCalled();
});

it('copies the prompt where nothing can send it, or once sending fails', async () => {
  const copy = vi.fn(async () => {});
  render(<Host call={async () => ({ notice: NOTICE })} send={async () => { throw new Error('refused'); }} copy={copy} />);
  await openCard();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send to agent' })); });
  expect(screen.getByRole('status').textContent).toBe('It could not be sent to the chat. Copy the prompt instead.');
  // The card's button copies now, in words, and the prompt keeps its corner icon.
  const copyButton = screen.getByRole('button', { name: 'Copy prompt' });
  expect([copyButton.querySelector('svg') !== null, copyButton.textContent, copyButton.closest('[data-update-prompt]')])
    .toEqual([true, 'Copy prompt', null]);
  expect(screen.getByRole('button', { name: 'Copy' }).closest('[data-update-prompt]')).not.toBeNull();
  await act(async () => { fireEvent.click(copyButton); });
  expect(copy).toHaveBeenCalledWith(NOTICE.prompt);
  expect(screen.getByRole('status').textContent).toBe("Copied. Paste it into your agent's chat.");
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

it('reads the server again when the person comes back, and shows nothing once the install is current', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  render(<Host call={call} />);
  await screen.findByRole('button', { name: 'Update to 0.9.0' });
  call.mockImplementation(async () => ({ notice: null }));
  await act(async () => { fireEvent.focus(window); });
  expect(call).toHaveBeenCalledTimes(2);
  expect(screen.getByText('No notice')).toBeTruthy();
});
