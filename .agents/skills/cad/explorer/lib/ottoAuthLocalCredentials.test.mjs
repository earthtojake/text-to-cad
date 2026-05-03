import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  readOttoAuthLocalAgentCredential,
  writeOttoAuthLocalAgentCredential,
} from "./ottoAuthLocalCredentials.mjs";

test("writes and reads local OttoAuth linked agent credentials", () => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), "ottoauth-local-agent-"));
  const stored = writeOttoAuthLocalAgentCredential({
    workspaceRoot,
    baseUrl: "http://127.0.0.1:3000",
    env: {},
    payload: {
      ok: true,
      tool_name: "cad-explorer",
      created: true,
      human: {
        id: 7,
        email: "human@example.com",
        display_name: "Human",
        handle: "human",
      },
      agent: {
        id: 12,
        username: "cad_explorer_abc123",
        username_lower: "cad_explorer_abc123",
        description: "CAD Explorer local coding agent",
      },
      private_key: "oa_private_test",
    },
  });

  assert.equal(stored.agent.username, "cad_explorer_abc123");
  assert.equal(stored.credential_path, ".agents/ottoauth.local.json");
  assert.equal(stored.env_path, ".agents/.env.ottoauth.local");

  const credential = readOttoAuthLocalAgentCredential({
    workspaceRoot,
    env: {},
  });
  assert.equal(credential.username, "cad_explorer_abc123");
  assert.equal(credential.privateKey, "oa_private_test");
  assert.match(credential.source, /ottoauth\.local\.json$/);
});

test("prefers explicit OttoAuth agent env credentials", () => {
  const credential = readOttoAuthLocalAgentCredential({
    workspaceRoot: "/does/not/matter",
    env: {
      OTTOAUTH_AGENT_USERNAME: "from_env",
      OTTOAUTH_PRIVATE_KEY: "env_private",
    },
  });

  assert.deepEqual(credential, {
    source: "env",
    username: "from_env",
    privateKey: "env_private",
  });
});
