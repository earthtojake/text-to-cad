import type { ViewerAlert } from "../file-viewer/types.js";
import type { UpdateFailure } from "./useUpdate.js";

// A failed update in the person's words, and as the viewer's alert card says it.

/** The command that updates cad in a terminal, the failure's way on: the same on every computer. */
export const UPDATE_COMMAND = "cad update";
/** The causes the page says in words of its own (`update.cause.<word>`); any other is said by the server's words. */
export const UPDATE_CAUSES = ["timeout", "no_program", "in_use", "denied", "disk_full", "half_made", "network", "offline", "no_release",
  "python", "platform", "config_exclude", "config_index", "config_tls", "uv_old", "kept", "server_running", "helper_start",
  "helper_crash", "lost", "no_installer", "no_python", "packaged", "unknown"] as const;

/**
 * The causes that are cad's own fault, which Report Issue is offered for: an update whose helper could not start,
 * raised, went silent, or met an installer failure cad does not recognize. Every other cause is the person's computer,
 * their installer or its settings, or the package index, and its words say what to do: no issue of the project's (as a
 * model's own error is none: `buildFailedAlert`'s `reportable`).
 */
export const UPDATE_REPORTABLE = ["helper_start", "helper_crash", "lost", "unknown"] as const;

/** A failure in the person's language: why it did not install, and what to do. */
export function failureWords(failure: UpdateFailure, t: (key: string, params?: Record<string, unknown>) => string): string {
  const installer = failure.installer === "pipx" ? "pipx" : failure.installer === "uv" ? "uv" : t("update.installer");
  if ((UPDATE_CAUSES as readonly string[]).includes(failure.cause)) return t(`update.cause.${failure.cause}`, { installer });
  return failure.said || t("update.cause.other");
}

/**
 * A failed update as the viewer's alert card says it (`ViewerAlertCard`, through `CadViewer`'s `alert`), the card every
 * error is said in: an error that blocks nothing (the person works on, and can put it away), "Couldn't update to
 * {version}", why in plain words and what to do (`failureWords`), Retry as "Try again" where there is a release to
 * update to, Report Issue only for cad's own fault (`UPDATE_REPORTABLE`), and in Details the terminal's way on,
 * `cad update`, and where the helper kept one, its log's path (a line a terminal reads as a comment, so the copy
 * pastes and runs).
 */
export function updateAlert(failure: UpdateFailure, version: string, t: (key: string, params?: Record<string, unknown>) => string): ViewerAlert {
  return {
    severity: "error", kind: "update", blocking: false,
    summary: t("update.failed"), title: version ? t("update.failedTo", { version }) : t("update.failed"),
    message: failureWords(failure, t),
    details: [UPDATE_COMMAND, failure.log ? `# The update's log: ${failure.log}` : ""].filter(Boolean).join("\n"),
    ...(version ? { reload: true, retryLabel: t("update.retry") } : {}),
    ...((UPDATE_REPORTABLE as readonly string[]).includes(failure.cause) ? {} : { reportable: false }),
  };
}
