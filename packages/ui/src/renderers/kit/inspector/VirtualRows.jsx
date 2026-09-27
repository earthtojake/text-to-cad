import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

const EMPTY = [];
// Rows mounted before the list is measured, and while it cannot be (jsdom, a hidden panel).
const INITIAL_ROWS = 60;
export const VIRTUAL_ROWS_OVERSCAN = 12;

function scrollerOf(element) {
  const panel = element.closest('[data-tool-panel-body]');
  if (panel) return panel;
  for (let node = element.parentElement; node; node = node.parentElement) {
    if (/(auto|scroll|overlay)/.test(getComputedStyle(node).overflowY)) return node;
  }
  return null;
}

/**
 * A long list of fixed-height rows (a tree's rows, flattened), of which only the rows in view —
 * and a margin either side — are mounted. The list keeps the height every row would take and
 * places each mounted row where it would sit, so its scroller's height, scroll range and every
 * row's position are the full list's: what is drawn cannot tell the difference.
 *
 * The scroller is the list's tool-stack panel body (`[data-tool-panel-body]`), else the nearest
 * scrolling ancestor, else the window. The window follows it on scroll and resize, and is
 * brought up to date before the browser paints, so no scrolled-to row is ever missing. A list
 * with no layout (a folded or hidden panel) keeps the rows it had.
 *
 * `pinned` rows stay mounted wherever they are (the selection's row, a search cursor), and so
 * do a focused row and the row whose context menu was last opened, so a row being revealed,
 * pressed from the keyboard, holding focus or holding its menu open is always there. `onVisibleRange(first, last)` is told which rows are on screen, without the
 * margin, whenever that changes (and again when the callback itself changes); nothing is
 * reported while the list has no layout.
 *
 * @param {{ count: number, rowHeight: number, rowKey: (index: number) => string,
 *   rowProps?: (index: number) => object, renderRow: (index: number) => import('react').ReactNode,
 *   pinned?: number[], overscan?: number, onVisibleRange?: ((first: number, last: number) => void) | null,
 *   registerRow?: ((key: string, element: HTMLElement | null) => void) | null } & object} props
 */
