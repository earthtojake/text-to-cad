export const MAX_SERVER_LIFETIME_MS = 2_147_483_647;

export function parseServerLifetimeMs(value, flag = "--shutdown-after") {
  const rawValue = String(value ?? "").trim().toLowerCase();
  const match = /^(\d+(?:\.\d+)?)(ms|s|m|h)?$/.exec(rawValue);
  if (!match) {
    throw new Error(`${flag} must be a positive duration such as 30m, 2h, or 43200000.`);
  }

  const amount = Number.parseFloat(match[1]);
  const unit = match[2] || "ms";
  const multiplier = {
    ms: 1,
    s: 1000,
    m: 60 * 1000,
    h: 60 * 60 * 1000,
  }[unit];
  const parsed = Math.round(amount * multiplier);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > MAX_SERVER_LIFETIME_MS) {
    throw new Error(`${flag} must be between 1ms and ${MAX_SERVER_LIFETIME_MS}ms.`);
  }
  return parsed;
}

export function normalizeServerLifetimeMs(value, defaultMs = null) {
  const rawValue = String(value ?? "").trim();
  if (!rawValue) {
    return defaultMs;
  }
  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > MAX_SERVER_LIFETIME_MS) {
    return defaultMs;
  }
  return parsed;
}

export function formatServerLifetime(ms) {
  if (ms % (60 * 60 * 1000) === 0) {
    return `${ms / (60 * 60 * 1000)}h`;
  }
  if (ms % (60 * 1000) === 0) {
    return `${ms / (60 * 1000)}m`;
  }
  if (ms % 1000 === 0) {
    return `${ms / 1000}s`;
  }
  return `${ms}ms`;
}

export function closeHttpServer(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}

export function scheduleProcessShutdown({
  lifetimeMs,
  label = "CAD Viewer server",
  close = async () => {},
} = {}) {
  const normalizedLifetimeMs = normalizeServerLifetimeMs(lifetimeMs);
  if (normalizedLifetimeMs === null) {
    return null;
  }
  const timer = setTimeout(() => {
    console.log(`${label} reached ${formatServerLifetime(normalizedLifetimeMs)} lifetime; shutting down.`);
    const forceExit = setTimeout(() => process.exit(0), 5000);
    forceExit.unref?.();
    Promise.resolve()
      .then(() => close())
      .then(
        () => process.exit(0),
        (error) => {
          console.error(`${label} shutdown failed: ${error instanceof Error ? error.message : String(error)}`);
          process.exit(1);
        }
      );
  }, normalizedLifetimeMs);
  timer.unref?.();
  return timer;
}
