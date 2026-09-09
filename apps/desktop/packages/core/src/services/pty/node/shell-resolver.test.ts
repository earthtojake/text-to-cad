import { describe, expect, it } from 'vitest';
import {
  getLocalTerminalShellAvailability,
  resolveTerminalShell,
  ShellUnavailableError,
} from './shell-resolver';

describe('terminal shell resolver', () => {
  it('keeps system intent while recording the concrete local shell', async () => {
    const profile = await resolveTerminalShell({
      intent: 'system',
      platform: 'darwin',
      env: { SHELL: '/bin/zsh' },
    });

    expect(profile).toMatchObject({
      id: 'target-default',
      resolvedShellId: 'zsh',
      resolvedFromSystem: true,
      executable: '/bin/zsh',
    });
  });

  it('keeps login-shell args for fish local system shells', async () => {
    const profile = await resolveTerminalShell({
      intent: 'system',
      platform: 'darwin',
      env: { SHELL: '/opt/homebrew/bin/fish' },
    });

    expect(profile).toMatchObject({
      id: 'target-default',
      resolvedShellId: 'fish',
      resolvedFromSystem: true,
      executable: '/opt/homebrew/bin/fish',
      family: 'posix',
      interactiveArgs: ['-il'],
      commandArgs: ['-lc'],
    });
  });

  it('uses ComSpec as the Windows system shell', async () => {
    const profile = await resolveTerminalShell({
      intent: 'system',
      platform: 'win32',
      env: { ComSpec: 'C:\\Windows\\System32\\cmd.exe' },
    });

    expect(profile).toMatchObject({
      id: 'target-default',
      resolvedShellId: 'cmd',
      executable: 'C:\\Windows\\System32\\cmd.exe',
      family: 'windows-cmd',
    });
  });

  it('keeps regular PowerShell command profiles non-profile-loading by default', async () => {
    const profile = await resolveTerminalShell({
      intent: 'pwsh',
      platform: 'win32',
      env: {
        Path: 'C:\\Program Files\\PowerShell\\7',
        PATHEXT: '.EXE;.CMD',
      },
      fileExists: (candidate) => candidate === 'C:\\Program Files\\PowerShell\\7\\pwsh.exe',
    });

    expect(profile.commandArgs).toEqual(['-NoProfile', '-Command']);
  });

  it('resolves Windows bash to Git Bash instead of the WSL bash launcher', async () => {
    const profile = await resolveTerminalShell({
      intent: 'bash',
      platform: 'win32',
      env: {
        ProgramFiles: 'C:\\Program Files',
        Path: 'C:\\Windows\\System32;C:\\Program Files\\Git\\bin',
        PATHEXT: '.EXE;.CMD',
      },
      fileExists: (candidate) =>
        candidate.toLowerCase() === 'c:\\windows\\system32\\bash.exe' ||
        candidate.toLowerCase() === 'c:\\program files\\git\\bin\\bash.exe',
    });

    expect(profile).toMatchObject({
      id: 'bash',
      resolvedShellId: 'bash',
      executable: 'C:\\Program Files\\Git\\bin\\bash.exe',
      family: 'posix',
    });
  });

  it('resolves explicit WSL on Windows without POSIX shell args', async () => {
    const profile = await resolveTerminalShell({
      intent: 'wsl',
      platform: 'win32',
      env: {
        SystemRoot: 'C:\\Windows',
        Path: 'C:\\Windows\\System32',
        PATHEXT: '.EXE;.CMD',
      },
      fileExists: (candidate) => candidate.toLowerCase() === 'c:\\windows\\system32\\wsl.exe',
    });

    expect(profile).toMatchObject({
      id: 'wsl',
      resolvedShellId: 'wsl',
      executable: 'C:\\Windows\\System32\\wsl.exe',
      family: 'wsl',
      interactiveArgs: [],
      commandArgs: ['--exec', 'sh', '-lc'],
    });
  });

  it('does not resolve explicit WSL from an arbitrary PATH entry on Windows', async () => {
    await expect(
      resolveTerminalShell({
        intent: 'wsl',
        platform: 'win32',
        env: {
          SystemRoot: 'C:\\Windows',
          Path: 'C:\\Tools',
          PATHEXT: '.EXE;.CMD',
        },
        fileExists: (candidate) => candidate.toLowerCase() === 'c:\\tools\\wsl.exe',
      })
    ).rejects.toBeInstanceOf(ShellUnavailableError);
  });

  it('reports Windows shells separately from POSIX shells', async () => {
    const availability = await getLocalTerminalShellAvailability({
      platform: 'win32',
      env: {
        ComSpec: 'C:\\Windows\\System32\\cmd.exe',
        Path: 'C:\\Windows\\System32',
        PATHEXT: '.EXE;.CMD',
      },
      fileExists: (candidate) => candidate === 'C:\\Windows\\System32\\powershell.exe',
    });

    expect(availability.find((entry) => entry.id === 'system')).toMatchObject({
      available: true,
      label: 'cmd',
      isSystemDefault: true,
    });
    expect(availability.find((entry) => entry.id === 'cmd')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'powershell')).toMatchObject({
      label: 'PowerShell',
      available: true,
    });
    expect(availability.find((entry) => entry.id === 'pwsh')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'zsh')).toBeUndefined();
    expect(availability.map((entry) => entry.id)).toEqual(['system', 'powershell', 'wsl', 'bash']);
  });

  it('offers WSL separately from Git Bash and keeps one plainly labeled PowerShell option', async () => {
    const availability = await getLocalTerminalShellAvailability({
      platform: 'win32',
      env: {
        ComSpec: 'C:\\Windows\\System32\\cmd.exe',
        ProgramFiles: 'C:\\Program Files',
        SystemRoot: 'C:\\Windows',
        Path: 'C:\\Windows\\System32;C:\\Program Files\\Git\\bin',
        PATHEXT: '.EXE;.CMD',
      },
      readDirNames: (candidate) => (candidate === 'C:\\Program Files\\PowerShell' ? ['7.5.1'] : []),
      fileExists: (candidate) =>
        candidate.toLowerCase() === 'c:\\windows\\system32\\powershell.exe' ||
        candidate.toLowerCase() === 'c:\\program files\\powershell\\7.5.1\\pwsh.exe' ||
        candidate.toLowerCase() === 'c:\\windows\\system32\\wsl.exe' ||
        candidate.toLowerCase() === 'c:\\program files\\git\\bin\\bash.exe',
    });

    expect(availability.find((entry) => entry.id === 'bash')).toMatchObject({
      label: 'Git Bash',
      available: true,
    });
    expect(availability.find((entry) => entry.id === 'wsl')).toMatchObject({
      label: 'WSL',
      available: true,
    });
    expect(availability.find((entry) => entry.id === 'powershell')).toMatchObject({
      label: 'PowerShell',
      available: true,
    });
    expect(availability.find((entry) => entry.id === 'pwsh')).toBeUndefined();
  });

  it('marks Windows PowerShell unavailable when it is not found on PATH', async () => {
    const availability = await getLocalTerminalShellAvailability({
      platform: 'win32',
      env: {
        ComSpec: 'C:\\Windows\\System32\\cmd.exe',
        Path: 'C:\\Windows\\System32',
        PATHEXT: '.EXE;.CMD',
      },
      fileExists: () => false,
    });

    expect(availability.find((entry) => entry.id === 'powershell')).toMatchObject({
      available: false,
      reason: 'Not found on this machine',
    });
  });

  it('filters Windows-only shells out of POSIX local availability', async () => {
    const availability = await getLocalTerminalShellAvailability({
      platform: 'darwin',
      env: { PATH: '/bin:/usr/bin' },
      fileExists: (candidate) => candidate === '/bin/zsh' || candidate === '/bin/bash',
    });

    expect(availability.find((entry) => entry.id === 'cmd')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'powershell')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'pwsh')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'wsl')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'system')).toMatchObject({
      label: 'zsh',
      isSystemDefault: true,
    });
    expect(availability.find((entry) => entry.id === 'bash')?.available).toBe(true);
    expect(availability.find((entry) => entry.id === 'zsh')).toBeUndefined();
    expect(availability.find((entry) => entry.id === 'fish')?.available).toBe(false);
    expect(availability.at(-1)?.available).toBe(false);
  });

  it('labels unknown local system shells by executable basename', async () => {
    const availability = await getLocalTerminalShellAvailability({
      platform: 'darwin',
      env: { SHELL: '/opt/homebrew/bin/fish', PATH: '/bin:/usr/bin' },
      fileExists: () => false,
    });

    expect(availability.find((entry) => entry.id === 'system')).toMatchObject({
      label: 'fish',
      isSystemDefault: true,
    });
    expect(availability.find((entry) => entry.id === 'fish')).toBeUndefined();
  });

  it('throws for unavailable explicit local shells', async () => {
    await expect(
      resolveTerminalShell({
        intent: 'zsh',
        platform: 'linux',
        env: { PATH: '/usr/bin' },
        fileExists: () => false,
      })
    ).rejects.toBeInstanceOf(ShellUnavailableError);
  });
});