export default function VirtualRows({ count, rowHeight, rowKey, rowProps = null, renderRow, pinned = EMPTY,
  overscan = VIRTUAL_ROWS_OVERSCAN, onVisibleRange = null, registerRow = null, style, ...props }) {
  const list = useRef(null);
  const [range, setRange] = useState(() => ({ first: 0, last: Math.min(count, INITIAL_ROWS) - 1 }));
  // Rows in use off the window's edge: the one holding focus, and the last one whose context menu
  // was opened (its menu stays open while the tree changes around it).
  const [focusedKey, setFocusedKey] = useState(null), [menuKey, setMenuKey] = useState(null);
  const latest = useRef(null);
  latest.current = { count, rowHeight, overscan, onVisibleRange };
  const reported = useRef(null), pendingReport = useRef(null);

  // Where the list is in view: the rows on screen, then the rows to mount around them. The
  // mounted window moves only once the view nears its edge, so a scroll re-renders every few rows.
  const measure = useCallback((sync = false, force = false) => {
    const element = list.current;
    const { count, rowHeight, overscan, onVisibleRange } = latest.current;
    if (!element) return;
    const scroller = scrollerOf(element);
    const laidOut = element.getClientRects().length > 0 && (scroller ? scroller.clientHeight > 0 : window.innerHeight > 0);
    if (!laidOut) {
      // Nothing to measure: keep the rows it had, grown to a first screenful if it had fewer.
      reported.current = null;
      setRange(current => {
        const first = current.first < count ? current.first : 0;
        const last = Math.min(count, first + Math.max(INITIAL_ROWS, current.last - current.first + 1)) - 1;
        return first === current.first && last === current.last ? current : { first, last };
      });
      return;
    }
    const box = element.getBoundingClientRect();
    const viewTop = scroller ? scroller.getBoundingClientRect().top + scroller.clientTop : 0;
    const viewHeight = scroller ? scroller.clientHeight : window.innerHeight;
    const top = viewTop - box.top;
    const first = Math.max(0, Math.floor(top / rowHeight)), last = Math.min(count - 1, Math.ceil((top + viewHeight) / rowHeight) - 1);
    const update = current => {
      const empty = count === 0 || last < first;
      if (empty) return current.first === 0 && current.last === -1 ? current : { first: 0, last: -1 };
      const margin = Math.floor(overscan / 2);
      if (current.first <= Math.max(0, first - margin) && current.last >= Math.min(count - 1, last + margin)
        && current.last < count && current.last - current.first <= last - first + 3 * overscan) return current;
      return { first: Math.max(0, first - overscan), last: Math.min(count - 1, last + overscan) };
    };
    if (sync) flushSync(() => setRange(update)); else setRange(update);
    if (onVisibleRange) scheduleReport(force);
  }, []);

  // What is on screen is told once layout has settled, a frame later (or sooner when frames are
  // not running): a panel measures and bounds itself in its own layout pass, and until it has, a
  // list on mount can read every row as in view.
  const scheduleReport = useCallback(force => {
    if (pendingReport.current) { pendingReport.current.force ||= force; return; }
    const pending = { force };
    const run = () => {
      if (pendingReport.current !== pending) return;
      pendingReport.current = null;
      if (pending.frame !== undefined) cancelAnimationFrame(pending.frame);
      clearTimeout(pending.timeout);
      report(pending.force);
    };
    pending.frame = typeof requestAnimationFrame === 'function' ? requestAnimationFrame(run) : undefined;
    pending.timeout = setTimeout(run, 100);
    pendingReport.current = pending;
  }, []);
  const report = force => {
    const element = list.current;
    const { count, rowHeight, onVisibleRange } = latest.current;
    if (!element || !onVisibleRange) return;
    const scroller = scrollerOf(element);
    if (!(element.getClientRects().length > 0 && (scroller ? scroller.clientHeight > 0 : window.innerHeight > 0))) return;
    const box = element.getBoundingClientRect();
    const viewTop = scroller ? scroller.getBoundingClientRect().top + scroller.clientTop : 0;
    const viewHeight = scroller ? scroller.clientHeight : window.innerHeight;
    const top = viewTop - box.top;
    const first = Math.max(0, Math.floor(top / rowHeight)), last = Math.min(count - 1, Math.ceil((top + viewHeight) / rowHeight) - 1);
    const key = last >= first ? `${first}:${last}` : '';
    if (key && (force || reported.current?.key !== key || reported.current?.callback !== onVisibleRange)) {
      reported.current = { key, callback: onVisibleRange };
      onVisibleRange(first, last);
    }
  };
  useLayoutEffect(() => () => {
    const pending = pendingReport.current;
    pendingReport.current = null;
    if (pending) { if (pending.frame !== undefined) cancelAnimationFrame(pending.frame); clearTimeout(pending.timeout); }
  }, []);

  // Before paint whenever the rows or the report change; on scroll and resize before the frame
  // that shows them.
  useLayoutEffect(() => { measure(false, true); }, [measure, count, rowHeight, onVisibleRange]);
  useLayoutEffect(() => {
    const element = list.current;
    const scroller = element && scrollerOf(element);
    const target = scroller || window;
    const onScroll = () => measure(true);
    target.addEventListener('scroll', onScroll, { passive: true });
    let observer = null;
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => measure(true));
      if (scroller) observer.observe(scroller);
      observer.observe(element);
    } else window.addEventListener('resize', onScroll);
    return () => { target.removeEventListener('scroll', onScroll); observer?.disconnect(); if (!observer) window.removeEventListener('resize', onScroll); };
  }, [measure]);

  // One ref callback per row key, so a re-render does not detach and re-attach every row.
  const refs = useRef(new Map());
  const registered = useRef(registerRow);
  registered.current = registerRow;
  const refFor = key => {
    let callback = refs.current.get(key);
    if (!callback) {
      callback = element => { registered.current?.(key, element); if (!element) refs.current.delete(key); };
      refs.current.set(key, callback);
    }
    return callback;
  };

  const first = Math.max(0, range.first), last = Math.min(count - 1, range.last);
  const indices = [];
  for (let index = first; index <= last; index += 1) indices.push(index);
  const extra = new Set(pinned.filter(index => Number.isInteger(index) && index >= 0 && index < count && (index < first || index > last)));
  if (focusedKey !== null || menuKey !== null) {
    for (let index = 0; index < count; index += 1) {
      const key = rowKey(index);
      if ((key === focusedKey || key === menuKey) && (index < first || index > last)) extra.add(index);
    }
  }
  if (extra.size) { indices.push(...extra); indices.sort((a, b) => a - b); }

  return <ul ref={list} {...props} style={{ ...style, position: 'relative', height: count * rowHeight }}
    onFocus={event => {
      const row = event.target.closest?.('[data-virtual-row]');
      if (row && list.current?.contains(row)) setFocusedKey(row.dataset.virtualRow);
      props.onFocus?.(event);
    }}
    onContextMenu={event => {
      const row = event.target.closest?.('[data-virtual-row]');
      if (row && list.current?.contains(row)) setMenuKey(row.dataset.virtualRow);
      props.onContextMenu?.(event);
    }}
    onBlur={event => {
      if (!event.relatedTarget || !list.current?.contains(event.relatedTarget)) setFocusedKey(null);
      props.onBlur?.(event);
    }}>
    {indices.map(index => {
      const key = rowKey(index);
      const own = rowProps ? rowProps(index) : null;
      return <li key={key} ref={registerRow ? refFor(key) : undefined} data-virtual-row={key} {...own}
        style={{ ...own?.style, position: 'absolute', top: index * rowHeight, left: 0, right: 0 }}>{renderRow(index)}</li>;
    })}
  </ul>;
}
