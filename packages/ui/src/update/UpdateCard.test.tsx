import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { UpdateCard, useUpdateNotice, type UpdateCall } from './index.js';

const NOTICE = { latest: '0.9.0', version: '0.8.1', text: 'text-to-cad 0.9.0 is available (you have 0.8.1)',
  prompt: 'Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad' };

function Host({ call, send, copy = vi.fn(async () => {}) }: { call: UpdateCall; send?: (prompt: string) => Promise<void>; copy?: (prompt: string) => Promise<void> }) {
  const { notice, answer, close } = useUpdateNotice(call);
  return notice ? <UpdateCard notice={notice} send={send} copy={copy} onAnswer={answer} onClose={close} /> : <p>No notice</p>;
}

afterEach(cleanup);

it('sends the prompt to the chat where the host can, and keeps that as the answer', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const send = vi.fn(async () => {});
  render(<Host call={call} send={send} />);
  expect((await screen.findByRole('dialog')).textContent).toContain('text-to-cad 0.9.0 is available (you have 0.8.1). Your agent can update it:');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Send to agent' })); });
  expect(send).toHaveBeenCalledWith(NOTICE.prompt);
  expect(call).toHaveBeenLastCalledWith('0.9.0');
  expect(screen.getByText('No notice')).toBeTruthy();
});

it('copies the prompt where nothing can send it, or once sending fails', async () => {
  const call = vi.fn<UpdateCall>(async () => ({ notice: NOTICE }));
  const copy = vi.fn(async () => {});
  render(<Host call={call} send={async () => { throw new Error('refused'); }} copy={copy} />);
  const sendButton = await screen.findByRole('button', { name: 'Send to agent' });
  await act(async () => { fireEvent.click(sendButton); });
  expect(screen.getByRole('status').textContent).toBe('It could not be sent to the chat. Copy the prompt instead.');
  expect(call).toHaveBeenCalledTimes(1); // not sent: no answer yet
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy prompt' })); });
  expect(copy).toHaveBeenCalledWith(NOTICE.prompt);
  expect(call).toHaveBeenLastCalledWith('0.9.0');
  expect(screen.getByRole('status').textContent).toBe("Copied. Paste it into your agent's chat.");
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.getByText('No notice')).toBeTruthy();
  expect(call).toHaveBeenCalledTimes(2); // answered once
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
