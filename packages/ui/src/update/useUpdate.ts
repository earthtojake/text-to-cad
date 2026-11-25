import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useI18n } from "../i18n/index.js";
import type { HostAlert } from "../file-viewer/types.js";
import { updateAlert } from "./updateAlert.js";

/**
 * What the update button shows, as the server says it (`GET /api/v1/server`'s `cadUpdate`:
 * `cad_server/_internal/auto_update.py`'s `button`), or null where cad cannot update itself.
 */
export interface UpdateState {
  /** The release this install runs. */
  version: string;
  /** The newer release of its own major the button offers, or null: the install is current (a higher major is never offered). */
  latest: string | null;
  /** `working`: an attempt is underway; `failed`: the last one did not install. */
  state: "idle" | "working" | "failed";
  /** While `working`: `building` (the release installs beside this one), then `switching` (the server restarts onto it); none from an older server. */
  phase?: "building" | "switching";
  /** When the attempt began: what a failure is put away by. */
  at?: number;
  /** Whether a person asked for the attempt (the button, `cad update`), else cad's own automatic update. */
  asked?: boolean;
  /** Why it failed: one word of `auto_update_helper.CAUSES`. */
  cause?: string;
  /** The cause in the server's plain words, said where the page knows no words of its own for it. */
  said?: string;
  /** The helper's log of the attempt, where it kept one: its path on this computer. */
  log?: string;
  /** Who made this install, which a reinstall is told by: `uv` or `pipx`. */
  installer?: string;
  /** The person put the failure away (`dismiss`): every page keeps it behind its icon. */
  dismissed?: boolean;
}

/** `GET /api/v1/server`, and `POST /api/v1/local/update`'s answer: who the server is, and the update. */
export interface UpdateReply {
  release?: string;
  /** This start of the server: another one answering is a server that restarted. */
  instance?: string;
  cadUpdate?: UpdateState | null;
}

/** The host's calls to its server. */
export interface UpdateCalls {
  /** `GET /api/v1/server`, read afresh. */
  read(): Promise<UpdateReply>;
  /** `POST /api/v1/local/update` with `{}`: a person's update. A refusal throws, its body as `failure.payload`. */
  start(): Promise<UpdateReply>;
  /** `POST /api/v1/local/update` with `{dismiss: at}`: the failure put away, for every page. */
  dismiss(at: number): Promise<UpdateReply>;
}

/** Where the button is: offered (`idle`), installing (`working`, its stages done), or the server restarting. */
export type UpdatePhase =
  | { phase: "idle" }
  | { phase: "working"; done: number; total: number }
  | { phase: "restarting" };

/** Why an update did not install, as its alert says it (`updateAlert`). */
export interface UpdateFailure {
  cause: string;
  said?: string;
  /** The attempt it is of: put away on the server by it. None for a refusal no attempt began from. */
  at?: number;
  /** The helper's log of the attempt. */
  log?: string;
  /** Who made this install: `uv` or `pipx`. */
  installer?: string;
  /** Put away: its card behind its icon in the navbar. */
  dismissed?: boolean;
}

/** How often a page asks where an update it follows is. */
export const UPDATE_POLL_MS = 500;
/**
 * The ring's stages: building (the release installs beside this one: asked, and the server's `building` phase),
 * switching (the server restarts onto it), and the server gone meanwhile; then the spinner, the server back and the
 * page reloading.
 */
export const UPDATE_STAGES = 3;

const refusalOf = (error: unknown): UpdateFailure => {
  const payload = (error as { failure?: { payload?: Record<string, unknown> } } | null)?.failure?.payload;
  const text = (value: unknown) => (typeof value === "string" && value ? value : undefined);
  return { cause: text(payload?.cause) ?? "", said: text(payload?.error) ?? (error instanceof Error ? error.message : undefined),
    ...(text(payload?.installer) ? { installer: text(payload?.installer) } : {}) };
};

