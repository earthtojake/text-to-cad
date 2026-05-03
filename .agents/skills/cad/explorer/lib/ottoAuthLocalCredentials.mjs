import fs from "node:fs";
import path from "node:path";

export const OTTOAUTH_LOCAL_AGENT_JSON = ".agents/ottoauth.local.json";
export const OTTOAUTH_LOCAL_AGENT_ENV = ".agents/.env.ottoauth.local";

function normalizeText(value) {
  return String(value || "").trim();
}

function maybeRelative(workspaceRoot, targetPath) {
  const relative = path.relative(workspaceRoot, targetPath);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    return targetPath;
  }
  return relative;
}

export function resolveOttoAuthLocalCredentialPaths(workspaceRoot, env = process.env) {
  const root = path.resolve(workspaceRoot || process.cwd());
  return {
    jsonPath: path.resolve(
      root,
      normalizeText(env.OTTOAUTH_LOCAL_AGENT_FILE) || OTTOAUTH_LOCAL_AGENT_JSON
    ),
    envPath: path.resolve(
      root,
      normalizeText(env.OTTOAUTH_LOCAL_AGENT_ENV_FILE) || OTTOAUTH_LOCAL_AGENT_ENV
    ),
  };
}

function extractCredential(payload = {}) {
  const agent = payload.agent && typeof payload.agent === "object" ? payload.agent : {};
  const username =
    normalizeText(payload.username) ||
    normalizeText(agent.username) ||
    normalizeText(agent.username_display) ||
    normalizeText(agent.username_lower);
  const privateKey =
    normalizeText(payload.private_key) ||
    normalizeText(payload.privateKey) ||
    normalizeText(payload.credentials?.private_key) ||
    normalizeText(payload.credentials?.privateKey);
  if (!username || !privateKey) {
    return null;
  }
  return {
    username,
    privateKey,
    agent: {
      id: agent.id ?? null,
      username,
      username_lower: normalizeText(agent.username_lower) || username.toLowerCase(),
      description: normalizeText(agent.description),
    },
  };
}

function quoteEnv(value) {
  return JSON.stringify(String(value || ""));
}

export function writeOttoAuthLocalAgentCredential({
  workspaceRoot,
  payload,
  baseUrl,
  env = process.env,
}) {
  const root = path.resolve(workspaceRoot || process.cwd());
  const credential = extractCredential(payload);
  if (!credential) {
    throw new Error("OttoAuth did not return a usable linked agent credential.");
  }

  const paths = resolveOttoAuthLocalCredentialPaths(root, env);
  fs.mkdirSync(path.dirname(paths.jsonPath), { recursive: true });
  fs.mkdirSync(path.dirname(paths.envPath), { recursive: true });

  const record = {
    schema_version: 1,
    ottoauth_base_url: normalizeText(baseUrl),
    tool_name: normalizeText(payload.tool_name) || "cad-explorer",
    created: Boolean(payload.created),
    saved_at: new Date().toISOString(),
    human: payload.human && typeof payload.human === "object"
      ? {
          id: payload.human.id ?? null,
          email: normalizeText(payload.human.email),
          display_name: normalizeText(payload.human.display_name),
          handle: normalizeText(payload.human.handle),
        }
      : null,
    agent: credential.agent,
    credentials: {
      username: credential.username,
      private_key: credential.privateKey,
    },
  };

  fs.writeFileSync(paths.jsonPath, `${JSON.stringify(record, null, 2)}\n`, { mode: 0o600 });
  fs.writeFileSync(
    paths.envPath,
    [
      `OTTOAUTH_BASE_URL=${quoteEnv(record.ottoauth_base_url)}`,
      `OTTOAUTH_AGENT_USERNAME=${quoteEnv(credential.username)}`,
      `OTTOAUTH_PRIVATE_KEY=${quoteEnv(credential.privateKey)}`,
      "",
    ].join("\n"),
    { mode: 0o600 }
  );

  return {
    ok: true,
    created: Boolean(payload.created),
    tool_name: record.tool_name,
    human: record.human,
    agent: record.agent,
    credential_path: maybeRelative(root, paths.jsonPath),
    env_path: maybeRelative(root, paths.envPath),
  };
}

export function readOttoAuthLocalAgentCredential({
  workspaceRoot,
  env = process.env,
} = {}) {
  const username =
    normalizeText(env.OTTOAUTH_AGENT_USERNAME) ||
    normalizeText(env.OTTOAUTH_USERNAME);
  const privateKey = normalizeText(env.OTTOAUTH_PRIVATE_KEY);
  if (username && privateKey) {
    return {
      source: "env",
      username,
      privateKey,
    };
  }

  const root = path.resolve(workspaceRoot || process.cwd());
  const paths = resolveOttoAuthLocalCredentialPaths(root, env);
  if (!fs.existsSync(paths.jsonPath)) {
    return null;
  }

  const parsed = JSON.parse(fs.readFileSync(paths.jsonPath, "utf8"));
  const credential = extractCredential(parsed);
  if (!credential) {
    return null;
  }

  return {
    source: paths.jsonPath,
    username: credential.username,
    privateKey: credential.privateKey,
  };
}
