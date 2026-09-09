import { StringDecoder } from 'node:string_decoder';

export type RipgrepJsonFramerEvent =
  | Readonly<{
      type: 'line';
      line: string;
    }>
  | Readonly<{
      type: 'oversized-record';
      maxRecordBytes: number;
      observedRecordBytes: number;
    }>;

export type RipgrepJsonFramerOptions = Readonly<{
  maxRecordBytes: number;
}>;

/**
 * Incrementally frames ripgrep's UTF-8 JSON-lines output.
 *
 * The framer retains at most `maxRecordBytes` of one unfinished record. Once a
 * record crosses that bound, it emits one `oversized-record` event and discards
 * bytes through the next newline. A following record is then framed normally.
 */
export class RipgrepJsonFramer {
  private readonly maxRecordBytes: number;
  private recordBuffer = Buffer.alloc(0);
  private recordByteLength = 0;
  private discardingOversizedRecord = false;
  private finished = false;

  constructor(options: RipgrepJsonFramerOptions) {
    if (!Number.isSafeInteger(options.maxRecordBytes) || options.maxRecordBytes <= 0) {
      throw new RangeError('maxRecordBytes must be a positive safe integer');
    }
    this.maxRecordBytes = options.maxRecordBytes;
  }

  push(chunk: Buffer): RipgrepJsonFramerEvent[] {
    if (this.finished) {
      throw new Error('Cannot push ripgrep output after the framer has finished');
    }

    const events: RipgrepJsonFramerEvent[] = [];
    this.pushBuffer(chunk, events);
    return events;
  }

  finish(): RipgrepJsonFramerEvent[] {
    if (this.finished) return [];

    const events: RipgrepJsonFramerEvent[] = [];
    this.finished = true;

    if (this.discardingOversizedRecord) {
      this.discardingOversizedRecord = false;
      this.recordByteLength = 0;
      return events;
    }
    if (this.recordByteLength > 0) {
      events.push({ type: 'line', line: this.decodeRecord() });
      this.recordByteLength = 0;
    }
    return events;
  }

  private pushBuffer(chunk: Buffer, events: RipgrepJsonFramerEvent[]): void {
    let offset = 0;
    while (offset < chunk.length) {
      const newline = chunk.indexOf(0x0a, offset);
      const segmentEnd = newline < 0 ? chunk.length : newline;
      const segment = chunk.subarray(offset, segmentEnd);

      if (!this.discardingOversizedRecord) {
        const observedRecordBytes = this.recordByteLength + segment.length;
        if (observedRecordBytes > this.maxRecordBytes) {
          this.discardingOversizedRecord = true;
          this.recordByteLength = 0;
          events.push({
            type: 'oversized-record',
            maxRecordBytes: this.maxRecordBytes,
            observedRecordBytes,
          });
        } else if (newline >= 0) {
          this.append(segment);
          events.push({ type: 'line', line: this.decodeRecord() });
          this.recordByteLength = 0;
        } else {
          this.append(segment);
        }
      }

      if (newline < 0) return;
      if (this.discardingOversizedRecord) {
        this.discardingOversizedRecord = false;
        this.recordByteLength = 0;
      }
      offset = newline + 1;
    }
  }

  private append(chunk: Buffer): void {
    if (chunk.length === 0) return;

    const requiredCapacity = this.recordByteLength + chunk.length;
    if (this.recordBuffer.length < requiredCapacity) {
      const doubledCapacity = this.recordBuffer.length === 0 ? 4_096 : this.recordBuffer.length * 2;
      const nextCapacity = Math.min(
        this.maxRecordBytes,
        Math.max(requiredCapacity, doubledCapacity)
      );
      const nextBuffer = Buffer.allocUnsafe(nextCapacity);
      this.recordBuffer.copy(nextBuffer, 0, 0, this.recordByteLength);
      this.recordBuffer = nextBuffer;
    }

    chunk.copy(this.recordBuffer, this.recordByteLength);
    this.recordByteLength = requiredCapacity;
  }

  private decodeRecord(): string {
    const decoder = new StringDecoder('utf8');
    return decoder.end(this.recordBuffer.subarray(0, this.recordByteLength));
  }
}
