/**
 * StickToBottom — tracks whether the scroll container is "stuck" at the bottom
 * and scrolls to bottom on demand if stuck.
 */

/** Distance from the bottom (px) within which the container is considered "stuck". */
export const STICK_THRESHOLD_PX = 48;

export class StickToBottom {
  private el: HTMLElement;
  private stuck = true;
  private rafId: number | null = null;
  /**
   * While paused, the scroll listener skips its scrollHeight/clientHeight reads.
   * Set true by ChatRoot when a height tween starts; cleared on tween end.
   */
  private paused = false;

  constructor(scrollEl: HTMLElement) {
    this.el = scrollEl;
    this.onScroll = this.onScroll.bind(this);
    this.el.addEventListener('scroll', this.onScroll, { passive: true });
  }

  private onScroll(): void {
    if (this.paused) return;
    const el = this.el;
    const dist = el.scrollHeight - el.clientHeight - el.scrollTop;
    this.stuck = dist <= STICK_THRESHOLD_PX;
  }

  /** Pause/resume the scroll listener to avoid forced layout during tweens. */
  setPaused(paused: boolean): void {
    this.paused = paused;
  }

  /**
   * Force an immediate stuck-state recalculation from live DOM geometry.
   * Call once after unpausing (e.g. at animation end) to resync before the
   * next user-driven scroll event arrives.
   */
  recalcStuck(): void {
    const el = this.el;
    const dist = el.scrollHeight - el.clientHeight - el.scrollTop;
    this.stuck = dist <= STICK_THRESHOLD_PX;
  }

  /** Whether the container is currently pinned to the bottom. */
  isStuck(): boolean {
    return this.stuck;
  }

  /** Scroll to bottom on the next frame, if stuck. */
  schedule(): void {
    if (!this.stuck) return;
    if (this.rafId !== null) return;
    this.rafId = requestAnimationFrame(() => {
      this.rafId = null;
      if (this.stuck) {
        const el = this.el;
        el.scrollTop = el.scrollHeight - el.clientHeight;
      }
    });
  }

  /** Force scroll to bottom regardless of stuck state. */
  scrollToBottom(): void {
    this.el.scrollTop = this.el.scrollHeight - this.el.clientHeight;
  }

  dispose(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.el.removeEventListener('scroll', this.onScroll);
  }
}
