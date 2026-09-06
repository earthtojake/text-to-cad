/**
 * The client half of ACP (plan §5): what the agent may ask of us.
 *
 *   - `fs/read_text_file`, `fs/write_text_file`: real files. Writes are
 *     confined to the session's working directory and announced through
 *     `onFilesChanged` so the explorer refreshes what it has open.
 *   - `terminal/*`: `TerminalManager`.
 *   - `session/request_permission`: parked in a pending map until the
 *     renderer answers, unless the approval mode is `approve-for-me`, which
 *     answers the agent's `allow_once` option itself. Either way the
 *     transcript gets the request and its outcome as events.
 *   - `session/update`: nothing. The connection reads every update off the
 *     wire before the SDK parses it (`connection.ts`), so the reducer sees
 *     the raw payload and draft update kinds the SDK does not know yet.
 */
import { mkdir, readFile, realpath, writeFile } from "node:fs/promises";
import path from "node:path";

import { RequestError } from "@agentclientprotocol/sdk";
import type * as acp from "@agentclientprotocol/sdk";

import { pendingPermissionFromRequest } from "../../shared/acp/reduce";
import type { ApprovalMode, PendingPermission, SessionEvent } from "../../shared/acp/types";
import type { TerminalManager } from "./terminals";

type PermissionOutcome = Extract<SessionEvent, { type: "permission/resolve" }>["outcome"];

export type AcpClientOptions = {
  /** The session's working directory — the only place the agent may write through us. */
  cwd: string;
  /** Environment for terminals the agent creates. */
  env: Record<string, string>;
  terminals: TerminalManager;
  dispatch: (event: SessionEvent) => void;
  onFilesChanged?: (paths: string[]) => void;
  approvalMode?: ApprovalMode;
};

export class AcpClient implements acp.Client {
  approvalMode: ApprovalMode;
  private readonly pending = new Map<string, (outcome: PermissionOutcome) => void>();
  private counter = 0;

  constructor(private readonly options: AcpClientOptions) {
    this.approvalMode = options.approvalMode ?? "ask";
  }

  /* ---------------------------------------------------------------------- */
  /* session/*                                                               */
  /* ---------------------------------------------------------------------- */

  sessionUpdate(): void {
    // Observed on the wire by the connection; see the module comment.
  }

  async requestPermission(
    params: acp.RequestPermissionRequest,
  ): Promise<acp.RequestPermissionResponse> {
    const requestId = `perm-${++this.counter}`;
    const request = pendingPermissionFromRequest(requestId, params);
    if (!request) {
      return { outcome: { outcome: "cancelled" } };
    }
    this.options.dispatch({ type: "permission/request", request, at: Date.now() });

    const auto = this.autoAnswer(request);
    if (auto) {
      this.options.dispatch({ type: "permission/resolve", requestId, outcome: auto, at: Date.now() });
      return toResponse(auto);
    }

    return new Promise((resolve) => {
      this.pending.set(requestId, (outcome) => {
        this.pending.delete(requestId);
        this.options.dispatch({ type: "permission/resolve", requestId, outcome, at: Date.now() });
        resolve(toResponse(outcome));
      });
    });
  }

  /** `approve-for-me` answers the agent's own allow-once option; anything else asks. */
  private autoAnswer(request: PendingPermission): PermissionOutcome | null {
    if (this.approvalMode !== "approve-for-me") {
      return null;
    }
    const allowOnce = request.options.find((option) => option.kind === "allow_once");
    return allowOnce ? { state: "selected", optionId: allowOnce.optionId } : null;
  }

  /** The renderer's answer. Unknown or already-answered ids are ignored. */
  respondPermission(requestId: string, optionId: string | null): boolean {
    const resolve = this.pending.get(requestId);
    if (!resolve) {
      return false;
    }
    resolve(optionId === null ? { state: "cancelled" } : { state: "selected", optionId });
    return true;
  }

  /** On `session/cancel` (and on close): every open request is answered "cancelled". */
  cancelPendingPermissions(): void {
    for (const resolve of [...this.pending.values()]) {
      resolve({ state: "cancelled" });
    }
  }

  get pendingPermissionIds(): string[] {
    return [...this.pending.keys()];
  }

  /* ---------------------------------------------------------------------- */
  /* fs/*                                                                    */
  /* ---------------------------------------------------------------------- */

