import { spawnSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import {
  EMDASH_MARKER,
  EMDASH_HOOK_VERSION_MARKER,
  filterUserHooks,
  makeNotificationHookCommand,
  makeStdinHookCommand,
  makeWindowsPowerShellHookCommand,
} from './hooks';

describe('hook command helpers', () => {
  it('builds POSIX stdin hook commands', () => {
    expect(makeStdinHookCommand('stop', { platform: 'linux' })).toBe(
      `${EMDASH_HOOK_VERSION_MARKER}; ` +
        'if [ -z "${EMDASH_HOOK_PORT:-}" ] || [ -z "${EMDASH_HOOK_NONCE:-}" ] || [ -z "${EMDASH_PTY_ID:-}" ]; then exit 0; fi; ' +
        'curl -sf -X POST ' +
        '-H "Content-Type: application/json" ' +
        '-H "X-Emdash-Token: $EMDASH_HOOK_NONCE" ' +
        '-H "X-Emdash-Pty-Id: $EMDASH_PTY_ID" ' +
        '-H "X-Emdash-Event-Type: stop" ' +
        '-d @- ' +
        '"http://127.0.0.1:$EMDASH_HOOK_PORT/hook" || true'
    );
  });

  it.skipIf(process.platform === 'win32')(
    'does not invoke curl when the Emdash hook environment is absent',
    () => {
      const command = makeStdinHookCommand('stop', { platform: 'linux' });
      const shellCommand = `curl() { printf called; }; ${command}`;

      const outsideEmdash = spawnSync('/bin/sh', ['-c', shellCommand], {
        encoding: 'utf8',
        env: { PATH: process.env.PATH ?? '' },
        input: '{}',
      });
      const insideEmdash = spawnSync('/bin/sh', ['-c', shellCommand], {
        encoding: 'utf8',
        env: {
          PATH: process.env.PATH ?? '',
          EMDASH_HOOK_PORT: '1234',
          EMDASH_HOOK_NONCE: 'nonce',
          EMDASH_PTY_ID: 'pty-1',
        },
        input: '{}',
      });

      expect(outsideEmdash.status).toBe(0);
      expect(outsideEmdash.stdout).toBe('');
      expect(insideEmdash.status).toBe(0);
      expect(insideEmdash.stdout).toBe('called');
    }
  );

  it('builds Windows hook commands without a quoted cmd.exe body', () => {
    const command = makeNotificationHookCommand('idle_prompt', { platform: 'win32' });

    expect(command).toMatch(
      /^cmd\.exe \/d \/c set EMDASH_HOOK_MARKER=EMDASH_HOOK_CONFIG_VERSION=1 EMDASH_HOOK_PORT&&powershell\.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand [A-Za-z0-9+/]+=*$/
    );
    expect(command).toContain(EMDASH_MARKER);
    expect(command).not.toContain('/c "');
    expect(command).not.toContain('& powershell.exe');
  });

  it('emits no redirects (an outer shell parsing >NUL creates a stray NUL file)', () => {
    const command = makeWindowsPowerShellHookCommand('Write-Output "ok"');

    expect(command).not.toContain('>');
  });

  it('keeps the Emdash markers visible to hook config cleanup without PowerShell args', () => {
    const command = makeWindowsPowerShellHookCommand('Write-Output "ok"');

    expect(
      command.startsWith(
        `cmd.exe /d /c set EMDASH_HOOK_MARKER=${EMDASH_HOOK_VERSION_MARKER} ${EMDASH_MARKER}&&powershell.exe `
      )
    ).toBe(true);
    expect(filterUserHooks([{ command }])).toHaveLength(0);
  });
});
