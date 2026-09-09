// Verbatim source of the Kilo emdash notifications plugin, embedded as a string constant.
export const KILOCODE_PLUGIN_CONTENT = `\
/* global fetch, process */

export const EmdashNotifications = async () => ({
  event: async ({ event }) => {
    const port = process.env.EMDASH_HOOK_PORT;
    const token = process.env.EMDASH_HOOK_NONCE ?? process.env.EMDASH_HOOK_TOKEN;
    const ptyId = process.env.EMDASH_PTY_ID;
    if (!port || !token || !ptyId) return;

    const sessionId = getKiloSessionId(event);
    if (sessionId) {
      await postToEmdash({ port, token, ptyId, type: 'session', body: { sessionId } });
    }

    const payload = toEmdashPayload(event);
    if (!payload) return;

    await postToEmdash({ port, token, ptyId, type: payload.type, body: payload.body });
  },
});

async function postToEmdash({ port, token, ptyId, type, body }) {
  try {
    await fetch(\`http://127.0.0.1:\${port}/hook\`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Emdash-Token': token,
        'X-Emdash-Pty-Id': ptyId,
        'X-Emdash-Event-Type': type,
      },
      signal: AbortSignal.timeout(2000),
      body: JSON.stringify(body),
    });
  } catch {
    // Hook delivery is best-effort and must never interrupt Kilo.
  }
}

function getKiloSessionId(event) {
  if (!event.type?.startsWith('session.')) return undefined;

  const infoId = event.properties?.info?.id;
  if (isKiloSessionId(infoId)) return infoId.trim();

  const sessionId = event.properties?.sessionID;
  if (isKiloSessionId(sessionId)) return sessionId.trim();

  return undefined;
}

function isKiloSessionId(value) {
  return typeof value === 'string' && value.trim().startsWith('ses');
}

function toEmdashPayload(event) {
  if (event.type === 'session.idle') {
    return {
      type: 'notification',
      body: {
        notification_type: 'idle_prompt',
        title: 'Kilo',
        message: 'Kilo is ready for input.',
      },
    };
  }

  if (event.type === 'session.error') {
    return {
      type: 'error',
      body: {
        title: 'Kilo error',
        message: typeof event.properties?.error === 'string' ? event.properties.error : undefined,
      },
    };
  }

  return undefined;
}
`;
