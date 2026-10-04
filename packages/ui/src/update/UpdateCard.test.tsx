import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { UpdateCard, useUpdateNotice, type UpdateCall } from './index.js';

const NOTICE = { latest: '0.9.0', version: '0.8.1', text: 'A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)',
  prompt: 'Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad',
  instructions: 'https://www.texttocad.dev/install' };

function Host({ call, send, copy = vi.fn(async () => {}), onLink = vi.fn() }: {
  call: UpdateCall; send?: (prompt: string) => Promise<void>; copy?: (prompt: string) => Promise<void>; onLink?: (url: string) => void;
}) {
  const { notice, answer, close } = useUpdateNotice(call);
  return notice ? <UpdateCard notice={notice} send={send} copy={copy} onLink={onLink} onAnswer={answer} onClose={close} /> : <p>No notice</p>;
}

afterEach(cleanup);

it('sends the prompt to the chat where the host can, and keeps that as the answer', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const send = vi.fn(async () => {});
  render(<Host call={call} send={send} />);
  expect((await screen.findByRole('dialog')).textContent).toContain('A new version v0.9.0 of text-to-cad is available (currently on v0.8.1). Ask your agent to update to the latest version, or install manually:');
  expect(screen.getByRole('button', { name: 'Send to agent' }).querySelector('svg')).toBeTruthy(); // its icon first, as Quick Edit's
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send to agent' })); });
  expect(send).toHaveBeenCalledWith(NOTICE.prompt);
  expect(call).toHaveBeenLastCalledWith('0.9.0');
  expect(screen.getByText('No notice')).toBeTruthy();
});

it('beside Send to agent, Copy prompt is an icon: copying is the answer, and Send stays', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const send = vi.fn(async () => {});
  const copy = vi.fn(async () => {});
  render(<Host call={call} send={send} copy={copy} />);
  const icon = await screen.findByRole('button', { name: 'Copy prompt' });
  expect(icon.textContent).toBe('');
  await act(async () => { fireEvent.click(icon); });
  expect(copy).toHaveBeenCalledWith(NOTICE.prompt);
  expect(call).toHaveBeenLastCalledWith('0.9.0');
  expect(screen.getByRole('status').textContent).toBe("Copied. Paste it into your agent's chat.");
  expect((screen.getByRole('button', { name: 'Prompt copied' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Send to agent' }) as HTMLButtonElement).disabled).toBe(false);
  expect(send).not.toHaveBeenCalled();
});

it('copies the prompt where nothing can send it, or once sending fails', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const copy = vi.fn(async () => {});
  render(<Host call={call} send={async () => { throw new Error('refused'); }} copy={copy} />);
  const sendButton = await screen.findByRole('button', { name: 'Send to agent' });
  await act(async () => { fireEvent.click(sendButton); });
  expect(screen.getByRole('status').textContent).toBe('It could not be sent to the chat. Copy the prompt instead.');
  expect(call).toHaveBeenCalledTimes(1); // not sent: no answer yet
  expect(screen.getByRole('button', { name: 'Copy prompt' }).querySelector('svg')).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy prompt' })); });
  expect(copy).toHaveBeenCalledWith(NOTICE.prompt);
  expect(call).toHaveBeenLastCalledWith('0.9.0');
  expect(screen.getByRole('status').textContent).toBe("Copied. Paste it into your agent's chat.");
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.getByText('No notice')).toBeTruthy();
  expect(call).toHaveBeenCalledTimes(2); // answered once
});

it('links to the full install instructions through the host, and following the link is no answer', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const onLink = vi.fn();
  render(<Host call={call} onLink={onLink} />);
  const link = await screen.findByRole('link', { name: 'Manual installation' }) as HTMLAnchorElement;
  expect([link.href, link.target]).toEqual(['https://www.texttocad.dev/install', '_blank']);
  fireEvent.click(link);
  expect(onLink).toHaveBeenCalledWith('https://www.texttocad.dev/install');
  expect(call).toHaveBeenCalledTimes(1); // the read alone: the card stays
  expect(screen.getByRole('dialog')).toBeTruthy();
});

it('closing is an answer, and a read still on its way never brings the card back', async () => {
  let reply!: (value: { notice: typeof NOTICE }) => void;
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  render(<Host call={call} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
  expect(call).toHaveBeenLastCalledWith('0.9.0');
  call.mockImplementation(() => new Promise(resolve => { reply = resolve; }));
  fireEvent.focus(window);
  await act(async () => { reply({ notice: NOTICE }); });
  expect(screen.getByText('No notice')).toBeTruthy();
});
