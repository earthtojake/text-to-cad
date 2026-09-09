import { describe, expect, it } from 'vitest';
import { formatCommandLine, quoteArg } from './command';

describe('quoteArg', () => {
  it('quotes POSIX shell arguments', () => {
    expect(quoteArg('', 'posix')).toBe("''");
    expect(quoteArg('/home/user/project', 'posix')).toBe('/home/user/project');
    expect(quoteArg('/home/user/file name', 'posix')).toBe("'/home/user/file name'");
    expect(quoteArg('# comment', 'posix')).toBe("'# comment'");
    expect(quoteArg("a'; rm -rf /; echo '", 'posix')).toBe("'a'\\''; rm -rf /; echo '\\'''");
  });

  it('uses POSIX quoting for WSL arguments', () => {
    expect(quoteArg('$HOME/*.txt', 'wsl')).toBe("'$HOME/*.txt'");
  });

  it('escapes csh history expansion', () => {
    expect(quoteArg('hello!', 'csh')).toBe("'hello\\!'");
  });

  it('quotes cmd.exe arguments', () => {
    expect(quoteArg('', 'windows-cmd')).toBe('""');
    expect(quoteArg('plain', 'windows-cmd')).toBe('plain');
    expect(quoteArg('a b&%x!', 'windows-cmd')).toBe('"a b^&%%x^^!"');
  });

  it('quotes PowerShell arguments', () => {
    expect(quoteArg('', 'powershell')).toBe("''");
    expect(quoteArg('plain', 'powershell')).toBe('plain');
    expect(quoteArg("a b'c", 'powershell')).toBe("'a b''c'");
  });
});

describe('formatCommandLine', () => {
  it('formats a command and its arguments for the requested shell', () => {
    expect(
      formatCommandLine(
        {
          command: '/opt/Emdash Server/bin/emdash',
          args: ['start', '--socket', '/tmp/emdash socket'],
        },
        'posix'
      )
    ).toBe("'/opt/Emdash Server/bin/emdash' start --socket '/tmp/emdash socket'");
  });

  it('uses the PowerShell invocation operator', () => {
    expect(
      formatCommandLine(
        {
          command: 'C:\\Program Files\\Emdash\\emdash.exe',
          args: ['start', '--name', "David's task"],
        },
        'powershell'
      )
    ).toBe("& 'C:\\Program Files\\Emdash\\emdash.exe' start --name 'David''s task'");
  });
});
