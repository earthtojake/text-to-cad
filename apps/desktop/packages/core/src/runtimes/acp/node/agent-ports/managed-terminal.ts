import { StringDecoder } from 'node:string_decoder';
import type { TerminalState } from '#runtimes/acp/api';
import type { AcpTerminalExit, AcpTerminalProcess } from '#runtimes/acp/api/transport';

/** Default per-terminal output byte cap (4 MB). */
const DEFAULT_OUTPUT_BYTE_LIMIT = 4 * 1024 * 1024;

/**
 * Owns the lifecycle of a single ACP-requested terminal command.
 * Buffers stdout+stderr output up to an optional byte limit (ring-buffer:
 * oldest bytes are discarded first, `truncated` is set to true).
 * Output chunks are decoded incrementally with StringDecoder so multibyte
 * UTF-8 sequences are never split across chunk boundaries.
 */
export class ManagedAgentTerminal {
  private readonly decoder = new StringDecoder('utf8');
  private readonly chunks: string[] = [];
  private bytes = 0;
  private _truncated = false;
  private _exitStatus: AcpTerminalExit | null = null;
  private readonly waiters: ((s: AcpTerminalExit) => void)[] = [];
  private readonly byteLimit: number;
  private readonly proc: AcpTerminalProcess;

  readonly terminalId: string;
  readonly command: string;
  readonly args: string[];
  readonly cwd: string;

  constructor(
    terminalId: string,
    command: string,
    args: string[],
    cwd: string,
    proc: AcpTerminalProcess,
    private readonly onOutput: (chunk: string, truncated: boolean) => void,
    private readonly onExitCb: (status: AcpTerminalExit) => void,
    byteLimit?: number | null
  ) {
    this.terminalId = terminalId;
    this.command = command;
    this.args = args;
    this.cwd = cwd;
    this.proc = proc;
    this.byteLimit = byteLimit ?? DEFAULT_OUTPUT_BYTE_LIMIT;

    const handleData = (d: Buffer) => this.append(d);
    proc.stdout.on('data', handleData);
    proc.stderr?.on('data', handleData);

    proc.onExit((status) => {
      this._exitStatus = status;
      this.waiters.splice(0).forEach((w) => w(status));
      this.onExitCb(status);
    });
  }

  private append(d: Buffer): void {
    const text = this.decoder.write(d);
    if (!text) return;

    const incoming = Buffer.byteLength(text, 'utf8');
    this.bytes += incoming;

    if (this.bytes > this.byteLimit) {
      // Discard oldest chunks until we're under the limit.
      this._truncated = true;
      while (this.chunks.length > 0 && this.bytes > this.byteLimit) {
        const oldest = this.chunks.shift()!;
        this.bytes -= Buffer.byteLength(oldest, 'utf8');
      }
    }

    this.chunks.push(text);
    this.onOutput(text, this._truncated);
  }

  /** Lifecycle metadata only — no output text (see terminalStateSchema). */
  snapshot(): TerminalState {
    return {
      terminalId: this.terminalId,
      command: this.command,
      args: this.args,
      cwd: this.cwd,
      truncated: this._truncated,
      exitStatus: this._exitStatus,
    };
  }

  /**
   * The agent-facing ACP `terminal/output` surface: joins the ring buffer on
   * demand. Not used on the client publish path.
   */
  outputSnapshot(): { output: string; truncated: boolean; exitStatus: AcpTerminalExit | null } {
    return {
      output: this.chunks.join(''),
      truncated: this._truncated,
      exitStatus: this._exitStatus,
    };
  }

  waitForExit(): Promise<AcpTerminalExit> {
    if (this._exitStatus) return Promise.resolve(this._exitStatus);
    return new Promise<AcpTerminalExit>((resolve) => this.waiters.push(resolve));
  }

  kill(): void {
    try {
      this.proc.kill('SIGTERM');
    } catch {
      // ignore
    }
  }

  dispose(): void {
    this.kill();
    this.chunks.length = 0;
    this.bytes = 0;
    this.waiters.splice(0);
  }
}
