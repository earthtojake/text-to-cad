/**
 * Virtualizer — Fenwick-tree (BIT) based scroll virtualization.
 *
 * Maintains per-row pixel heights in a Binary Indexed Tree for O(log n)
 * prefix-sum updates and lookups over potentially 10k+ rows.
 *
 * API:
 *   setCount(n, estimate)  — resize, seeding new rows with estimate(i)
 *   setSize(i, h)          — update row height, returns pixel delta for scroll-anchor correction
 *   top(i)                 — pixel offset of row i from the top (prefix sum [0,i))
 *   total()                — total canvas height
 *   findIndex(offset)      — binary lift: row index at a given pixel offset
 *   range(scrollTop, viewH, before?, after?) — { start, end } of visible rows (inclusive); omit after to use symmetric overscan
 */

export class Virtualizer {
  private n = 0;
  /** Actual per-row sizes (truth). */
  private sizes: Float64Array = new Float64Array(0);
  /** Fenwick BIT: bit[i] = sum over a range ending at i (1-indexed). */
  private bit: Float64Array = new Float64Array(0);
  /** Running sum of all row heights, kept in sync with every mutation. */
  private totalSize = 0;

  // ── Internal BIT operations ─────────────────────────────────────────────────

  private bitUpdate(i: number, delta: number): void {
    // 1-indexed BIT
    for (let j = i + 1; j <= this.n; j += j & -j) {
      this.bit[j] += delta;
    }
  }

  private bitQuery(i: number): number {
    // prefix sum [0, i] (0-indexed row i maps to 1-indexed i+1)
    let s = 0;
    for (let j = i + 1; j > 0; j -= j & -j) {
      s += this.bit[j];
    }
    return s;
  }

  // ── Public API ───────────────────────────────────────────────────────────────

  /**
   * Resize to n rows. New rows are seeded with estimate(i); removed rows are dropped.
   * Existing measured rows keep their sizes.
   */
  setCount(n: number, estimate: (i: number) => number): void {
    const prevN = this.n;
    if (n === prevN) return;

    if (n > prevN) {
      // Grow: existing BIT entries (1-indexed 1..prevN) stay valid, since their
      // ranges never extend past prevN. The *new* high-index nodes, however, can
      // cover ranges that span old rows, so we must build each from its children
      // rather than only adding new rows. Processing new indices in increasing
      // order guarantees every child (old → copied, new → already built) is
      // finalized. Each new node costs O(log n): O(n_new * log n) total, which
      // keeps the streaming append path (one new message per turn) at O(log n).
      const newSizes = new Float64Array(n);
      const newBit = new Float64Array(n + 1);
      newSizes.set(this.sizes.subarray(0, prevN));
      newBit.set(this.bit.subarray(0, prevN + 1));
      this.n = n;
      this.sizes = newSizes;
      this.bit = newBit;
      for (let j = prevN + 1; j <= n; j++) {
        const h = estimate(j - 1);
        newSizes[j - 1] = h;
        this.totalSize += h;
        let s = h;
        const stop = j - (j & -j);
        for (let c = j - 1; c > stop; c -= c & -c) {
          s += newBit[c];
        }
        newBit[j] = s;
      }
    } else {
      // Shrink: keep the first n sizes and rebuild the BIT in a single O(n) pass.
      const newSizes = new Float64Array(n);
      newSizes.set(this.sizes.subarray(0, n));
      this.sizes = newSizes;
      this.n = n;
      this.rebuild();
    }
  }

  /**
   * O(n) Fenwick construction from `this.sizes` (vs n point updates at
   * O(log n) each). Each node adds its own value then propagates into its
   * parent in one forward pass.
   */
  private rebuild(): void {
    const n = this.n;
    const bit = new Float64Array(n + 1);
    const sizes = this.sizes;
    let total = 0;
    for (let i = 1; i <= n; i++) {
      bit[i] += sizes[i - 1];
      total += sizes[i - 1];
      const parent = i + (i & -i);
      if (parent <= n) bit[parent] += bit[i];
    }
    this.bit = bit;
    this.totalSize = total;
  }

