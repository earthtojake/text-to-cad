/**
 * Shiki token → DOM helpers.
 *
 * Imperatively write syntax-highlighted tokens into pre-existing DOM elements.
 * Shared by Code.tsx and Diff.tsx so the highlighting logic is not duplicated.
 */

export type CodeToken = {
  content: string;
  htmlStyle?: Record<string, string>;
};

/**
 * Replace the children of `el` with the provided token array.
 * Plain tokens become text nodes; tokens with `htmlStyle` become styled spans.
 */
export function applyTokensToElement(el: HTMLElement, tokens: CodeToken[]): void {
  while (el.firstChild) el.removeChild(el.firstChild);
  for (const tok of tokens) {
    if (!tok.content) continue;
    if (!tok.htmlStyle) {
      el.appendChild(document.createTextNode(tok.content));
    } else {
      const span = document.createElement('span');
      span.textContent = tok.content;
      for (const [prop, val] of Object.entries(tok.htmlStyle)) {
        span.style.setProperty(prop, val);
      }
      el.appendChild(span);
    }
  }
}

/**
 * Apply a 2D token array (one array per line) to a matching array of line elements.
 * Index i of `lineEls` corresponds to index i of `tokenLines`.
 * Mismatched lengths are handled gracefully (shorter of the two wins).
 */
export function applyTokenLines(lineEls: HTMLElement[], tokenLines: CodeToken[][]): void {
  for (let i = 0; i < lineEls.length; i++) {
    const el = lineEls[i];
    const tokens = tokenLines[i];
    if (!el || !tokens) continue;
    applyTokensToElement(el, tokens);
  }
}
