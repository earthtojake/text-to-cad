import { reaction } from 'mobx';
import type { CadTurnLedger } from './cad-turn-ledger';

export const CAD_ARTIFACT_REVEAL_SETTLE_MS = 750;
const POLL_INTERVAL_MS = 2_000;
const TURN_START_SLACK_MS = 2_000;

/** One scan at a time, only for the visible task's active or unacknowledged turns. */
export function startCadArtifactPolling(input: {
  ledger: CadTurnLedger;
  conversationIds: () => Iterable<string>;
  scan: (sinceMs: number, isDisposed: () => boolean) => Promise<boolean>;
}): () => void {
  let disposed = false;
  let running = false;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const pending = () => input.ledger.pendingTurns(input.conversationIds());
  const schedule = (delay: number) => {
    if (disposed || running) return;
    clearTimeout(timer);
    if (pending().length) timer = setTimeout(() => void scan(), delay);
  };
  const scan = async () => {
    const turns = pending();
    if (disposed || !turns.length) return;
    running = true;
    try {
      const since = Math.min(...turns.map(([, record]) => record.startedAt));
      const settled = await input.scan(since - TURN_START_SLACK_MS, () => disposed);
      if (!disposed && settled) input.ledger.markRevealed(turns);
      failures = 0;
    } catch {
      // Keep the final scan pending across transient transport failures and remounts.
      failures += 1;
    } finally {
      running = false;
      schedule(Math.min(30_000, POLL_INTERVAL_MS * 2 ** failures));
    }
  };
  const disposeReaction = reaction(pending, () => schedule(CAD_ARTIFACT_REVEAL_SETTLE_MS));
  schedule(CAD_ARTIFACT_REVEAL_SETTLE_MS);
  return () => {
    disposed = true;
    disposeReaction();
    clearTimeout(timer);
  };
}
