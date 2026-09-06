const WORKTREE_POOL_HASH_LENGTH = 8;
const SHA256_INITIAL = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
] as const;
const SHA256_ROUND = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
] as const;

export type CompileWorktreePayloadInput = {
  repoPath: string;
  worktreeRoot: string;
  branchName: string;
  preservePatterns?: readonly string[];
};

export type CompiledWorktreePayload = {
  worktreePath: string;
  branchName: string;
  preservePatterns: string[];
};

/**
 * The per-repository worktree pool under a worktree root:
 * `<root>/<repo-basename>-<sha256(repoPath) first 8 hex>`. Portable and pure —
 * execution (worktree payload compilation, placement) and renderer previews
 * (settings page, create-task destination) must all derive pools through this
 * one definition.
 */
export function deriveWorktreePoolPath(input: { worktreeRoot: string; repoPath: string }): string {
  const separator = pathSeparatorFor(input.worktreeRoot);
  const repositoryName = basename(input.repoPath, separator) || 'repository';
  const repositoryHash = sha256Hex(input.repoPath).slice(0, WORKTREE_POOL_HASH_LENGTH);
  return joinPath(input.worktreeRoot, separator, `${repositoryName}-${repositoryHash}`);
}

export function compileWorktreePayload(
  input: CompileWorktreePayloadInput
): CompiledWorktreePayload {
  const separator = pathSeparatorFor(input.worktreeRoot);
  const worktreePoolPath = deriveWorktreePoolPath(input);

  return {
    worktreePath: joinPath(worktreePoolPath, separator, sanitizeBranchName(input.branchName)),
    branchName: input.branchName,
    preservePatterns: [...(input.preservePatterns ?? [])],
  };
}

function sanitizeBranchName(branchName: string): string {
  const sanitized = branchName.replace(/[^a-zA-Z0-9._-]/g, '-');
  if (!sanitized || sanitized === '.' || sanitized === '..') return 'branch';
  if (/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/iu.test(sanitized)) {
    return `${sanitized}-branch`;
  }
  return sanitized;
}

function pathSeparatorFor(absolutePath: string): '/' | '\\' {
  return /^[a-zA-Z]:[\\/]/u.test(absolutePath) || absolutePath.startsWith('\\\\') ? '\\' : '/';
}

function basename(filePath: string, separator: '/' | '\\'): string {
  const separators = separator === '\\' ? /[\\/]+/u : /\/+/u;
  return filePath.split(separators).filter(Boolean).at(-1) ?? '';
}

function joinPath(base: string, separator: '/' | '\\', segment: string): string {
  const trailingSeparators = separator === '\\' ? /[\\/]+$/u : /\/+$/u;
  const normalizedBase = base.replace(trailingSeparators, '');
  return normalizedBase ? `${normalizedBase}${separator}${segment}` : `${separator}${segment}`;
}

function sha256Hex(input: string): string {
  const bytes = new TextEncoder().encode(input);
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const message = new Uint8Array(paddedLength);
  message.set(bytes);
  message[bytes.length] = 0x80;
  const view = new DataView(message.buffer);
  const bitLength = bytes.length * 8;
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x1_0000_0000));
  view.setUint32(paddedLength - 4, bitLength >>> 0);

  const hash: number[] = [...SHA256_INITIAL];
  const words = new Uint32Array(64);
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4);
    }
    for (let index = 16; index < 64; index += 1) {
      const previous15 = words[index - 15]!;
      const previous2 = words[index - 2]!;
      const sigma0 = rotateRight(previous15, 7) ^ rotateRight(previous15, 18) ^ (previous15 >>> 3);
      const sigma1 = rotateRight(previous2, 17) ^ rotateRight(previous2, 19) ^ (previous2 >>> 10);
      words[index] = (words[index - 16]! + sigma0 + words[index - 7]! + sigma1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e!, 6) ^ rotateRight(e!, 11) ^ rotateRight(e!, 25);
      const choice = (e! & f!) ^ (~e! & g!);
      const temporary1 = (h! + sum1 + choice + SHA256_ROUND[index]! + words[index]!) >>> 0;
      const sum0 = rotateRight(a!, 2) ^ rotateRight(a!, 13) ^ rotateRight(a!, 22);
      const majority = (a! & b!) ^ (a! & c!) ^ (b! & c!);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d! + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }
    hash[0] = (hash[0]! + a!) >>> 0;
    hash[1] = (hash[1]! + b!) >>> 0;
    hash[2] = (hash[2]! + c!) >>> 0;
    hash[3] = (hash[3]! + d!) >>> 0;
    hash[4] = (hash[4]! + e!) >>> 0;
    hash[5] = (hash[5]! + f!) >>> 0;
    hash[6] = (hash[6]! + g!) >>> 0;
    hash[7] = (hash[7]! + h!) >>> 0;
  }
  return hash.map((value) => value.toString(16).padStart(8, '0')).join('');
}

function rotateRight(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}
