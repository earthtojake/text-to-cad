import type { Duplex } from 'node:stream';
import { streamTransport, type WireTransport } from '@emdash/wire/rpc';

export function ownedStreamTransport(stream: Duplex): WireTransport {
  const transport = streamTransport(stream, stream);
  let closed = false;
  return {
    ...transport,
    close() {
      if (closed) return;
      closed = true;
      transport.close?.();
      stream.destroy();
    },
  };
}