  /**
   * Update the height of row i. Returns the signed pixel delta (newH - oldH),
   * which the engine uses for scroll-anchor correction when the row is above
   * the viewport.
   */
  setSize(i: number, h: number): number {
    if (i < 0 || i >= this.n) return 0;
    const old = this.sizes[i];
    const delta = h - old;
    if (delta === 0) return 0;
    this.sizes[i] = h;
    this.bitUpdate(i, delta);
    this.totalSize += delta;
    return delta;
  }

  /** Pixel offset of row i from the canvas top (sum of rows 0..i-1). */
  top(i: number): number {
    if (i <= 0) return 0;
    return this.bitQuery(i - 1);
  }

  /** Total canvas height (sum of all row heights). O(1) — kept as a running sum. */
  total(): number {
    return this.totalSize;
  }

  /** Size of row i. */
  size(i: number): number {
    return i >= 0 && i < this.n ? this.sizes[i] : 0;
  }

  /** Count of rows. */
  get count(): number {
    return this.n;
  }

  /**
   * Binary-lift search: find the row index whose top offset ≤ offset < top+height.
   * Returns 0 for empty or out-of-range.
   */
  findIndex(offset: number): number {
    if (this.n === 0 || offset <= 0) return 0;
    const total = this.total();
    if (offset >= total) return Math.max(0, this.n - 1);

    // Binary lift on the BIT: find smallest i s.t. bit prefix sum > offset
    let idx = 0;
    let bitMask = 1;
    while (bitMask <= this.n) bitMask <<= 1;
    bitMask >>= 1;

    let runningSum = 0;
    while (bitMask > 0) {
      const next = idx + bitMask;
      if (next <= this.n && runningSum + this.bit[next] <= offset) {
        runningSum += this.bit[next];
        idx = next;
      }
      bitMask >>= 1;
    }
    // idx is now the 1-based index of the last row whose cumulative sum ≤ offset
    // so the 0-based row containing offset is idx
    return Math.min(idx, this.n - 1);
  }

  /**
   * Prepend `count` rows at the front of the virtualizer, seeding each with
   * `estimate(i)` where `i` is the logical index within the prepended batch
   * (0 = the first prepended row, count-1 = the last).
   *
   * All existing row sizes are preserved: they shift to indices [count, count+n)
   * and their measured heights remain valid. The BIT is rebuilt in O(n) after
   * the shift — acceptable for user-paced history page-loads.
   *
   * Used by ChatRoot.loadOlder for incremental history loading.
   */
  prepend(count: number, estimate: (i: number) => number): void {
    if (count <= 0) return;
    const newN = this.n + count;
    const newSizes = new Float64Array(newN);
    // Seed the prepended rows with estimates.
    for (let i = 0; i < count; i++) {
      newSizes[i] = estimate(i);
    }
    // Copy existing rows shifted by count.
    newSizes.set(this.sizes.subarray(0, this.n), count);
    this.sizes = newSizes;
    this.n = newN;
    this.rebuild();
  }

  /**
   * Returns inclusive { start, end } row indices visible at [scrollTop, scrollTop+viewH].
   *
   * Two call signatures:
   *   range(scrollTop, viewH, overscan)            — symmetric overscan on both sides
   *   range(scrollTop, viewH, overscanBefore, overscanAfter) — asymmetric (direction-aware)
   *
   * Pass a larger `overscanAfter` when scrolling down (velocity > 0) and a larger
   * `overscanBefore` when scrolling up to pre-buffer in the direction of travel.
   */
  range(
    scrollTop: number,
    viewH: number,
    overscanBefore?: number,
    overscanAfter?: number
  ): { start: number; end: number } {
    if (this.n === 0) return { start: 0, end: -1 };
    const before = overscanBefore ?? 4;
    const after = overscanAfter ?? before; // symmetric when only one arg given
    const start = Math.max(0, this.findIndex(scrollTop) - before);
    const end = Math.min(this.n - 1, this.findIndex(scrollTop + viewH) + after);
    return { start, end };
  }
}
