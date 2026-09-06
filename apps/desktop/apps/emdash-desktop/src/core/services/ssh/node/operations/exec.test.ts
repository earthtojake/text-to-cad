import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import type { Client, ClientChannel } from 'ssh2';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { execOnClient, SshExecOutputOverflowError, SshExecTimeoutError } from './exec';

describe('execOnClient', () => {
  afterEach(() => vi.useRealTimers());

  it('collects bounded output and returns the exit code', async () => {
    const { client, channel } = fakeExecClient();
    const result = execOnClient(client, 'printf test');

    channel.write('hello');
    (channel.stderr as PassThrough).write('warning');
    channel.emit('close', 7);

    await expect(result).resolves.toEqual({ stdout: 'hello', stderr: 'warning', exitCode: 7 });
  });

  it('rejects and destroys the channel when output exceeds its bound', async () => {
    const { client, channel } = fakeExecClient();
    const destroy = vi.spyOn(channel, 'destroy');
    const result = execOnClient(client, 'large-output', { maxStdoutBytes: 3 });

    channel.write('four');

    await expect(result).rejects.toEqual(new SshExecOutputOverflowError('stdout', 3));
    expect(destroy).toHaveBeenCalledOnce();
  });

  it('rejects on timeout', async () => {
    vi.useFakeTimers();
    const { client, channel } = fakeExecClient();
    const destroy = vi.spyOn(channel, 'destroy');
    const result = execOnClient(client, 'sleep', { timeoutMs: 25 });
    const rejected = expect(result).rejects.toEqual(new SshExecTimeoutError(25));

    await vi.advanceTimersByTimeAsync(25);

    await rejected;
    expect(destroy).toHaveBeenCalledOnce();
  });

  it('rejects when aborted', async () => {
    const { client, channel } = fakeExecClient();
    const controller = new AbortController();
    const result = execOnClient(client, 'sleep', { signal: controller.signal });

    controller.abort(new Error('cancelled by caller'));

    await expect(result).rejects.toThrow('cancelled by caller');
    expect(channel.destroyed).toBe(true);
  });

  it('rejects when the SSH connection closes mid-command', async () => {
    const { client, clientEvents } = fakeExecClient();
    const result = execOnClient(client, 'sleep');

    clientEvents.emit('close');

    await expect(result).rejects.toThrow('SSH connection closed while running command');
    expect(clientEvents.listenerCount('close')).toBe(0);
    expect(clientEvents.listenerCount('end')).toBe(0);
  });
});

function fakeExecClient(): {
  client: Client;
  clientEvents: EventEmitter;
  channel: ClientChannel & PassThrough;
} {
  const stderr = new PassThrough();
  const channel = Object.assign(new PassThrough(), { stderr }) as unknown as ClientChannel &
    PassThrough;
  const clientEvents = Object.assign(new EventEmitter(), {
    exec: vi.fn(
      (_command: string, callback: (error: Error | undefined, value: ClientChannel) => void) =>
        callback(undefined, channel)
    ),
  });
  return { client: clientEvents as unknown as Client, clientEvents, channel };
}
