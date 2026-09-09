import { dirname } from 'node:path';
import type { AcpFs } from '#runtimes/acp/api/transport';

/** Read a UTF-8 file via an AcpFs adapter, wrapping errors with the file path. */
export async function readTextFile(fs: AcpFs, path: string): Promise<string> {
  try {
    return await fs.readFile(path, 'utf8');
  } catch (err) {
    throw new Error(
      `readTextFile failed for ${path}: ${err instanceof Error ? err.message : String(err)}`
    );
  }
}

/** Create parent directories and write a UTF-8 file via an AcpFs adapter. */
export async function writeTextFile(fs: AcpFs, path: string, content: string): Promise<void> {
  await fs.mkdir(dirname(path), { recursive: true });
  await fs.writeFile(path, content, 'utf8');
}
