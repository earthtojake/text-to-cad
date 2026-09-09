import { describe, expect, it } from 'vitest';
import {
  buildRemoteEditorUrl,
  buildRemoteSshAuthority,
  buildRemoteTerminalExecArgs,
} from './remoteOpenIn';

describe('remoteOpenIn', () => {
  describe('buildRemoteEditorUrl', () => {
    it('builds VSCodium remote SSH URLs', () => {
      expect(buildRemoteEditorUrl('vscodium', 'example.com', 'alice', '/repo')).toBe(
        'vscodium://vscode-remote/ssh-remote+7b22686f73744e616d65223a226578616d706c652e636f6d222c2275736572223a22616c696365227d/repo'
      );
    });

    it('omits ports from VS Code-style remote SSH URLs', () => {
      expect(buildRemoteEditorUrl('vscode', 'localhost', 'dev', '/repo', 2222)).toBe(
        'vscode://vscode-remote/ssh-remote+7b22686f73744e616d65223a226c6f63616c686f7374222c2275736572223a22646576227d/repo'
      );
    });

    it('builds Zed remote SSH URLs without encoding the SSH authority', () => {
      expect(buildRemoteEditorUrl('zed', 'localhost', 'dev', '/repo')).toBe(
        'zed://ssh/dev@localhost/repo'
      );
    });

    it('includes a non-default port in Zed remote SSH URLs', () => {
      expect(buildRemoteEditorUrl('zed', 'localhost', 'dev', '/repo', 2222)).toBe(
        'zed://ssh/dev@localhost:2222/repo'
      );
    });

    it('omits port 22 (the SSH default) from Zed remote SSH URLs', () => {
      expect(buildRemoteEditorUrl('zed', 'localhost', 'dev', '/repo', 22)).toBe(
        'zed://ssh/dev@localhost/repo'
      );
    });

    it('encodes remote path segments in editor URLs', () => {
      expect(buildRemoteEditorUrl('zed', 'localhost', 'dev', '/repo with space/#1')).toBe(
        'zed://ssh/dev@localhost/repo%20with%20space/%231'
      );
    });
  });

  describe('buildRemoteTerminalExecArgs', () => {
    it('builds argv tokens for terminal app SSH launchers', () => {
      const args = buildRemoteTerminalExecArgs({
        host: 'example.com',
        username: 'arne',
        port: 2222,
        targetPath: "/tmp/with 'quote'",
      });

      expect(args).toEqual([
        'ssh',
        'arne@example.com',
        '-o',
        'ControlMaster=no',
        '-o',
        'ControlPath=none',
        '-p',
        '2222',
        '-t',
        "cd '/tmp/with '\\''quote'\\''' && (if command -v infocmp >/dev/null 2>&1 && [ -n \"${TERM:-}\" ] && infocmp \"${TERM}\" >/dev/null 2>&1; then :; else export TERM=xterm-256color; fi) && (exec \"${SHELL:-/bin/bash}\" || exec /bin/bash || exec /bin/sh)",
      ]);
    });
  });

  describe('buildRemoteSshAuthority', () => {
    it('does not prepend the username when the host already includes one', () => {
      expect(buildRemoteSshAuthority('git@example.com', 'arne')).toBe('git@example.com');
    });
  });
});
