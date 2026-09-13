// ForwardAgent socket resolution and compatibility checks.
import type { ConnectConfig } from 'ssh2';
import {
  resolveAgentSocketFromResolved,
  type ResolvedAgentSocket,
  type ResolvedSshConfig,
} from '../config/resolve-ssh-config';
import type { SshConnectDeps } from './resolve-ssh-connect-config';
import type { AuthResult } from './ssh-connect-auth';

function expandForwardAgentValue(
  value: string,
  env: Record<string, string | undefined>
): string | undefined {
  if (value === 'SSH_AUTH_SOCK') return env.SSH_AUTH_SOCK;
  const variableOnly = value.match(/^\$([A-Za-z_][A-Za-z0-9_]*)$/);
  if (variableOnly) return env[variableOnly[1]];
  const bracedVariableOnly = value.match(/^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$/);
  if (bracedVariableOnly) return env[bracedVariableOnly[1]];
  return value;
}

function agentForForwarding(resolved: ResolvedSshConfig | undefined, deps: SshConnectDeps): string {
  if (resolved?.forwardAgentValue) {
    const agent = expandForwardAgentValue(resolved.forwardAgentValue, deps.env);
    if (!agent) {
      throw new Error('Agent forwarding was requested, but the ForwardAgent socket is unavailable');
    }
    return agent;
  }

  const agentSocket = resolved
    ? resolveAgentSocketFromResolved(resolved, deps.env)
    : ({ kind: 'unset' } satisfies ResolvedAgentSocket);
  const agent = agentSocket.kind === 'socket' ? agentSocket.path : deps.env.SSH_AUTH_SOCK;
  if (!agent) {
    throw new Error('Agent forwarding was requested, but no SSH agent socket is available');
  }
  return agent;
}

function assertAgentSocketCompatible(
  authAgentSocket: string | undefined,
  forwardingAgent: string
): void {
  if (authAgentSocket && authAgentSocket !== forwardingAgent) {
    throw new Error(
      'Agent authentication and ForwardAgent resolved to different SSH agent sockets, which ssh2 cannot represent safely'
    );
  }
}

export function applyForwardAgent(
  config: ConnectConfig,
  enabled: boolean,
  resolved: ResolvedSshConfig | undefined,
  authResult: AuthResult,
  deps: SshConnectDeps
): void {
  if (!enabled) return;

  const forwardingAgent = agentForForwarding(resolved, deps);
  assertAgentSocketCompatible(authResult.agentSocketPath, forwardingAgent);
  config.agentForward = true;
  if (typeof config.agent !== 'object') {
    config.agent = forwardingAgent;
  }
}
