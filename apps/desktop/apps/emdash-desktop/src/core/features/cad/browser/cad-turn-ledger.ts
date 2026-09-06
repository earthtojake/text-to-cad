import { action, observable } from 'mobx';

export type CadTurnRecord = {
  startedAt: number;
  endedAt: number | null;
  revealed: boolean;
};

export type ConversationStatusSnapshot = ReadonlyArray<readonly [id: string, status: string]>;

// A permission or question pauses the same turn; tools may finish while it is paused.
const isActiveTurn = (status: string | undefined) =>
  status === 'working' || status === 'awaiting-input';

/**
 * Which turns are active or still owe a final model scan, for every conversation
 * in the app. It lives outside any task view so a turn that starts or ends
 * while another project is on screen, or while a pane change remounts the
 * task view, is neither lost nor scanned from the wrong moment.
 */
export class CadTurnLedger {
  readonly turns = observable.map<string, CadTurnRecord>();

  constructor(private readonly now: () => number = Date.now) {}

  /** Fold a status snapshot against the previous one: a turn starts when a conversation begins working and ends when it stops. */
  readonly apply = action(
    (current: ConversationStatusSnapshot, previous?: ConversationStatusSnapshot): void => {
      const before = new Map(previous ?? []);
      for (const [id, status] of current) {
        const was = before.get(id);
        if (isActiveTurn(status) && !isActiveTurn(was)) {
          this.turns.set(id, { startedAt: this.now(), endedAt: null, revealed: false });
        } else if (isActiveTurn(was) && !isActiveTurn(status)) {
          const record = this.turns.get(id);
          this.turns.set(id, {
            startedAt: record?.startedAt ?? this.now(),
            endedAt: this.now(),
            revealed: false,
          });
        }
      }
    }
  );

  /** Conversations already working when a watcher attaches: their turn is assumed to start now. */
  readonly seed = action((current: ConversationStatusSnapshot): void => {
    for (const [id, status] of current) {
      if (isActiveTurn(status) && !this.turns.has(id)) {
        this.turns.set(id, { startedAt: this.now(), endedAt: null, revealed: false });
      }
    }
  });

  /** Immutable record snapshots let an in-flight scan acknowledge only the turns it saw. */
  pendingTurns(ids: Iterable<string>): Array<readonly [string, CadTurnRecord]> {
    return [...ids].flatMap((id) => {
      const record = this.turns.get(id);
      return record && !record.revealed ? [[id, record] as const] : [];
    });
  }

  readonly markRevealed = action((turns: ReadonlyArray<readonly [string, CadTurnRecord]>): void => {
    for (const [id, record] of turns) {
      if (record.endedAt !== null && this.turns.get(id) === record) {
        this.turns.set(id, { ...record, revealed: true });
      }
    }
  });
}

/** The app-wide ledger. */
export const cadTurnLedger = new CadTurnLedger();
