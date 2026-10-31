/**
 * Whether a view just opened takes the keyboard: only where nothing has it (the page's body), and
 * only in a page of its own -- a view in a frame (the CAD app's card in a chat) never pulls the keys
 * away from the host around it.
 * @param {Document} document
 * @param {Window} view
 */
export function mayTakeKeyboard(document, view) {
  let framed = true;
  try { framed = view.top !== view; } catch { /* a frame another origin holds */ }
  const active = document.activeElement;
  return !framed && (!active || active === document.body || active === document.documentElement);
}
