// Verbatim source of the MiMo Code emdash notifications plugin, embedded as a string constant.
// MiMoCode is an OpenCode fork and shares the `event` plugin hook API.
export const MIMOCODE_PLUGIN_CONTENT = `\
/* global fetch, process */

export const EmdashNotifications = async () => ({
  event: async ({ event }) => {
    const port = process.env.EMDASH_HOOK_PORT;
    const token = process.env.EMDASH_HOOK_NONCE ?? process.env.EMDASH_HOOK_TOKEN;
    const ptyId = process.env.EMDASH_PTY_ID;
    if (!port || !token || !ptyId) return;

    const sessionId = getMimoSessionId(event);
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
      body: JSON.stringify(body),
    });
  } catch {
    // Hook delivery is best-effort and must never interrupt MiMo Code.
  }
}

function getMimoSessionId(event) {
  if (!event.type?.startsWith('session.')) return undefined;

  const infoId = event.properties?.info?.id;
  if (isMimoSessionId(infoId)) return infoId.trim();

  const sessionId = event.properties?.sessionID;
  if (isMimoSessionId(sessionId)) return sessionId.trim();

  return undefined;
}

function isMimoSessionId(value) {
  return typeof value === 'string' && value.trim().startsWith('ses');
}

function toEmdashPayload(event) {
  if (event.type === 'session.idle') {
    return {
      type: 'notification',
      body: {
        notification_type: 'idle_prompt',
        title: 'MiMo Code',
        message: 'MiMo Code is ready for input.',
      },
    };
  }

  if (event.type === 'session.error') {
    return {
      type: 'error',
      body: {
        title: 'MiMo Code error',
        message: typeof event.properties?.error === 'string' ? event.properties.error : undefined,
      },
    };
  }

  return undefined;
}
`;
