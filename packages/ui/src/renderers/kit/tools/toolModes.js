// The tool-mode state machine. One tool is active at a time. A renderer declares
// its modes once; this module answers the two questions every host of tools
// asks: which tool is a file's own to open in, and what does pressing a tool do.
// The tool in hand is never saved: every open starts in the default tool.

// Mode ids are compared exactly as recorded: no trimming, no case folding.
const text = value => String(value ?? "");

/**
 * @param {{ defaultMode: string, modes: Record<string, { toggles?: boolean }> }} definition
 *   `toggles`: a session that ends when its tool is asked for again.
 */
export function createToolModes({ defaultMode, modes }) {
  const known = new Set([defaultMode, ...Object.keys(modes)]);
  const normalize = mode => (known.has(text(mode)) ? text(mode) : defaultMode);
  return Object.freeze({
    defaultMode,
    /** Anything unrecognized is the default tool, never a mode with no tool behind it. */
    normalize,
    /** The mode after `requested` is pressed while `current` is active. */
    next(current, requested) {
      const mode = normalize(requested);
      return modes[mode]?.toggles === true && current === mode ? defaultMode : mode;
    },
  });
}
