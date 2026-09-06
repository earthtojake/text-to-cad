let hostElement: HTMLDivElement | null = null;

export function ensureXtermHost(): HTMLDivElement {
  if (hostElement && hostElement.isConnected) return hostElement;
  const el = document.createElement('div');
  el.setAttribute('data-terminal-host', 'true');
  Object.assign(el.style, {
    position: 'fixed',
    left: '-10000px',
    top: '0px',
    width: '1px',
    height: '1px',
    overflow: 'hidden',
    pointerEvents: 'none',
    zIndex: '-1',
  } as CSSStyleDeclaration);
  document.body.appendChild(el);
  hostElement = el;
  return el;
}
