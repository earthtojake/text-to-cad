import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { err, ok, type Result } from '@emdash/shared';

export type PidFileError = {
  type: 'missing' | 'invalid' | 'io';
  message: string;
};

export type ProcessSignal = NodeJS.Signals | 0;

export type ProcessSignaler = (pid: number, signal?: ProcessSignal) => boolean;

export async function writePidFile(pidPath: string, pid = process.pid): Promise<void> {
  await mkdir(dirname(pidPath), { recursive: true, mode: 0o700 });
  await writeFile(pidPath, `${pid}\n`, { mode: 0o600 });
}

export async function readPidFile(pidPath: string): Promise<Result<number, PidFileError>> {
  try {
    const raw = await readFile(pidPath, 'utf8');
    const pid = Number(raw.trim());
    if (!Number.isInteger(pid) || pid <= 0) {
      return err({
        type: 'invalid',
        message: `Invalid workspace daemon pid file: ${pidPath}`,
      });
    }
    return ok(pid);
  } catch (error) {
    return err({
      type: isMissingFileError(error) ? 'missing' : 'io',
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

export async function removePidFile(pidPath: string): Promise<void> {
  await unlink(pidPath).catch((error: unknown) => {
    if (!isMissingFileError(error)) throw error;
  });
}

export function isProcessAlive(pid: number, signaler: ProcessSignaler = process.kill): boolean {
  try {
    signaler(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function isMissingFileError(error: unknown): boolean {
  return (
    error instanceof Error && 'code' in error && (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}
