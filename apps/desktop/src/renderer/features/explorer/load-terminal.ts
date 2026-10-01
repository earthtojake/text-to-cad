/**
 * The terminal's chunk (xterm), loaded ahead of its first tab.
 *
 * `ExplorerPane` draws the terminal through `React.lazy` over this, so xterm
 * stays out of the window's first chunk. A tab the person asks for still has
 * to take the keyboard (`./focus`), and a body that is still a fallback
 * cannot: so the chunk is fetched while the window is idle after its first
 * paint, and again — a no-op once it is in — the moment a new terminal is
 * asked for, before the strip has rendered the tab.
 */
export const loadTerminal = () => import("./TerminalTab");

/**
 * Start the terminal's chunk without waiting for it. A failure is not reported here: the tab
 * draws through `lazy` inside a boundary (`ExplorerPane`), which shows it with a Try again.
 */
export function preloadTerminal(): void {
  void loadTerminal().catch(() => {});
}
