export const OH_MY_PI_EXTENSION_CONTENT = `\
import type { ExtensionAPI } from '@oh-my-pi/pi-coding-agent';

async function notifyEmdash(
  eventType: 'stop' | 'error' | 'notification' | 'session',
  body: Record<string, unknown> = {}
) {
  const port = process.env.EMDASH_HOOK_PORT;
  const token = process.env.EMDASH_HOOK_NONCE ?? process.env.EMDASH_HOOK_TOKEN;
  const ptyId = process.env.EMDASH_PTY_ID;

  if (!port || !token || !ptyId) return;

  try {
    await fetch(\`http://127.0.0.1:\${port}/hook\`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Emdash-Token': token,
        'X-Emdash-Pty-Id': ptyId,
        'X-Emdash-Event-Type': eventType,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(2000),
    });
  } catch {
    // Emdash may not be running when omp is launched directly; ignore hook failures.
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return 'Oh My Pi exited with an error';
}

let stopNotified = false;

async function notifyStopOnce(message: string) {
  if (stopNotified) return;
  stopNotified = true;
  await notifyEmdash('stop', { message });
}

export default function (pi: ExtensionAPI) {
  pi.on('session_start', async (_event, ctx) => {
    stopNotified = false;
    const sessionFile = ctx.sessionManager?.getSessionFile?.();
    if (!sessionFile) return;
    await notifyEmdash('session', { providerSessionId: sessionFile });
  });

  pi.on('session_stop', async (event) => {
    if (typeof event.session_file === 'string' && event.session_file.trim()) {
      await notifyEmdash('session', { providerSessionId: event.session_file });
    }
    await notifyStopOnce('Task completed');
  });

  pi.on('agent_end', async () => {
    await notifyStopOnce('Task completed');
  });

  pi.on('session_shutdown', async () => {
    await notifyStopOnce('Session ended');
  });

  process.once('uncaughtException', (error) => {
    void notifyEmdash('error', { message: errorMessage(error) });
  });

  process.once('unhandledRejection', (reason) => {
    void notifyEmdash('error', { message: errorMessage(reason) });
  });
}
`;
