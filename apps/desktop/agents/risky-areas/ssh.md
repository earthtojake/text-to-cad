# Risky Area: SSH And Shell Escaping

## Main Files

- `src/main/core/ssh/` — `ssh-connection-manager.ts`, `ssh-credential-service.ts`, `ssh-client-proxy.ts`, `sshConfigParser.ts`, `build-connect-config.ts`, `controller.ts`
- `src/main/core/fs/impl/ssh-fs.ts`
- `src/main/core/pty/ssh2-pty.ts`
- `src/main/core/terminals/impl/ssh-terminal-provider.ts`

## Rules

- treat remote shell construction as security-sensitive
- use shared escaping and validation helpers
- do not bypass path-safety or shell validation helpers
- verify how a change affects both connection setup and command execution
