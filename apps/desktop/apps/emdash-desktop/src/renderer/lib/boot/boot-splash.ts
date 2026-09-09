/**
 * Controller for the static boot splash that ships in index.html. The markup
 * and its theme-correct colors paint before any bundle executes; this module
 * only wires behavior: the watchdog escape hatch and the dismiss transition.
 */

const SPLASH_ID = 'boot-splash';
const ESCAPE_ID = 'boot-splash-escape';

function splashElement(): HTMLElement | null {
  return document.getElementById(SPLASH_ID);
}

/**
 * Subscribes the escape hatch to the main-process boot watchdog and wires its
 * actions. The hatch cannot ride the wire — a hung backend may never register
 * controllers — so both directions use direct preload channels.
 */
export function initBootSplash(): void {
  if (!splashElement()) return;
  window.electronAPI.onBootStuck(() => showBootSplashEscapeHatch());
  document.getElementById('boot-splash-restart')?.addEventListener('click', () => {
    void window.electronAPI.requestBootEscape('restart');
  });
  document.getElementById('boot-splash-recovery')?.addEventListener('click', () => {
    void window.electronAPI.requestBootEscape('open-recovery');
  });
}

/**
 * Reveals the "taking too long" escape hatch. Only called when the boot
 * watchdog trips or the renderer bootstrap fails fatally; a splash that has
 * already lifted means the user has real UI, so this becomes a no-op.
 */
export function showBootSplashEscapeHatch(): void {
  const splash = splashElement();
  if (!splash || splash.classList.contains('boot-splash-done')) return;
  document.getElementById(ESCAPE_ID)?.removeAttribute('hidden');
}

/** Fades the splash out and removes it from the DOM. */
export function dismissBootSplash(): void {
  const splash = splashElement();
  if (!splash) return;
  splash.classList.add('boot-splash-done');
  splash.addEventListener('transitionend', () => splash.remove(), { once: true });
  // Fallback removal in case the transition never fires (display: none tab, reduced motion).
  window.setTimeout(() => splash.remove(), 400);
}
