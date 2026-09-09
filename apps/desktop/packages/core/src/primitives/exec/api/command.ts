export type ShellFamily = 'posix' | 'csh' | 'windows-cmd' | 'powershell' | 'wsl';

export type Command = {
  command: string;
  args: string[];
  env?: Record<string, string>;
  cwd?: string;
};

export function quoteArg(value: string, family: ShellFamily): string {
  switch (family) {
    case 'posix':
    case 'wsl':
      return quotePosixArg(value);
    case 'csh':
      return quoteCshArg(value);
    case 'windows-cmd':
      return quoteCmdArg(value);
    case 'powershell':
      return quotePowerShellArg(value);
  }
}

export function formatCommandLine(
  command: Pick<Command, 'command' | 'args'>,
  family: ShellFamily
): string {
  const commandLine = [command.command, ...command.args]
    .map((value) => quoteArg(value, family))
    .join(' ');
  return family === 'powershell' ? `& ${commandLine}` : commandLine;
}

function quotePosixArg(value: string): string {
  if (value.length === 0) return "''";
  if (/^[a-zA-Z0-9.,_:/@=+-]+$/u.test(value)) return value;
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function quoteCshArg(value: string): string {
  return quotePosixArg(value).replaceAll('!', '\\!');
}

function quoteCmdArg(value: string): string {
  if (value.length === 0) return '""';
  if (!/[\s"^&|<>()%!]/.test(value)) return value;
  return `"${value
    .replaceAll('%', '%%')
    .replaceAll('!', '^!')
    .replace(/(["^&|<>()])/g, '^$1')}"`;
}

function quotePowerShellArg(value: string): string {
  if (value.length === 0) return "''";
  if (!/[\s'`"$;&|<>(){}[\],]/.test(value)) return value;
  return `'${value.replaceAll("'", "''")}'`;
}
