import { realpathSync } from 'node:fs';
import path from 'node:path';

export function realpathOrResolve(filePath: string): string {
  try {
    return realpathSync.native(filePath);
  } catch {
    try {
      return realpathSync(filePath);
    } catch {
      return path.resolve(filePath);
    }
  }
}
