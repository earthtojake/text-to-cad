import { useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { fuzzyMatch } from '../../../file-viewer/navigation/fuzzy.js';

/** The scroller a tree sits in (its tool-stack panel's body): a search keeps its place in it. */
const panelScroller = element => element?.closest('[data-tool-panel-body]') ?? element;

/**
 * A tree's filter box: a flat, ranked view over the presented tree, never a
 * filter over its expansion.
 *
 * Expansion belongs to the tree's owner, and opening a row can be expensive for
 * it (what is pickable, what gets loaded), so a search that opened branches to
 * show its hits would load a large tree one keystroke at a time. The index
 * instead reads what the presented tree already holds — every row by name,
 * including rows that arrived under ones opened earlier — and nothing here
 * expands, requests or loads.
 */

/**
 * @typedef {object} ModelTreeSearchEntry
 * @property {object} node The presented tree node, by reference.
 * @property {number} parent Index of the owning entry, or -1 at the top level.
 * @property {string} label
 * @property {string} prefix Ancestor labels joined by `/`, with a trailing `/`; shared between siblings.
 * @property {string} lowerLabel
 * @property {string} lowerPrefix
 * @property {string} reference Lower-case id the node is selected by (`node.selectionId`, e.g. `o1.2`), when it has one.
 * @property {string[]} aliases Other names the row answers to (`node.searchAliases`).
 */

const segment = label => String(label || '').replaceAll('/', '∕');
const NO_ALIASES = Object.freeze([]);

/** Flatten the presented tree once per tree; curves are never rows. */
export function buildModelTreeSearchIndex(tree) {
  /** @type {ModelTreeSearchEntry[]} */
  const entries = [];
  const visit = (nodes, parent, prefix) => {
    for (const node of nodes || []) {
      if (node.kind === 'curve') continue;
      const label = String(node.label || '');
      const at = entries.push({
        node, parent, label, prefix,
        lowerLabel: label.toLowerCase(), lowerPrefix: prefix.toLowerCase(),
        reference: node.selectionId && !node.selectionId.startsWith('__') ? node.selectionId.toLowerCase() : '',
        aliases: Array.isArray(node.searchAliases) ? node.searchAliases.map(String).filter(Boolean) : NO_ALIASES,
      }) - 1;
      if (node.children?.length) visit(node.children, at, `${prefix}${segment(label)}/`);
    }
  };
  visit(tree, -1, '');
  return entries;
}

/** The entry's owners, outermost first, ending with the entry itself. */
export function modelTreeSearchChain(index, at) {
  const chain = [];
  for (let cursor = at; cursor >= 0; cursor = index[cursor].parent) chain.push(index[cursor].node);
  return chain.reverse();
}

// Every token is somewhere in the path and at least one is in the name: `gripper
// m3` finds the M3 screws under Gripper, while `gripper` alone does not return
// everything Gripper owns.
function tokenMatch(tokens, entry) {
  const indices = [];
  let inLabel = 0, score = 0;
  for (const token of tokens) {
    const at = entry.lowerLabel.indexOf(token);
    if (at >= 0) {
      inLabel += 1;
      score += (at === 0 || /[\s\-_.]/.test(entry.lowerLabel[at - 1]) ? 10 : 6) + token.length;
      for (let offset = 0; offset < token.length; offset += 1) indices.push(at + offset);
    } else if (entry.lowerPrefix.includes(token)) score += 2;
    else return null;
  }
  return inLabel ? { score, indices } : null;
}

/**
 * Rank the index against `query`, best first; ties keep tree order.
 *
 * @returns {{ matches: { at: number, entry: ModelTreeSearchEntry, indices: number[], alias?: { text: string, indices: number[] } }[], total: number }}
 *   `indices` highlight `entry.label`; a hit on another name carries that `alias` and its own
 *   highlight instead. `total` counts every match, `matches` the first `limit`.
 */
export function searchModelTree(index, query, limit = 200) {
  const needle = String(query || '').trim().replace(/^#/, '');
  if (!needle) return { matches: [], total: 0 };
  const lower = needle.toLowerCase();
  const tokens = lower.split(/\s+/).filter(Boolean);
  const scored = [];
  for (let at = 0; at < index.length; at += 1) {
    const entry = index[at];
    // A pasted reference (`#o1.2`) names one row; nothing outranks it.
    if (entry.reference === lower) { scored.push({ at, entry, indices: [], score: 1000 }); continue; }
    // The whole query against the name first, as the file filter reads a
    // filename: `m3scr` finds `M3 Screw`. Names are short, so a subsequence
    // there is a real hit rather than letters scattered across a path.
    const named = fuzzyMatch(needle, entry.label);
    if (named) { scored.push({ at, entry, indices: named.indices, score: named.score + 20 }); continue; }
    const pathed = tokens.length > 1 ? tokenMatch(tokens, entry) : null;
    if (pathed) { scored.push({ at, entry, ...pathed }); continue; }
    // Another name for the same row, read like the name but ranked behind it.
    let alias = null;
    for (const text of entry.aliases) {
      const hit = fuzzyMatch(needle, text);
      if (hit && (!alias || hit.score > alias.score)) alias = { text, indices: hit.indices, score: hit.score };
    }
    if (alias) { scored.push({ at, entry, indices: [], alias: { text: alias.text, indices: alias.indices }, score: alias.score + 10 }); continue; }
    if (entry.reference && entry.reference.includes(lower)) {
      scored.push({ at, entry, indices: [], score: 4 });
    }
  }
  scored.sort((left, right) => right.score - left.score || left.at - right.at);
  return { matches: scored.slice(0, limit).map(({ at, entry, indices, alias }) => (alias ? { at, entry, indices, alias } : { at, entry, indices })), total: scored.length };
}

const NO_MATCHES = Object.freeze({ matches: Object.freeze([]), total: 0 });

/**
 * A tree's filter box, as one hook for every file tree that has one: the query, the ranked
 * hits over `roots` (indexed only while there is a query, and searched at deferred
 * priority), the keyboard cursor over them, and the scroll position the tree had when the
 * search began, put back when it ends.
 *
 * The tree renders the hits into `listRef`'s element; each hit row carries
 * `data-search-row={node.id}`, and Enter presses that row's `button[aria-pressed]`.
 *
 * @param {object[]} roots The presented tree's top-level nodes.
 */
export function useTreeSearch(roots) {
  const [query, setQuery] = useState(''), [cursor, setCursor] = useState(null);
  const searching = query.trim() !== '', deferredQuery = useDeferredValue(query);
  const index = useMemo(() => (searching ? buildModelTreeSearchIndex(roots) : null), [searching, roots]);
  const found = useMemo(() => (index ? searchModelTree(index, deferredQuery) : NO_MATCHES), [index, deferredQuery]);
  const listRef = useRef(null), resumeScroll = useRef(0);
  const changeQuery = value => {
    if (!searching && value.trim() && listRef.current) resumeScroll.current = panelScroller(listRef.current).scrollTop;
    setQuery(value); setCursor(null);
  };
  // Back where the tree was; a hit selected meanwhile is then scrolled to by the tree's own reveal.
  useLayoutEffect(() => { if (!searching && listRef.current) panelScroller(listRef.current).scrollTop = resumeScroll.current; }, [searching]);
  const cursorId = found.matches.some(match => match.entry.node.id === cursor) ? cursor : found.matches[0]?.entry.node.id ?? null;
  useEffect(() => { if (cursorId) listRef.current?.querySelector(`[data-search-row="${CSS.escape(cursorId)}"]`)?.scrollIntoView?.({ block: 'nearest' }); }, [cursorId]);
  const onKeyDown = event => {
    if (event.key === 'Escape' && query) { event.preventDefault(); event.stopPropagation(); changeQuery(''); return; }
    if (!found.matches.length) return;
    const at = found.matches.findIndex(match => match.entry.node.id === cursorId);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor(found.matches[Math.min(Math.max(at + (event.key === 'ArrowDown' ? 1 : -1), 0), found.matches.length - 1)].entry.node.id);
    } else if (event.key === 'Enter' && at >= 0) {
      event.preventDefault();
      listRef.current?.querySelector(`[data-search-row="${CSS.escape(cursorId)}"] button[aria-pressed]:not(:disabled)`)?.click();
    }
  };
  return { query, searching, deferredQuery, index, found, cursorId, listRef, changeQuery, onKeyDown };
}