/**
 * The update button's state, from the host's server: what the host already read with the server's
 * description (`initial`, so the button draws with the page; none: read once), read again whenever the
 * person comes back to the page. `update()` is the click: the server begins a person's update
 * (`start`), and the page asks where it is (`read`) until it ends -- building, then switching, then, the
 * server gone while it restarts, still asking -- and once another start of the server answers
 * (`instance`), the server restarted: `restarting`, and the host's `onRestarted` (a page reloads into
 * it, once nothing it holds is unsaved). An automatic update the page finds underway is followed the
 * same way. A failure is the viewer's alert (`alert`, `CadViewer`'s: `updateAlert`'s card, its Try again the
 * click), from the server's record and so through a reload, until another attempt begins; put away (`dismiss`:
 * its X or Escape) it stays behind its icon in the navbar, on every page and through a reload (the server
 * keeps it put away), and the icon brings it back on this page (`reopen`). A refusal with no attempt (cad
 * cannot update itself) is said the same way, on this page alone, until it is reloaded. A page loaded after
 * it followed an update through the restart (`followed`: the release it was followed from, which the host
 * keeps across the reload) shows the spinner while the update's end is still being written, then its failure -- or, on another release, that it is updated, once,
 * as a toast (`restartForSkills`: a host app that reads a release's skills only in a new session
 * suggests restarting it). A read that fails changes nothing, but while an update is followed it is the
 * server gone for the install.
 */
