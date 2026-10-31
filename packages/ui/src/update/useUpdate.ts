import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useI18n } from "../i18n/index.js";

/** What a CAD app's server says when a newer text-to-cad is out (`cad_server/updates.py`): the release offered, and this install's. */
export interface UpdateNotice {
  /** The release offered. */
  latest: string;
  /** The release this install runs. */
  version: string;
}

/** Where an update a click started is (`cad_server/_internal/update.py`): its last progress frame among the rest. */
export interface UpdateState {
  state: "idle" | "working" | "restarting" | "failed";
  target?: string | null;
  /** The update's progress frame (`cad/engine/progress.py`, kind `update`): its stage, counted of the four. */
  progress?: { stage?: string; done?: number; total?: number | null } | null;
  /** Why it failed, in one line. */
  error?: string | null;
}

/** `GET /__cad/version` (and `POST /__cad/update`, which answers the same): the notice, the engine's release, the update's state. */
export interface UpdateReply {
  notice: UpdateNotice | null;
  release?: string;
  update?: UpdateState | null;
}

/** The host's call to its server: what `GET /__cad/version` answers. */
export type UpdateCall = () => Promise<UpdateReply>;

/** Where the update button is: offered (`idle`), installing (`working`, its share done), or restarting the engine. */
export type UpdatePhase =
  | { phase: "idle" }
  | { phase: "working"; done: number; total: number }
  | { phase: "restarting" };

/** How often a page asks where an update it started is. */
export const UPDATE_POLL_MS = 500;
const STAGES = 4;

/**
 * The update button's state, from the host's server: the notice the host already knew as the page
 * started (`initial`: a CAD app's launch carries it, the web page reads it with its server's
 * description), so the button draws with the page, and read again whenever the person comes back to
 * the page. `update()` is the click: the server updates (`start`, `POST /__cad/update`), and the page
 * asks where it is (`read`) until the engine restarts -- `working`, then `restarting`, which is the
 * host's to follow: the engine goes and comes back with the new release, and the page reloads into
 * it. A failed update the page followed is said once -- its one line, as the viewer's toast (an
 * export's: `sonner`), or to `onFailed` -- and the button is offered again; the engine keeps saying it
 * failed until the next click, and a page that comes back to it later says nothing. A read that fails
 * changes nothing; one while the engine restarts is the restart.
 */
export function useUpdate({ read, start }: { read: UpdateCall; start: UpdateCall },
  initial: UpdateNotice | null, { onFailed }: { onFailed?: (error: string) => void } = {}) {
  const [notice, setNotice] = useState<UpdateNotice | null>(initial);
  const [phase, setPhase] = useState<UpdatePhase>({ phase: "idle" });
  const polling = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);
  // Whether this page follows an update (its click, or another page's it found running): its failure is said.
  const following = useRef(false);
  const { t } = useI18n();
  const failed = useRef(onFailed);
  failed.current = onFailed ?? (error => { toast.error(t("update.failed", { error })); });

  const stopPolling = () => {
    if (polling.current !== null) clearTimeout(polling.current);
    polling.current = null;
  };
  const apply = useCallback((reply: UpdateReply): UpdatePhase["phase"] => {
    if (!alive.current) return "idle";
    setNotice(reply.notice ?? null);
    const update = reply.update;
    if (update?.state === "working") {
      following.current = true;
      const total = Number(update.progress?.total) || STAGES;
      setPhase({ phase: "working", done: Math.min(Number(update.progress?.done) || 0, total), total });
      return "working";
    }
    if (update?.state === "restarting") {
      setPhase({ phase: "restarting" });
      return "restarting";
    }
    if (update?.state === "failed" && following.current) failed.current?.(update.error || "");
    following.current = false;
    setPhase({ phase: "idle" });
    return "idle";
  }, []);
  const follow = useCallback(() => {
    stopPolling();
    polling.current = setTimeout(() => {
      polling.current = null;
      void read().then(reply => { if (apply(reply) === "working") follow(); }, () => follow());
    }, UPDATE_POLL_MS);
  }, [read, apply]);
  const update = useCallback(() => {
    following.current = true;
    setPhase(current => current.phase === "idle" ? { phase: "working", done: 0, total: STAGES } : current);
    void start().then(reply => { if (apply(reply) === "working") follow(); },
      () => { if (alive.current) setPhase({ phase: "idle" }); });
  }, [start, apply, follow]);
  const refresh = useCallback(() => {
    void read().then(reply => {
      // A page opened while an update runs (another tab's click) follows it too.
      if (apply(reply) === "working" && polling.current === null) follow();
    }, () => {});
  }, [read, apply, follow]);
  useEffect(() => {
    alive.current = true;
    window.addEventListener("focus", refresh);
    return () => { alive.current = false; window.removeEventListener("focus", refresh); stopPolling(); };
  }, [refresh]);
  return { notice, phase, update };
}
