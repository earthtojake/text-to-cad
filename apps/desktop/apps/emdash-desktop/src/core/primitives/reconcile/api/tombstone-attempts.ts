import z from 'zod';

/**
 * The durable, clock-free terminal-stop mechanism shared by every deletion tombstone
 * kind (ADR 0006, spec §2). The desktop tombstone row owns two fields: an integer
 * `attemptEpoch` that the Retry affordance increments durably, and a `terminalStop`
 * record written durably when a sweep attempt fails with a host-classified terminal
 * error, tagged with the epoch the attempt ran in. A stop halts auto-retry only while
 * its epoch is current — a Retry advances the epoch, so an older stop (or one a
 * registry sync tries to resurrect through the host-written mark) never stops the
 * fresh intent. No wall-clock comparison decides stop/retry.
 */

export const tombstoneTerminalStopSchema = z.object({
  /** The attempt epoch the failed attempt ran in; older epochs never stop the sweep. */
  epoch: z.number().int(),
  /** Removal step that failed, from the RPC error detail (host-classified). */
  stage: z.string(),
  message: z.string(),
  /** Epoch-ms desktop write stamp; display only, never compared. */
  at: z.number(),
});
export type TombstoneTerminalStop = z.infer<typeof tombstoneTerminalStopSchema>;

/** The epoch fields every tombstone payload carries (optional for pre-epoch rows). */
export type EpochedTombstone = {
  attemptEpoch?: number;
  terminalStop?: TombstoneTerminalStop | null;
};

/** Pre-epoch tombstones (rows written before these fields existed) read as epoch 0. */
export function tombstoneAttemptEpoch(tombstone: EpochedTombstone): number {
  return tombstone.attemptEpoch ?? 0;
}

/**
 * The stop that halts auto-retry now: recorded, and still in the current epoch. A
 * Retry's durable epoch bump leaves the record in place but makes it inert.
 */
export function activeTombstoneTerminalStop(
  tombstone: EpochedTombstone
): TombstoneTerminalStop | null {
  const stop = tombstone.terminalStop ?? null;
  if (stop === null) return null;
  return stop.epoch >= tombstoneAttemptEpoch(tombstone) ? stop : null;
}