  async readTextFile(params: acp.ReadTextFileRequest): Promise<acp.ReadTextFileResponse> {
    return explained(params.path, async () => {
      const file = absolute(params.path);
      const content = await readFile(file, "utf8");
      if (params.line == null && params.limit == null) {
        return { content };
      }
      const lines = content.split("\n");
      const start = Math.max(0, (params.line ?? 1) - 1);
      const end = params.limit == null ? lines.length : start + params.limit;
      return { content: lines.slice(start, end).join("\n") };
    });
  }

  async writeTextFile(params: acp.WriteTextFileRequest): Promise<acp.WriteTextFileResponse> {
    return explained(params.path, async () => {
      const file = await confineToCwd(this.options.cwd, params.path);
      await mkdir(path.dirname(file), { recursive: true });
      await writeFile(file, params.content, "utf8");
      this.options.onFilesChanged?.([file]);
      return {};
    });
  }

  /* ---------------------------------------------------------------------- */
  /* terminal/*                                                              */
  /* ---------------------------------------------------------------------- */

  createTerminal(params: acp.CreateTerminalRequest): acp.CreateTerminalResponse {
    const terminalId = this.options.terminals.create({
      command: params.command,
      args: params.args,
      env: params.env,
      cwd: params.cwd ?? this.options.cwd,
      outputByteLimit: params.outputByteLimit,
      baseEnv: this.options.env,
    });
    return { terminalId };
  }

  terminalOutput(params: acp.TerminalOutputRequest): acp.TerminalOutputResponse {
    const { output, truncated, exitStatus } = this.options.terminals.output(params.terminalId);
    return {
      output,
      truncated,
      exitStatus: exitStatus ? { exitCode: exitStatus.exitCode, signal: exitStatus.signal } : null,
    };
  }

  async waitForTerminalExit(
    params: acp.WaitForTerminalExitRequest,
  ): Promise<acp.WaitForTerminalExitResponse> {
    const exit = await this.options.terminals.waitForExit(params.terminalId);
    return { exitCode: exit.exitCode, signal: exit.signal };
  }

  killTerminal(params: acp.KillTerminalRequest): acp.KillTerminalResponse {
    this.options.terminals.kill(params.terminalId);
    return {};
  }

  releaseTerminal(params: acp.ReleaseTerminalRequest): acp.ReleaseTerminalResponse {
    this.options.terminals.release(params.terminalId);
    return {};
  }

  /** Kill every terminal and answer every open permission request. */
  dispose(): void {
    this.cancelPendingPermissions();
    this.options.terminals.releaseAll();
  }
}

/**
 * A plain `Error` thrown from a client method reaches the agent as a bare
 * "Internal error"; a `RequestError` carries its message, so the agent (and
 * the transcript) can say why a read or write was refused.
 */
async function explained<T>(file: string, work: () => Promise<T>): Promise<T> {
  try {
    return await work();
  } catch (error) {
    if (error instanceof RequestError) {
      throw error;
    }
    const message = error instanceof Error ? error.message : String(error);
    throw RequestError.internalError({ path: file }, message);
  }
}

function toResponse(outcome: PermissionOutcome): acp.RequestPermissionResponse {
  return outcome.state === "selected"
    ? { outcome: { outcome: "selected", optionId: outcome.optionId } }
    : { outcome: { outcome: "cancelled" } };
}

function absolute(target: string): string {
  if (!path.isAbsolute(target)) {
    throw new Error(`path must be absolute: ${target}`);
  }
  return path.normalize(target);
}

/**
 * The absolute, normalised path if it lies inside `cwd`; throws otherwise.
 * Symlinks are resolved on the deepest existing ancestor so a link out of
 * the tree does not count as inside it. Exported for the tests.
 */
export async function confineToCwd(cwd: string, target: string): Promise<string> {
  const file = absolute(target);
  const root = await realpathOrSelf(cwd);
  const inside = (candidate: string) => {
    const relative = path.relative(root, candidate);
    return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
  };
  if (!inside(file)) {
    throw new Error(`refusing to write outside the session directory: ${target}`);
  }
  const resolvedParent = await realpathOrSelf(await deepestExisting(path.dirname(file)));
  if (!inside(resolvedParent)) {
    throw new Error(`refusing to write through a link that leaves the session directory: ${target}`);
  }
  return file;
}

async function realpathOrSelf(target: string): Promise<string> {
  try {
    return await realpath(target);
  } catch {
    return path.normalize(target);
  }
}

async function deepestExisting(dir: string): Promise<string> {
  let current = dir;
  for (;;) {
    try {
      await realpath(current);
      return current;
    } catch {
      const parent = path.dirname(current);
      if (parent === current) {
        return current;
      }
      current = parent;
    }
  }
}
