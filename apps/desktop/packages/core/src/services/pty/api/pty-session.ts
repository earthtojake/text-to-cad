import type { LiveLogSourceOptions } from '@emdash/wire/live';
import { LiveLogSource } from '@emdash/wire/live';
import type { PtyExitInfo, PtyProcess, PtySpawnSpec } from './types';

export interface PtySessionOptions {
  log?: LiveLogSourceOptions;
  output?: LiveLogSource;
  onProcess?: (process: PtyProcess) => void;
  onData?: (chunk: string) => void;
  onExit?: (info: PtyExitInfo) => void;
  onStateChange?: () => void;
}

export class PtySession {
  readonly output: LiveLogSource;
  readonly startedAt = Date.now();
  private disposed = false;
  private exitInfo: PtyExitInfo | null = null;

  constructor(
    readonly key: string,
    readonly spec: PtySpawnSpec,
    private readonly process: PtyProcess,
    private readonly options: PtySessionOptions = {}
  ) {
    this.output = options.output ?? new LiveLogSource(options.log);
    this.process.onData((chunk) => {
      this.output.append(chunk);
      this.options.onData?.(chunk);
      this.options.onStateChange?.();
    });
    this.process.onExit((info) => {
      this.exitInfo = normalizeExitInfo(info);
      this.options.onExit?.(this.exitInfo);
      this.options.onStateChange?.();
    });
  }

  get exitStatus(): PtyExitInfo | null {
    return this.exitInfo;
  }

  get exited(): boolean {
    return this.exitInfo !== null;
  }

  write(data: string): void {
    if (this.disposed || this.exited) return;
    this.process.write(data);
  }

  resize(cols: number, rows: number): void {
    if (this.disposed || this.exited) return;
    this.process.resize(cols, rows);
  }

  kill(): void {
    if (this.disposed) return;
    this.process.kill();
  }

  dispose(): void {
    if (this.disposed) return;
    this.kill();
    this.disposed = true;
  }

  getPid(): number | undefined {
    return this.process.getPid?.();
  }
}

function normalizeExitInfo(info: PtyExitInfo): PtyExitInfo {
  return {
    exitCode: info.exitCode ?? null,
    signal: info.signal ?? null,
  };
}
