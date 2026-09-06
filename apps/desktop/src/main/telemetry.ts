/**
 * Anonymous usage counts, off unless two separate things are true: a build-
 * time key (`HARDCORE_APTABASE_KEY`) and the user's own `telemetry` setting,
 * which defaults to false (plan §10).
 *
 * Without the key this module is inert — a development checkout and a
 * community build send nothing, and no network call is even attempted.
 * Nothing here ever carries a path, a prompt, a file name or a project name.
 */
import { initialize, trackEvent } from "@aptabase/electron/main";

import { settings } from "./db/repositories";

const APTABASE_KEY = process.env.HARDCORE_APTABASE_KEY ?? "";

let initialized = false;

/**
 * Called once at startup, after the database is open. The app version reaches
 * Aptabase from `app.getVersion()` on its own; nothing is passed here beyond
 * the key.
 */
export function initTelemetry() {
  if (!APTABASE_KEY) {
    return;
  }
  void initialize(APTABASE_KEY);
  initialized = true;
}

/**
 * Record an event, if telemetry is both configured and switched on.
 *
 * The setting is read per call rather than cached: turning telemetry off in
 * Settings has to stop the next event, not the next launch.
 */
export function track(event: string, props?: Record<string, string | number | boolean>) {
  if (!initialized) {
    return;
  }
  try {
    if (!settings.get().telemetry) {
      return;
    }
    void trackEvent(event, props);
  } catch (error) {
    // Telemetry must never be able to take the app down.
    console.warn("[telemetry] dropped event", event, error);
  }
}

/** True when a key was compiled in — Settings shows the switch either way. */
export function telemetryAvailable() {
  return Boolean(APTABASE_KEY);
}
