import { normalizePath } from '@text-to-cad/ui/cad-viewer';
import type { LiveController, LiveRegistry } from './live';
import { TUNNEL_REPLY_MAX_BYTES } from './tunnel';

/**
 * How long an agent's capture waits for its view to show the model it asked about, loaded and drawn:
 * an agent captures right after it showed or rebuilt a model, while the view is still loading it.
 * Within the server's own wait for the answer (`views.CAPTURE_SECONDS`), so the view says why first.
 */
export const CAPTURE_SETTLE_MS = 20_000;
// How often a waiting capture looks again, besides whenever a renderer binds: the view's loading is
// its live state, which nothing announces. A page the host hides runs this timer as its others.
const RECHECK_MS = 100;

/** One file, however it was spelled: the viewer's spelling, a Windows drive's case aside. */
function samePath(a: string | undefined, b: string): boolean {
  if (!a) return false;
  const [x, y] = [normalizePath(a), normalizePath(b)];
  return x === y || (/^[A-Za-z]:\//.test(x) && x.toLowerCase() === y.toLowerCase());
}

/** The mounted view's controller if it shows `model`, whole and drawn, and is not busy; else null. */
function settledOn(live: LiveRegistry, model: string | null): LiveController | null {
  const controller = live.current();
  if (!model || !controller) return null;
  const state = controller.readState();
  return state.active !== false && !state.loading && samePath(state.resource?.path, model) ? controller : null;
}

/**
 * A PNG of what the view shows (`cad_screenshot`), once it shows `model()` — the file the agent
 * last showed in it, else the one on screen — loaded and drawn. A capture asked while the view is
 * still loading or switching waits for it (`CAPTURE_SETTLE_MS`) rather than failing, and one the
 * view's model moved under is taken again. A view with no model fails at once.
 */
export async function captureSettled(live: LiveRegistry, model: () => string | null,
  { timeoutMs = CAPTURE_SETTLE_MS }: { timeoutMs?: number } = {}): Promise<Blob> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const wanted = model();
    if (!wanted) throw new Error('No model is showing in this CAD view.');
    const controller = settledOn(live, wanted);
    if (controller) {
      try {
        return await controller.capture();
      } catch (error) {
        // Still settled on the same model: the failure is the capture's own, and waiting changes nothing.
        if (settledOn(live, model()) === controller) throw error;
      }
    }
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      throw new Error(`${wanted} did not finish loading in this CAD view within ${Math.round(timeoutMs / 1000)} s `
        + '(a large model, a rebuild still running, or a load that failed: the view says which). Capture again once it shows.');
    }
    await new Promise<void>(resolve => {
      let stop = () => {};
      const timer = setTimeout(() => { stop(); resolve(); }, Math.min(RECHECK_MS, remaining));
      stop = live.subscribe(() => { clearTimeout(timer); stop(); resolve(); });
    });
  }
}

/**
 * A view's picture for the agent (`cad_screenshot`), in one message: the server refuses one longer
 * than a reply carries (`TUNNEL_REPLY_MAX_BYTES`), since a host could close the connection on it.
 * A longer PNG is drawn again smaller, by about as much as it is over, until it fits.
 */
export async function fitCapture(png: Blob): Promise<Blob> {
  let fitted = png;
  let scale = 1;
  while (fitted.size > TUNNEL_REPLY_MAX_BYTES && scale > 1 / 64) {
    scale *= 0.9 * Math.sqrt(TUNNEL_REPLY_MAX_BYTES / fitted.size);
    const image = await createImageBitmap(png);
    const canvas = new OffscreenCanvas(Math.max(1, Math.round(image.width * scale)), Math.max(1, Math.round(image.height * scale)));
    canvas.getContext('2d')!.drawImage(image, 0, 0, canvas.width, canvas.height);
    image.close();
    fitted = await canvas.convertToBlob({ type: 'image/png' });
  }
  return fitted;
}
