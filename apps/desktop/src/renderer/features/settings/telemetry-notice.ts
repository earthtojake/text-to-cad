import { toast } from "sonner";

import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import type { TelemetryStatus } from "@shared/ipc/telemetry";
import type { Settings } from "@shared/types";

/**
 * The first-launch notice: what telemetry sends, said once, before anything
 * is sent (`src/main/telemetry.ts`, "Nothing before the person has been told").
 *
 * A toast rather than a step in the welcome, because the welcome is for new
 * installs and this has to reach everyone once — a person upgrading from a
 * build without the notice has never been told either. It says the four
 * events in a line, offers Turn off, and Details opens Settings › General,
 * where the same list is printed with what each event carries. Showing it is
 * what flips `telemetryNoticeShown`; the queued events go out on that flip,
 * or are dropped if Turn off was pressed first.
 */

/** The events, as one line: what the notice says. */
export const TELEMETRY_NOTICE_TEXT =
  "Anonymous usage counts are on: launches, sessions started (which agent), file types opened, and the names of settings changed. Never a file name, a path, a prompt or an output.";

/**
 * Whether to show it: telemetry can send in this build and environment, the
 * person has not turned it off, and the notice has not been shown. Pure, for
 * the test.
 */
export function shouldShowTelemetryNotice(status: TelemetryStatus | null, settings: Settings | null): boolean {
  return Boolean(status?.available && settings && settings.telemetry && !settings.telemetryNoticeShown);
}

/** Called once after the first hydration. */
export async function showTelemetryNoticeIfNeeded(): Promise<void> {
  let status: TelemetryStatus;
  try {
    status = await window.textToCad.telemetry.status();
  } catch {
    return;
  }
  const { settings, patch } = useSettings.getState();
  if (!shouldShowTelemetryNotice(status, settings)) return;
  toast("text-to-cad shares usage data", {
    description: TELEMETRY_NOTICE_TEXT,
    duration: 20_000,
    action: {
      label: "Turn off",
      onClick: () => void patch({ telemetry: false, telemetryNoticeShown: true }),
    },
    cancel: {
      label: "Details",
      onClick: () => useUi.getState().openSettings("general"),
    },
  });
  // Shown is shown: the events that waited for this go out now.
  void patch({ telemetryNoticeShown: true });
}
