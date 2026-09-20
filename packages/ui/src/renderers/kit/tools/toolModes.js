// The tool-mode state machine. One tool is active at a time. A renderer declares
// its modes once; this module answers the three questions every host of tools
// asks: what does pressing a tool do, what may a saved tab record, and which
// tool does a file open in.

// Mode ids are compared exactly as recorded: no trimming, no case folding.
const text = value => String(value ?? "");

/**
 * @param {{ defaultMode: string, modes: Record<string, { toggles?: boolean, persists?: boolean }> }} definition
 *   `toggles`: a session that ends when its tool is asked for again.
 *   `persists`: a mode a saved tab may record. Anything else is a live session and
 *   is recorded as the default mode. The default mode always persists.
 */
export function createToolModes({ defaultMode, modes }) {
  const known = new Set([defaultMode, ...Object.keys(modes)]);
  const normalize = mode => (known.has(mode) ? mode : defaultMode);
  const persisted = recorded => {
    const mode = text(recorded || defaultMode);
    return mode === defaultMode || modes[mode]?.persists === true ? mode : defaultMode;
  };
  return Object.freeze({
    defaultMode,
    /** Anything unrecognized is the default tool, never a mode with no tool behind it. */
    normalize,
    /** The mode after `requested` is pressed while `current` is active. */
    next(current, requested) {
      const mode = normalize(requested);
      return modes[mode]?.toggles === true && current === mode ? defaultMode : mode;
    },
    /** What a record holds for a mode. */
    persisted,
    /**
     * The mode a file opens in. `opensIn` is the tool of a file with nothing
     * recorded; `never` lists recorded modes this file does not restore into.
     */
    restore(recorded, { opensIn = defaultMode, never = [] } = {}) {
      const mode = persisted(recorded);
      if (never.includes(mode)) return defaultMode;
      return text(recorded) ? mode : opensIn;
    }
  });
}
