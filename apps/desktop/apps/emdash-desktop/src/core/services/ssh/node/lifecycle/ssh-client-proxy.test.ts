import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import type { Client, ClientChannel } from 'ssh2';
import { describe, expect, it, vi } from 'vitest';
import { SshClientProxy } from './ssh-client-proxy';

describe('SshClientProxy', () => {
  it('throws when the SSH connection is unavailable', () => {
    const proxy = new SshClientProxy('ssh-1');

    expect(() => proxy.client).toThrow('SSH connection is not available');
    expect(proxy.isConnected).toBe(false);
  });

  it('exposes the current client while connected', () => {
    const client = {} as Client;
    const proxy = new SshClientProxy('ssh-1');

    proxy.update(client);

    expect(proxy.client).toBe(client);
    expect(proxy.isConnected).toBe(true);
  });

  it('clears the current client on invalidate', () => {
    const proxy = new SshClientProxy('ssh-1');
    proxy.update({} as Client);

    proxy.invalidate();

    expect(proxy.isConnected).toBe(false);
    expect(() => proxy.client).toThrow('SSH connection is not available');
  });

  it('opens a streamlocal channel through the current client', async () => {
    const channel = new PassThrough() as unknown as ClientChannel;
    const opensshForwardOutStreamLocal = vi.fn(
      (_socketPath: string, callback: (error: Error | undefined, value: ClientChannel) => void) => {
        callback(undefined, channel);
      }
    );
    const proxy = new SshClientProxy('ssh-1');
    proxy.update(
      Object.assign(new EventEmitter(), {
        openssh_forwardOutStreamLocal: opensshForwardOutStreamLocal,
      }) as unknown as Client
    );

    await expect(proxy.forwardOutStreamLocal('/run/workspace.sock')).resolves.toBe(channel);
    expect(opensshForwardOutStreamLocal).toHaveBeenCalledWith(
      '/run/workspace.sock',
      expect.any(Function)
    );
  });

  it('rejects a failed streamlocal request', async () => {
    const error = new Error('administratively prohibited');
    const proxy = new SshClientProxy('ssh-1');
    proxy.update(
      Object.assign(new EventEmitter(), {
        openssh_forwardOutStreamLocal: (_socketPath: string, callback: (error: Error) => void) =>
          callback(error),
      }) as unknown as Client
    );

    await expect(proxy.forwardOutStreamLocal('/run/workspace.sock')).rejects.toBe(error);
  });

  it('rejects a pending streamlocal request when the SSH connection closes', async () => {
    const client = Object.assign(new EventEmitter(), {
      openssh_forwardOutStreamLocal: vi.fn(),
    });
    const proxy = new SshClientProxy('ssh-1');
    proxy.update(client as unknown as Client);

    const pending = proxy.forwardOutStreamLocal('/run/workspace.sock');
    client.emit('close');

    await expect(pending).rejects.toThrow(
      'SSH connection closed while opening streamlocal channel'
    );
    expect(client.listenerCount('close')).toBe(0);
    expect(client.listenerCount('end')).toBe(0);
  });

  it('destroys a channel delivered after its SSH connection closed', async () => {
    let callback: ((error: Error | undefined, channel: ClientChannel) => void) | undefined;
    const client = Object.assign(new EventEmitter(), {
      openssh_forwardOutStreamLocal: vi.fn(
        (_socketPath: string, next: (error: Error | undefined, channel: ClientChannel) => void) => {
          callback = next;
        }
      ),
    });
    const proxy = new SshClientProxy('ssh-1');
    proxy.update(client as unknown as Client);
    const channel = Object.assign(new PassThrough(), { destroy: vi.fn() });

    const pending = proxy.forwardOutStreamLocal('/run/workspace.sock');
    client.emit('close');
    await expect(pending).rejects.toThrow(
      'SSH connection closed while opening streamlocal channel'
    );
    callback?.(undefined, channel as unknown as ClientChannel);

    expect(channel.destroy).toHaveBeenCalledOnce();
  });

  it('formats structured commands for the remote POSIX shell', async () => {
    const channel = Object.assign(new PassThrough(), { stderr: new PassThrough() });
    const exec = vi.fn(
      (_command: string, callback: (error: Error | undefined, value: ClientChannel) => void) =>
        callback(undefined, channel as unknown as ClientChannel)
    );
    const proxy = new SshClientProxy('ssh-1');
    proxy.update(Object.assign(new EventEmitter(), { exec }) as unknown as Client);

    const pending = proxy.exec({
      command: '/opt/Emdash Server/bin/emdash',
      args: ['start', '--socket', '/tmp/emdash socket'],
    });
    channel.emit('close', 0);

    await expect(pending).resolves.toMatchObject({ exitCode: 0 });
    expect(exec).toHaveBeenCalledWith(
      "'/opt/Emdash Server/bin/emdash' start --socket '/tmp/emdash socket'",
      expect.any(Function)
    );
  });

  it('passes explicit scripts to the remote shell unchanged', async () => {
    const channel = Object.assign(new PassThrough(), { stderr: new PassThrough() });
    const exec = vi.fn(
      (_command: string, callback: (error: Error | undefined, value: ClientChannel) => void) =>
        callback(undefined, channel as unknown as ClientChannel)
    );
    const proxy = new SshClientProxy('ssh-1');
    proxy.update(Object.assign(new EventEmitter(), { exec }) as unknown as Client);

    const script = 'printf \'%s\\n\' "$HOME"; uname -s';
    const pending = proxy.execScript(script);
    channel.emit('close', 0);

    await expect(pending).resolves.toMatchObject({ exitCode: 0 });
    expect(exec).toHaveBeenCalledWith(script, expect.any(Function));
  });
});
