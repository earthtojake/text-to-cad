import { parseServerLifetimeMs } from "./serverLifetime.mjs";

function requiredValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function parsePort(value, flag) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > 65535) {
    throw new Error(`${flag} must be a TCP port from 1 to 65535`);
  }
  return parsed;
}

export function parseServerArgs(argv = []) {
  const options = {
    port: null,
    host: "",
    shutdownAfterMs: null,
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      options.help = true;
      continue;
    }
    if (arg.startsWith("--root-dir=")) {
      throw new Error("--root-dir has been removed; pass ?dir= in the Viewer URL.");
    }
    if (arg === "--root-dir") {
      throw new Error("--root-dir has been removed; pass ?dir= in the Viewer URL.");
    }
    if (arg.startsWith("--port=")) {
      options.port = parsePort(arg.slice("--port=".length), "--port");
      continue;
    }
    if (arg === "--port") {
      options.port = parsePort(requiredValue(argv, index, arg), arg);
      index += 1;
      continue;
    }
    if (arg.startsWith("--host=")) {
      options.host = arg.slice("--host=".length).trim();
      continue;
    }
    if (arg === "--host") {
      options.host = requiredValue(argv, index, arg).trim();
      index += 1;
      continue;
    }
    if (arg.startsWith("--shutdown-after=")) {
      options.shutdownAfterMs = parseServerLifetimeMs(arg.slice("--shutdown-after=".length), "--shutdown-after");
      continue;
    }
    if (arg === "--shutdown-after") {
      options.shutdownAfterMs = parseServerLifetimeMs(requiredValue(argv, index, arg), arg);
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${arg}`);
  }
  return options;
}

export function serverHelpText() {
  return `Usage: node backend/server.mjs [options]

Options:
  --port <number>    Port to bind. Defaults to 4178.
  --host <host>      Host to bind. Defaults to 127.0.0.1.
  --shutdown-after <time>
                     Shut down after a duration such as 12h, 30m, or 60000.
  -h, --help         Show this help.
`;
}

export function applyServerArgsToEnv({
  argv = [],
  env = process.env,
  cwd = process.cwd(),
} = {}) {
  const args = parseServerArgs(argv);
  const nextEnv = { ...env };
  return { args, env: nextEnv };
}
