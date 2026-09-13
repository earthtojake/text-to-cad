export const MAX_STATUS_FILES = 10_000;

export class TooManyFilesChangedError extends Error {
  override readonly name = 'TooManyFilesChangedError';

  constructor() {
    super('Too many changed files');
  }
}

export type FileStatus = {
  x: string;
  y: string;
  rename?: string;
  path: string;
  headOid?: string;
  indexOid?: string;
};

export class StatusParser {
  private lastRaw = '';
  private result: FileStatus[] = [];
  tooManyFiles = false;

  get status(): FileStatus[] {
    return this.result;
  }

  update(chunk: string): void {
    let raw = this.lastRaw + chunk;
    let index = 0;
    let nextIndex: number | undefined;

    while ((nextIndex = this.parseEntry(raw, index)) !== undefined) {
      index = nextIndex;
      if (this.result.length > MAX_STATUS_FILES) {
        this.tooManyFiles = true;
        raw = '';
        index = 0;
        break;
      }
    }

    this.lastRaw = raw.slice(index);
  }

  reset(): void {
    this.lastRaw = '';
    this.result = [];
    this.tooManyFiles = false;
  }

  private parseEntry(raw: string, index: number): number | undefined {
    if (index >= raw.length) return undefined;

    const kind = raw.charAt(index);
    switch (kind) {
      case '1':
        return this.parseOrdinary(raw, index);
      case '2':
        return this.parseRename(raw, index);
      case '?':
        return this.parseUntracked(raw, index);
      case 'u':
        return this.parseUnmerged(raw, index);
      case '!':
        return this.skipSimple(raw, index);
      default:
        return undefined;
    }
  }

  private parseOrdinary(raw: string, index: number): number | undefined {
    const parsed = readNullTerminated(raw, index);
    if (!parsed) return undefined;
    const parts = splitPrefix(parsed.value, 8);
    if (!parts) return parsed.nextIndex;
    const [_, xy, _sub, _mH, _mI, _mW, headOid, indexOid, filePath] = parts;
    this.push({
      ...parseXY(xy),
      path: filePath,
      headOid,
      indexOid,
    });
    return parsed.nextIndex;
  }

  private parseRename(raw: string, index: number): number | undefined {
    const first = readNullTerminated(raw, index);
    if (!first) return undefined;
    const second = readNullTerminated(raw, first.nextIndex);
    if (!second) return undefined;
    const parts = splitPrefix(first.value, 9);
    if (!parts) return second.nextIndex;
    const [_, xy, _sub, _mH, _mI, _mW, headOid, indexOid, _score, filePath] = parts;
    this.push({
      ...parseXY(xy),
      rename: filePath,
      path: second.value,
      headOid,
      indexOid,
    });
    return second.nextIndex;
  }

  private parseUntracked(raw: string, index: number): number | undefined {
    const parsed = readNullTerminated(raw, index);
    if (!parsed) return undefined;
    const filePath = parsed.value.startsWith('? ') ? parsed.value.slice(2) : parsed.value;
    this.push({ x: '?', y: '?', path: filePath });
    return parsed.nextIndex;
  }

  private parseUnmerged(raw: string, index: number): number | undefined {
    const parsed = readNullTerminated(raw, index);
    if (!parsed) return undefined;
    const parts = splitPrefix(parsed.value, 10);
    if (!parts) return parsed.nextIndex;
    const [_, xy, _sub, _m1, _m2, _m3, _mW, _h1, _h2, _h3, filePath] = parts;
    this.push({ ...parseXY(xy), path: filePath });
    return parsed.nextIndex;
  }

  private skipSimple(raw: string, index: number): number | undefined {
    return readNullTerminated(raw, index)?.nextIndex;
  }

  private push(status: FileStatus): void {
    const filePath = status.rename ?? status.path;
    if (filePath.length > 0 && filePath[filePath.length - 1] !== '/') {
      this.result.push(status);
    }
  }
}

function readNullTerminated(
  raw: string,
  index: number
): { value: string; nextIndex: number } | undefined {
  const end = raw.indexOf('\0', index);
  if (end === -1) return undefined;
  return { value: raw.substring(index, end), nextIndex: end + 1 };
}

function splitPrefix(value: string, fieldCount: number): string[] | undefined {
  const fields: string[] = [];
  let index = 0;
  for (let i = 0; i < fieldCount; i++) {
    const nextSpace = value.indexOf(' ', index);
    if (nextSpace === -1) return undefined;
    fields.push(value.slice(index, nextSpace));
    index = nextSpace + 1;
  }
  fields.push(value.slice(index));
  return fields;
}

function parseXY(xy: string): { x: string; y: string } {
  return {
    x: normalizeStatusChar(xy.charAt(0)),
    y: normalizeStatusChar(xy.charAt(1)),
  };
}

function normalizeStatusChar(value: string): string {
  return value === '.' ? ' ' : value;
}
