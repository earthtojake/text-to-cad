import type { Client, ClientChannel } from 'ssh2';

export function forwardOutStreamLocalOnClient(
  client: Client,
  socketPath: string
): Promise<ClientChannel> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      client.off('close', handleClose);
      client.off('end', handleClose);
      client.off('error', handleError);
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    };
    const handleClose = () => {
      fail(new Error('SSH connection closed while opening streamlocal channel'));
    };
    const handleError = (error: Error) => {
      fail(error);
    };

    client.once('close', handleClose);
    client.once('end', handleClose);
    client.once('error', handleError);

    try {
      client.openssh_forwardOutStreamLocal(socketPath, (error, channel) => {
        if (settled) {
          channel?.destroy();
          return;
        }
        settled = true;
        cleanup();
        if (error) {
          reject(error);
          return;
        }
        resolve(channel);
      });
    } catch (error) {
      fail(error instanceof Error ? error : new Error(String(error)));
    }
  });
}
