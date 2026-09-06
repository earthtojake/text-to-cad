import type { AgentCommand } from '#services/agent-plugins/api/plugins/capabilities/prompt';

export class CommandBuilder {
  private _args: string[] = [];
  private _env: Record<string, string> = {};
  constructor(private _command: string) {}
  arg(...args: string[]): this {
    this._args.push(...args);
    return this;
  }
  argIf(condition: unknown, ...args: string[]): this {
    if (condition) this._args.push(...args);
    return this;
  }
  env(key: string, value: string): this {
    this._env[key] = value;
    return this;
  }
  envIf(condition: unknown, key: string, value: string): this {
    if (condition) this._env[key] = value;
    return this;
  }
  build(): AgentCommand {
    return { command: this._command, args: this._args, env: this._env };
  }
}
export function cmd(command: string): CommandBuilder {
  return new CommandBuilder(command);
}
