import type {
  CreateTerminalRequest,
  CreateTerminalResponse,
  KillTerminalRequest,
  KillTerminalResponse,
  ReleaseTerminalRequest,
  ReleaseTerminalResponse,
  TerminalOutputRequest,
  TerminalOutputResponse,
  WaitForTerminalExitRequest,
  WaitForTerminalExitResponse,
} from '@agentclientprotocol/sdk';
import type { AgentTerminalManager } from './terminal-manager';

export class TerminalPort {
  constructor(private readonly terminals: AgentTerminalManager) {}

  async createTerminal(
    conversationId: string,
    defaultCwd: string,
    params: CreateTerminalRequest
  ): Promise<CreateTerminalResponse> {
    const envRecord = params.env
      ? Object.fromEntries(params.env.map((e) => [e.name, e.value]))
      : {};
    const terminalId = await this.terminals.create(conversationId, {
      command: params.command,
      args: params.args ?? [],
      env: envRecord,
      cwd: params.cwd ?? defaultCwd,
      outputByteLimit: params.outputByteLimit,
    });
    return { terminalId };
  }

  async terminalOutput(params: TerminalOutputRequest): Promise<TerminalOutputResponse> {
    const terminal = this.terminals.get(params.terminalId);
    if (!terminal) throw new Error(`AcpRuntime: terminal not found: ${params.terminalId}`);
    const snap = terminal.outputSnapshot();
    return {
      output: snap.output,
      truncated: snap.truncated,
      exitStatus: snap.exitStatus ?? undefined,
    };
  }

  async waitForTerminalExit(
    params: WaitForTerminalExitRequest
  ): Promise<WaitForTerminalExitResponse> {
    const terminal = this.terminals.get(params.terminalId);
    if (!terminal) throw new Error(`AcpRuntime: terminal not found: ${params.terminalId}`);
    const status = await terminal.waitForExit();
    return { exitCode: status.exitCode, signal: status.signal ?? undefined };
  }

  async killTerminal(params: KillTerminalRequest): Promise<KillTerminalResponse> {
    const terminal = this.terminals.get(params.terminalId);
    if (!terminal) throw new Error(`AcpRuntime: terminal not found: ${params.terminalId}`);
    terminal.kill();
    return {};
  }

  releaseTerminal(params: ReleaseTerminalRequest): ReleaseTerminalResponse {
    this.terminals.release(params.terminalId);
    return {};
  }
}