export function useUpdate(calls: UpdateCalls, initial: UpdateReply | null | undefined,
  { instance, followed = null, onRestarted, restartForSkills = false }: { instance?: string; followed?: string | null;
    onRestarted?: (reply: UpdateReply) => void; restartForSkills?: boolean } = {}) {
  const [state, setState] = useState<UpdateState | null>(initial?.cadUpdate ?? null);
  const [phase, setPhase] = useState<UpdatePhase>({ phase: "idle" });
  const [failure, setFailure] = useState<UpdateFailure | null>(null);
  const polling = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);
  // Whether the page follows an update now: a read that fails is then the server gone for the install.
  const following = useRef(false);
  // A page loaded after the restart its page before followed: the spinner until the update's end is written.
  const after = useRef(Boolean(followed));
  const restarted = useRef(false);
  // The start of the server the page follows, and the release it ran: a restart onto the same release is the update
  // failed and the release before started again, which the page goes on following.
  const server = useRef({ instance, version: initial?.release ?? initial?.cadUpdate?.version ?? "" });
  // The person's own choice on the failure on screen, by its attempt: put away, or brought back from the navbar's icon
  // (on this page alone: the server keeps a failure put away for every page).
  const chosen = useRef<{ at?: number; dismissed: boolean } | null>(null);
  const { t } = useI18n();
  const latest = useRef({ calls, onRestarted, restartForSkills, t });
  latest.current = { calls, onRestarted, restartForSkills, t };

  const stopPolling = () => {
    if (polling.current !== null) clearTimeout(polling.current);
    polling.current = null;
  };
  /** An answer of the server's: whether the page goes on asking. */
  const apply = useCallback((reply: UpdateReply): boolean => {
    if (!alive.current || restarted.current) return false;
    const mine = server.current;
    const release = reply.release ?? reply.cadUpdate?.version ?? "";
    if (following.current && mine.version && release && release !== mine.version) {
      // A server of another release: the update installed it, and the page goes to it.
      restarted.current = true;
      following.current = false;
      setPhase({ phase: "restarting" });
      latest.current.onRestarted?.(reply);
      return false;
    }
    if (following.current && mine.instance && reply.instance && reply.instance !== mine.instance) {
      // The release before, started again: the update failed, and says why once its end is written.
      after.current = true;
    }
    // Another start of the server, or the first a host that read nothing before (a CAD card) hears from.
    server.current = { instance: reply.instance ?? mine.instance, version: mine.version || release };
    const update = reply.cadUpdate ?? null;
    setState(update);
    if (update?.state === "working") {
      following.current = true;
      setFailure(null);
      setPhase(after.current ? { phase: "restarting" }
        : { phase: "working", done: update.phase === "building" ? 0 : 1, total: UPDATE_STAGES });
      return true;
    }
    following.current = false;
    if (update?.state === "failed") {
      const mine = chosen.current && chosen.current.at === update.at ? chosen.current.dismissed : undefined;
      setFailure({ cause: update.cause ?? "", said: update.said, at: update.at,
        ...(update.log ? { log: update.log } : {}), ...(update.installer ? { installer: update.installer } : {}), dismissed: mine ?? update.dismissed === true });
    } else {
      setFailure(current => (current && current.at === undefined ? current : null));
      if (after.current && reply.release && reply.release !== followed) {
        const { restartForSkills: skills, t: say } = latest.current;
        toast.success(say(skills ? "update.updatedRestart" : "update.updated", { version: reply.release }));
      }
    }
    after.current = false;
    setPhase({ phase: "idle" });
    return false;
  }, []);
  const follow = useCallback(() => {
    stopPolling();
    polling.current = setTimeout(() => {
      polling.current = null;
      void latest.current.calls.read().then(reply => { if (apply(reply)) follow(); }, () => {
        if (!alive.current || !following.current) return;
        // The server gone while the update switches: the next stage, and asked again.
        if (!after.current) setPhase({ phase: "working", done: 2, total: UPDATE_STAGES });
        follow();
      });
    }, UPDATE_POLL_MS);
  }, [apply]);
  const read = useCallback(() => {
    void latest.current.calls.read().then(reply => { if (apply(reply) && polling.current === null) follow(); }, () => {});
  }, [apply, follow]);
  const update = useCallback(() => {
    following.current = true;
    after.current = false;
    chosen.current = null;
    setFailure(null);
    setPhase({ phase: "working", done: 0, total: UPDATE_STAGES });
    void latest.current.calls.start().then(reply => { if (apply(reply)) follow(); else following.current = false; }, error => {
      if (!alive.current) return;
      following.current = false;
      setFailure(refusalOf(error));
      setPhase({ phase: "idle" });
    });
  }, [apply, follow]);
  const dismiss = useCallback(() => {
    setFailure(current => {
      if (!current) return current;
      chosen.current = { at: current.at, dismissed: true };
      if (current.at !== undefined) void latest.current.calls.dismiss(current.at).then(apply, () => {});
      return { ...current, dismissed: true };
    });
  }, [apply]);
  const reopen = useCallback(() => {
    setFailure(current => {
      if (!current) return current;
      chosen.current = { at: current.at, dismissed: false };
      return { ...current, dismissed: false };
    });
  }, []);
  // Where the page starts: what the host read, else read now; an update underway is followed from the start (and
  // again where React's strict mode mounts the page a second time).
  const begun = useRef(false);
  const start = useRef(initial);
  useEffect(() => {
    alive.current = true;
    if (!begun.current) {
      begun.current = true;
      if (start.current) { if (apply(start.current)) follow(); } else read();
    } else if (following.current && polling.current === null) follow();
    const back = () => { if (!following.current) read(); };
    window.addEventListener("focus", back);
    return () => { alive.current = false; window.removeEventListener("focus", back); stopPolling(); };
  }, [read]);
  const shown = Boolean(state?.latest) || phase.phase !== "idle";
  const version = state?.latest ?? "";
  const alert = useMemo<HostAlert | null>(() => failure ? { alert: updateAlert(failure, version, t),
    dismissed: Boolean(failure.dismissed), onDismiss: dismiss, onReopen: reopen, ...(version ? { onRetry: update } : {}) } : null,
  [failure, version, t, dismiss, reopen, update]);
  return { state, phase, failure, alert, shown, update, dismiss, reopen };
}
