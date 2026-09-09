/** Snapshot pushed into chat state per coalesced flush; matches chat-ui's TerminalOutputSnapshot. */
export type TerminalOutputSnapshot = {
  readonly lines: readonly string[];
  readonly truncated: boolean;
  readonly version: number;
};

type TerminalOutputBinding = {
  lines(): readonly string[];
  truncated(): boolean;
  version(): number;
  onFlush(listener: () => void): () => void;
};

type TerminalOutputSession = {
  terminals: {
    current(): ReadonlyArray<{ terminalId: string; truncated?: boolean }>;
    onChange(listener: () => void): () => void;
  };
  terminalOutput(terminalId: string): Promise<TerminalOutputBinding>;
};

type TerminalEntry = {
  dispose: () => void;
  /** Re-push the current snapshot; set once the output binding resolves. */
  resync?: () => void;
};

export function bindSessionTerminalOutputs(
  session: TerminalOutputSession,
  setTerminalOutput: (terminalId: string, snapshot: TerminalOutputSnapshot | null) => void
): () => void {
  const entries = new Map<string, TerminalEntry>();
  let disposed = false;

  const agentTruncated = (terminalId: string): boolean =>
    session.terminals
      .current()
      .some((terminal) => terminal.terminalId === terminalId && terminal.truncated === true);

  const removeTerminal = (terminalId: string): void => {
    entries.get(terminalId)?.dispose();
    entries.delete(terminalId);
  };

  const syncTerminals = (): void => {
    if (disposed) return;
    const nextIds = new Set(session.terminals.current().map((terminal) => terminal.terminalId));

    for (const terminalId of Array.from(entries.keys())) {
      if (!nextIds.has(terminalId)) removeTerminal(terminalId);
    }

    for (const terminalId of nextIds) {
      const existing = entries.get(terminalId);
      if (existing) {
        // Terminal lifecycle republish (create / exit / truncation transition):
        // refresh the snapshot so the agent-side truncated flag is picked up.
        existing.resync?.();
        continue;
      }

      let unsubscribeLog: (() => void) | undefined;
      let active = true;
      const entry: TerminalEntry = {
        dispose: () => {
          active = false;
          unsubscribeLog?.();
          setTerminalOutput(terminalId, null);
        },
      };
      entries.set(terminalId, entry);

      void session
        .terminalOutput(terminalId)
        .then((binding) => {
          if (disposed || !active) return;
          const syncOutput = (): void =>
            setTerminalOutput(terminalId, {
              lines: binding.lines(),
              // Collapse agent-side (ring buffer) and client-side (byte cap)
              // truncation into one flag; the UI never distinguishes them.
              truncated: binding.truncated() || agentTruncated(terminalId),
              version: binding.version(),
            });
          entry.resync = syncOutput;
          syncOutput();
          unsubscribeLog = binding.onFlush(syncOutput);
        })
        .catch(() => {
          if (active) setTerminalOutput(terminalId, null);
        });
    }
  };

  syncTerminals();
  const unsubscribeTerminals = session.terminals.onChange(syncTerminals);
  return () => {
    disposed = true;
    unsubscribeTerminals();
    for (const terminalId of Array.from(entries.keys())) {
      removeTerminal(terminalId);
    }
  };
}
