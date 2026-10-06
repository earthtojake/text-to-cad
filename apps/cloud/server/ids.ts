import { createHash, randomBytes } from 'node:crypto';

const ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';

/** `length` characters of base62 from the system CSPRNG, without modulo bias. */
export function randomBase62(length: number): string {
  let out = '';
  while (out.length < length) {
    for (const byte of randomBytes(length * 2)) {
      if (byte >= 248) continue; // 248 = 4 * 62: keeps every character equally likely
      out += ALPHABET[byte % 62];
      if (out.length === length) break;
    }
  }
  return out;
}

/** Build, job, user and key ids: 16 base62 characters (~95 bits), unguessable. */
export const newId = () => randomBase62(16);

export const API_KEY_PREFIX = 't2c_';

export const newApiKey = () => API_KEY_PREFIX + randomBase62(40);

export const isBuildId = (value: string) => /^[0-9A-Za-z]{16}$/.test(value);

export function sha256Hex(data: Uint8Array | string): string {
  return createHash('sha256').update(data).digest('hex');
}
