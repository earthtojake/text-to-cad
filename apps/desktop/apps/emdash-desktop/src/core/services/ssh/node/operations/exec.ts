import type { Client, ClientChannel } from 'ssh2';
import type { SshExecOptions, SshExecResult } from '@core/primitives/ssh/api/node/ssh-client-proxy';

export class SshExecTimeoutError extends Error {
  readonly name = 'SshExecTimeoutError';

  constructor(readonly timeoutMs: number) {
    super(`SSH command timed out after ${timeoutMs}ms`);
  }
}

export class SshExecOutputOverflowError extends Error {
  readonly name = 'SshExecOutputOverflowError';

  constructor(
    readonly stream: 'stdout' | 'stderr',
    readonly limitBytes: number
  ) {
    super(`SSH command ${stream} exceeded the ${limitBytes}-byte limit`);
  }
}

const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024;

export function execOnClient(
  client: Client,
  command: string,
  options: SshExecOptions = {}
): Promise<SshExecResult> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxStdoutBytes = options.maxStdoutBytes ?? DEFAULT_MAX_OUTPUT_BYTES;
  const maxStderrBytes = options.maxStderrBytes ?? DEFAULT_MAX_OUTPUT_BYTES;

  return new Promise((resolve, reject) => {
    let channel: ClientChannel | undefined;
    let settled = false;
    let stdoutBytes = 0;
    let stderrBytes = 0;
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];

    const cleanupClient = () => {
      client.off('close', handleConnectionClose);
      client.off('end', handleConnectionClose);
      client.off('error', handleConnectionError);
    };
    const cleanup = () => {
      clearTimeout(timeout);
      options.signal?.removeEventListener('abort', handleAbort);
      cleanupClient();
      channel?.off('error', handleChannelError);
      channel?.off('close', handleChannelClose);
      channel?.off('data', handleStdout);
      channel?.stderr.off('data', handleStderr);
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      channel?.destroy();
      reject(error);
    };
    const handleConnectionClose = () => {
      fail(new Error('SSH connection closed while running command'));
    };
    const handleConnectionError = (error: Error) => fail(error);
    const handleChannelError = (error: Error) => fail(error);
    const handleAbort = () => fail(abortError(options.signal));
    const handleStdout = (chunk: Buffer | string) => {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      stdoutBytes += buffer.byteLength;
      if (stdoutBytes > maxStdoutBytes) {
        fail(new SshExecOutputOverflowError('stdout', maxStdoutBytes));
        return;
      }
      stdout.push(buffer);
    };
    const handleStderr = (chunk: Buffer | string) => {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      stderrBytes += buffer.byteLength;
      if (stderrBytes > maxStderrBytes) {
        fail(new SshExecOutputOverflowError('stderr', maxStderrBytes));
        return;
      }
      stderr.push(buffer);
    };
    const handleChannelClose = (code: number | undefined) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve({
        stdout: Buffer.concat(stdout).toString('utf8'),
        stderr: Buffer.concat(stderr).toString('utf8'),
        exitCode: code ?? 0,
      });
    };

    const timeout = setTimeout(() => fail(new SshExecTimeoutError(timeoutMs)), timeoutMs);
    timeout.unref?.();

    if (options.signal?.aborted) {
      fail(abortError(options.signal));
      return;
    }
    options.signal?.addEventListener('abort', handleAbort, { once: true });
    client.once('close', handleConnectionClose);
    client.once('end', handleConnectionClose);
    client.once('error', handleConnectionError);

    try {
      client.exec(command, (error, nextChannel) => {
        if (settled) {
          nextChannel?.destroy();
          return;
        }
        if (error) {
          fail(error);
          return;
        }
        channel = nextChannel;
        channel.on('data', handleStdout);
        channel.stderr.on('data', handleStderr);
        channel.once('error', handleChannelError);
        channel.once('close', handleChannelClose);
      });
    } catch (error) {
      fail(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

function abortError(signal: AbortSignal | undefined): Error {
  const reason = signal?.reason;
  if (reason instanceof Error) return reason;
  return new DOMException(
    reason === undefined ? 'The operation was aborted' : String(reason),
    'AbortError'
  );
}
