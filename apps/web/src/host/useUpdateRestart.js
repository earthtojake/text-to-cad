import { useEffect, useRef } from "react";
import { RECONNECT_UPDATE_MS } from "./useEngineReconnect.js";

/**
 * A page that follows its update through the engine's restart (`restarting`: `useUpdate`'s phase,
 * after which `useUpdate` reads nothing more) asks the server on its own, every
 * `RECONNECT_UPDATE_MS`, whatever its other reads met, until the restart is over:
 *
 * - an answer from another start of the engine (`instance`) or of another release (`release`) is the
 *   engine that followed -- the new release's, or the release before's once a failed switch went
 *   back -- and the page reloads into it (`reload`: `reloadWhenClean`), where the update's end is
 *   said (`followedUpdate`);
 * - an answer of the page's own engine whose update `failed` ends the restart there (`settle`:
 *   `useUpdate`'s -- the toast, the button offered again);
 * - anything else -- the same engine still `working` or `restarting`, an engine draining, nothing
 *   answering, an error -- and it asks again.
 *
 * It does not wait for a request of the page's to fail first, as `useEngineReconnect` does (`gone`):
 * an engine that goes and comes back between two of the page's reads leaves nothing to fail, and a
 * tab that already has focus hears no focus event.
 *
 * @param {boolean} restarting
 * @param {{ instance: unknown, release?: string,
 *   ask: () => Promise<{ instance?: unknown, release?: string, update?: { state?: string } | null } | null>,
 *   reload: () => void, settle: (answer: any) => void,
 *   schedule?: (run: () => void, delayMs: number) => unknown, cancel?: (handle: unknown) => void }} options
 */
export function useUpdateRestart(restarting, {
  instance,
  release = "",
  ask,
  reload,
  settle,
  schedule = (run, delayMs) => setTimeout(run, delayMs),
  cancel = (handle) => clearTimeout(handle)
}) {
  const optionsRef = useRef(null);
  optionsRef.current = { instance, release, ask, reload, settle, schedule, cancel };

  useEffect(() => {
    if (!restarting) {
      return undefined;
    }
    const loop = { active: true, timer: null };
    const wait = () => {
      loop.timer = optionsRef.current.schedule(attempt, RECONNECT_UPDATE_MS);
    };
    const attempt = async () => {
      loop.timer = null;
      const answer = await Promise.resolve().then(() => optionsRef.current.ask()).catch(() => null);
      if (!loop.active) {
        return;
      }
      const options = optionsRef.current;
      if (answer && typeof answer === "object" && answer.instance) {
        const released = Boolean(options.release && answer.release && answer.release !== options.release);
        if (answer.instance !== options.instance || released) {
          loop.active = false;
          options.reload();
          return;
        }
        if (answer.update?.state === "failed") {
          loop.active = false;
          options.settle(answer);
          return;
        }
      }
      wait();
    };
    wait();
    return () => {
      loop.active = false;
      if (loop.timer !== null) {
        optionsRef.current.cancel(loop.timer);
      }
    };
  }, [restarting]);
}
