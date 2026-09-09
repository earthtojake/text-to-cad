import { mkdir, open, unlink } from 'node:fs/promises';
import { dirname } from 'node:path';

export type FileLockOptions = {
  timeoutMs?: number;
  retryMs?: number;
};

export type FileLock = {
  release(): Promise<void>;
};

export async function acquireFileLock(
  lockPath: string,
  options: FileLockOptions = {}
): Promise<FileLock> {
  const timeoutMs = options.timeoutMs ?? 5_000;
  const retryMs = options.retryMs ?? 50;
  const deadline = Date.now() + timeoutMs;

  await mkdir(dirname(lockPath), { recursive: true, mode: 0o700 });

  while (true) {
    try {
      const handle = await open(lockPath, 'wx');
      await handle.writeFile(`${process.pid}\n`);
      await handle.close();
      return {
        async release() {
          await unlink(lockPath).catch(() => {});
        },
      };
    } catch (error) {
      if (!isAlreadyExistsError(error) || Date.now() >= deadline) {
        throw new Error(`Timed out acquiring workspace daemon lock: ${lockPath}`);
      }
      await sleep(retryMs);
    }
  }
}

export async function withFileLock<T>(
  lockPath: string,
  fn: () => Promise<T>,
  options: FileLockOptions = {}
): Promise<T> {
  const lock = await acquireFileLock(lockPath, options);
  try {
    return await fn();
  } finally {
    await lock.release();
  }
}

function isAlreadyExistsError(error: unknown): boolean {
  return (
    error instanceof Error && 'code' in error && (error as NodeJS.ErrnoException).code === 'EEXIST'
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
