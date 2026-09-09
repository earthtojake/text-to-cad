import { z } from 'zod';

export const clientHelloSchema = z.object({
  protocolVersion: z.string(),
  client: z.object({
    id: z.string(),
    appVersion: z.string(),
  }),
});

export const serverHelloSchema = z.object({
  /** The server's own protocol version, for display and telemetry. */
  protocolVersion: z.string(),
  /** Negotiated version: major.min(clientMinor, serverMinor).0 */
  agreedVersion: z.string(),
  /** The negotiated minor. Clients gate minor-guarded features on agreedMinor >= N. */
  agreedMinor: z.number().int(),
  server: z.object({
    appVersion: z.string(),
    /** Stable per-process identity, set at daemon startup. */
    daemonId: z.string(),
    /** Unix timestamp (ms) when the daemon started. */
    startedAt: z.number(),
  }),
});

export type ClientHello = z.infer<typeof clientHelloSchema>;
export type ServerHello = z.infer<typeof serverHelloSchema>;
