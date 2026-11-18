import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { xbfMachineJoints, xbfMachinePose } from "@cad/core/lib/xbf/xbfMachine.js";

// How long one wait on the machine holds its request; the engine answers sooner on each new reading.
const WAIT_SECONDS = 20;
// How long the page waits before asking again after a request failed.
const RETRY_MS = 2000;

const IDLE = Object.freeze({ phase: "idle", address: "", state: null, error: null });

/**
 * A machine's twin: Position's joints follow a machine the engine watches (`client.watchMachine`,
 * `cad_server/machines`), each axis on the joint named for it (`xbfMachineJoints`). While it watches,
 * every new reading is written to the pose as a person's would be (`onValues`), and Position takes no
 * edit: the machine is where it is.
 *
 * @param {{ client: object, kinematics: object | null, values: Record<string, number[]> | null,
 *   onValues: (values: Record<string, number[]>) => void }} options
 * @returns {{ mapping, phase: "idle" | "connecting" | "watching", address: string, state: object | null,
 *   error: string | null, pose: ReturnType<typeof xbfMachinePose> | null, watch: (address: string) => void,
 *   stop: () => void, available: boolean }}
 *   `available`: whether the client can watch a machine and the mechanism has a joint for an axis.
 *   `state`: the engine's last word on the watch (`{connected, error, reading}`); `error`: what the
 *   page could not do; `pose`: what the last reading put where, and what it could not.
 */
export function useMachineMirror({ client, kinematics, values, onValues }) {
  const mapping = useMemo(() => xbfMachineJoints(kinematics), [kinematics]);
  const [watching, setWatching] = useState(IDLE);
  const [pose, setPose] = useState(null);
  const valuesRef = useRef(values);
  valuesRef.current = values;
  const onValuesRef = useRef(onValues);
  onValuesRef.current = onValues;
  const mappingRef = useRef(mapping);
  mappingRef.current = mapping;
  const run = useRef(null);

  const end = useCallback(() => {
    const current = run.current;
    run.current = null;
    if (!current) return;
    current.controller.abort();
    if (current.id) void Promise.resolve(client?.unwatchMachine?.(current.id)).catch(() => {});
  }, [client]);

  const watch = useCallback((text) => {
    end();
    const address = String(text || "").trim();
    if (!address || typeof client?.watchMachine !== "function") return;
    const controller = new AbortController();
    const current = { controller, id: null };
    run.current = current;
    setPose(null);
    setWatching({ phase: "connecting", address, state: null, error: null });
    const live = () => run.current === current && !controller.signal.aborted;
    (async () => {
      let version = -1;
      while (live()) {
        try {
          if (!current.id) {
            const started = await client.watchMachine(address, { signal: controller.signal });
            current.id = started.id;
            version = -1;
          }
          const state = await client.machine(current.id, { after: version, wait: WAIT_SECONDS, signal: controller.signal });
          if (!live()) return;
          version = state.version;
          setWatching({ phase: state.connected && state.reading ? "watching" : "connecting", address: state.address || address, state, error: null });
          if (state.reading && valuesRef.current) {
            const next = xbfMachinePose(mappingRef.current, valuesRef.current, state.reading);
            setPose(next);
            onValuesRef.current?.(next.values);
          }
        } catch (error) {
          if (!live()) return;
          const status = error?.failure?.status;
          if (status === 400 || status === 409) {
            // The address itself, or the engine's room for watches: asking again changes nothing.
            run.current = null;
            setWatching({ phase: "idle", address, state: null, error: error?.message || String(error) });
            return;
          }
          if (status === 404) current.id = null; // the engine no longer watches it: watch it again
          setWatching(now => ({ ...now, error: error?.message || String(error) }));
          await new Promise(resolve => setTimeout(resolve, RETRY_MS));
        }
      }
    })();
  }, [client, end]);

  const stop = useCallback(() => {
    end();
    setPose(null);
    setWatching(now => ({ ...IDLE, address: now.address }));
  }, [end]);

  // The view closing ends it. A new build of the twin does not: its joints are matched again
  // (`mappingRef`) and the next reading poses them.
  useEffect(() => () => end(), [end]);

  const available = typeof client?.watchMachine === "function" && (Object.keys(mapping.joints).length > 0 || mapping.refused.length > 0);
  return { mapping, ...watching, pose, watch, stop, available };
}
