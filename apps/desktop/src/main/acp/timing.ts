/**
 * What a session load spent its seconds on.
 *
 * Opening a session used to be a spinner of unknown length, and the three
 * things that made it slow are not the same size for the two adapters — so
 * the app measures rather than guesses, and `SessionManager.load` logs one
 * line per load with the phases in it. The numbers in `README.md` ("Opening
 * a session") come from this logger.
 *
 * Phases are recorded in the order they are declared and printed as deltas
 * between consecutive marks, so a line reads left to right as the wait did:
 *
 *   [acp] load 3f2a claude-code warm=no spawn=1ms initialize=1043ms
 *         firstUpdate=1398ms replay=2ms total=2444ms
 *
 * A mark nobody set is left out (an adapter that replays nothing sends no
 * `session/update`, and there is no `firstUpdate` to print). No Node and no
 * Electron here: it is a clock and a list, and the unit tests drive it with
 * a clock of their own.
 */

/** The phases of one `load`, in the order they happen. */
export const LOAD_PHASES = ["spawn", "initialize", "firstUpdate", "replay"] as const;
export type LoadPhase = (typeof LOAD_PHASES)[number];

export class PhaseTimer<Phase extends string> {
  private readonly marks = new Map<Phase, number>();
  private readonly begun: number;

  constructor(
    private readonly order: readonly Phase[],
    private readonly now: () => number = () => Date.now(),
  ) {
    this.begun = now();
  }

  /**
   * Record a phase as finished now. The first mark of a phase wins: the
   * first replay update is the one worth knowing about, and the hundred
   * after it are not.
   */
  mark(phase: Phase): void {
    if (!this.marks.has(phase)) {
      this.marks.set(phase, this.now());
    }
  }

  /** Milliseconds since the timer started. */
  get total(): number {
    return Math.round(this.now() - this.begun);
  }

  /** The recorded phases with their durations, each measured from the one before it. */
  deltas(): { phase: Phase; ms: number }[] {
    let previous = this.begun;
    const out: { phase: Phase; ms: number }[] = [];
    for (const phase of this.order) {
      const at = this.marks.get(phase);
      if (at === undefined) {
        continue;
      }
      out.push({ phase, ms: Math.round(at - previous) });
      previous = at;
    }
    return out;
  }

  /** `spawn=1ms initialize=1043ms … total=2444ms` — one line, for the log. */
  format(): string {
    const parts = this.deltas().map(({ phase, ms }) => `${phase}=${ms}ms`);
    parts.push(`total=${this.total}ms`);
    return parts.join(" ");
  }
}

/** A timer over `LOAD_PHASES`. */
export function loadTimer(now?: () => number): PhaseTimer<LoadPhase> {
  return new PhaseTimer(LOAD_PHASES, now);
}

/** The phases of one `create`: there is no transcript to replay, only a session to be given. */
export const CREATE_PHASES = ["spawn", "initialize", "session/new"] as const;
export type CreatePhase = (typeof CREATE_PHASES)[number];

export function createTimer(now?: () => number): PhaseTimer<CreatePhase> {
  return new PhaseTimer(CREATE_PHASES, now);
}
