import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  activateAgentViewerWorkspace,
  agentViewerUrl,
  buildAgentViewerGit,
  buildAgentStartCommand,
  forwardedDefaultRootDir,
  forwardedServerTarget,
  normalizeAgentWorkspaceDir,
  isReusableAgentViewerServer,
  parseAgentStartArgs,
  probeAgentViewerPort,
  replaceForwardedPort,
  resolveAgentStartLaunch,
  resolveAgentStartCommand,
  resolveAgentViewerPort,
  selectAgentStartMode,
  stripDefaultRootDirArgs,
  stripShutdownAfterArgs,
} from "./start-agent-viewer.mjs";

const twelveHoursMs = 12 * 60 * 60 * 1000;

test("parseAgentStartArgs consumes launcher mode and preserves server flags", async (t) => {
  const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-workspace-"));
  t.after(() => fs.rm(workspaceDir, { recursive: true, force: true }));

  assert.deepEqual(
    parseAgentStartArgs([
      "--viewer-start-mode=dev",
      "--host",
      "127.0.0.1",
      "--dir",
      workspaceDir,
      "--port=4178",
      "--shutdown-after",
      "12h",
    ]),
    {
      startMode: "dev",
      forwardedArgs: [
        "--host",
        "127.0.0.1",
        "--dir",
        workspaceDir,
        "--port=4178",
        "--shutdown-after",
        "12h",
      ],
      workspaceDir,
      shutdownAfterMs: twelveHoursMs,
      portScanLimit: 64,
    }
  );
});

test("forwardedDefaultRootDir reads and strips default workspace flags", () => {
  assert.equal(forwardedDefaultRootDir(["--host", "127.0.0.1", "--dir=/workspace/models"]), "/workspace/models");
  assert.equal(forwardedDefaultRootDir(["--dir", "models", "--port", "4178"]), "models");
  assert.deepEqual(
    stripDefaultRootDirArgs(["--host", "127.0.0.1", "--dir", "/workspace/models", "--port=4178"]),
    ["--host", "127.0.0.1", "--port=4178"]
  );
});

test("parseAgentStartArgs requires agent:start --dir to be an absolute existing directory", async (t) => {
  const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-workspace-"));
  t.after(() => fs.rm(workspaceDir, { recursive: true, force: true }));
  const filePath = path.join(workspaceDir, "not-a-dir");
  await fs.writeFile(filePath, "");

  assert.equal(normalizeAgentWorkspaceDir(workspaceDir), workspaceDir);
  assert.throws(() => parseAgentStartArgs(["--host", "127.0.0.1"]), /requires --dir/);
  assert.throws(() => parseAgentStartArgs(["--dir", "models"]), /absolute path/);
  assert.throws(() => parseAgentStartArgs(["--dir", path.join(workspaceDir, "missing")]), /directory not found/);
  assert.throws(() => parseAgentStartArgs(["--dir", filePath]), /is not a directory/);
});

test("parseAgentStartArgs rejects invalid launcher modes", () => {
  assert.throws(
    () => parseAgentStartArgs(["--viewer-start-mode", "test"]),
    /must be one of/
  );
});

test("stripShutdownAfterArgs removes lifetime flags before starting Vite", () => {
  assert.deepEqual(
    stripShutdownAfterArgs(["--host", "127.0.0.1", "--shutdown-after=30m", "--port", "4178"]),
    ["--host", "127.0.0.1", "--port", "4178"]
  );
});

test("forwardedServerTarget reads host and port flags", () => {
  assert.deepEqual(
    forwardedServerTarget(["--host=0.0.0.0", "--port", "4200"]),
    {
      host: "0.0.0.0",
      port: 4200,
    }
  );
});

test("replaceForwardedPort updates or appends the selected port", () => {
  assert.deepEqual(
    replaceForwardedPort(["--host", "127.0.0.1", "--port=4178"], 4180),
    ["--host", "127.0.0.1", "--port=4180"]
  );
  assert.deepEqual(
    replaceForwardedPort(["--host", "127.0.0.1"], 4181),
    ["--host", "127.0.0.1", "--port", "4181"]
  );
});

test("selectAgentStartMode uses dev mode for symlinked npm prefixes", async (t) => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-"));
  t.after(() => fs.rm(tmpDir, { recursive: true, force: true }));
  const realViewer = path.join(tmpDir, "viewer");
  const linkedViewer = path.join(tmpDir, "skills", "cad-viewer", "scripts", "viewer");
  await fs.mkdir(realViewer, { recursive: true });
  await fs.mkdir(path.dirname(linkedViewer), { recursive: true });
  await fs.symlink(realViewer, linkedViewer, "dir");

  assert.equal(selectAgentStartMode({ npmConfigPrefix: linkedViewer }), "dev");
  assert.equal(selectAgentStartMode({ npmPackageJson: path.join(linkedViewer, "package.json") }), "dev");
  assert.equal(selectAgentStartMode({ npmConfigPrefix: realViewer }), "serve");
  assert.equal(selectAgentStartMode({ requestedMode: "serve", npmConfigPrefix: linkedViewer }), "serve");
});

test("buildAgentViewerGit returns a worktree and branch value when git exists", async (t) => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-"));
  t.after(() => fs.rm(tmpDir, { recursive: true, force: true }));
  const packageRoot = path.join(tmpDir, "viewer");
  await fs.mkdir(packageRoot, { recursive: true });
  execFileSync("git", ["init"], { cwd: tmpDir, stdio: "ignore" });
  execFileSync("git", ["checkout", "-b", "test-branch"], { cwd: tmpDir, stdio: "ignore" });

  const git = buildAgentViewerGit({ env: {}, cwd: packageRoot });
  assert.match(git, /#test-branch$/);
  assert.match(git, /\/\.git#test-branch$/);
});

test("buildAgentViewerGit is empty outside git", async (t) => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-"));
  t.after(() => fs.rm(tmpDir, { recursive: true, force: true }));
  assert.equal(buildAgentViewerGit({ env: {}, cwd: tmpDir }), "");
});

test("buildAgentStartCommand translates shutdown-after for dev mode", () => {
  const command = buildAgentStartCommand({
    mode: "dev",
    packageRoot: "/workspace/viewer",
    forwardedArgs: ["--host", "127.0.0.1", "--dir", "/workspace/models", "--shutdown-after", "12h", "--port", "4178"],
    shutdownAfterMs: twelveHoursMs,
    env: {},
    nodePath: "/node",
    git: "git-a",
  });

  assert.equal(command.command, "/node");
  assert.deepEqual(command.args, [
    "/workspace/viewer/node_modules/vite/bin/vite.js",
    "dev",
    "--host",
    "127.0.0.1",
    "--port",
    "4178",
  ]);
  assert.equal(command.env.VIEWER_SERVER_LIFETIME_MS, String(twelveHoursMs));
  assert.equal(command.env.VIEWER_DEFAULT_ROOT_DIR, "/workspace/models");
  assert.equal(command.env.VIEWER_GIT, "git-a");
});

test("resolveAgentStartCommand keeps server-only flags on the production server path", async (t) => {
  const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-workspace-"));
  t.after(() => fs.rm(workspaceDir, { recursive: true, force: true }));

  const command = resolveAgentStartCommand({
    argv: ["--viewer-start-mode", "serve", "--dir", workspaceDir, "--shutdown-after", "12h"],
    env: {},
    packageRoot: "/workspace/viewer",
    nodePath: "/node",
  });

  assert.equal(command.mode, "serve");
  assert.deepEqual(command.args, [
    "/workspace/viewer/src/server/server.mjs",
    "--dir",
    workspaceDir,
    "--shutdown-after",
    "12h",
  ]);
});

test("isReusableAgentViewerServer uses git only when both sides report it", () => {
  assert.equal(
    isReusableAgentViewerServer({
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
      git: "git-a",
    }, "git-a"),
    true
  );
  assert.equal(
    isReusableAgentViewerServer({
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
      git: "git-b",
    }, "git-a"),
    false
  );
  assert.equal(
    isReusableAgentViewerServer({
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
    }, "git-a"),
    true
  );
  assert.equal(
    isReusableAgentViewerServer({
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
      git: "git-a",
      activeDirectories: [{
        dir: "/workspace/models",
        rootPath: "/workspace/models",
      }],
    }, ""),
    true
  );
  assert.equal(
    isReusableAgentViewerServer({
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
      git: "git-a",
      workspaceRoot: "/workspace",
      activeDirectories: [{
        dir: "/workspace/models",
        rootPath: "/workspace/models",
      }],
    }, "git-a"),
    true
  );
  assert.equal(
    isReusableAgentViewerServer({
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
      git: "git-a",
      activeDirectories: [{
        dir: "/workspace/skill",
        rootPath: "/workspace/skill",
      }],
    }, "git-a"),
    true
  );
});

test("agentViewerUrl includes the selected absolute workspace dir", async (t) => {
  const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-workspace-"));
  t.after(() => fs.rm(workspaceDir, { recursive: true, force: true }));

  const url = agentViewerUrl("http://127.0.0.1:4178", workspaceDir);
  assert.equal(new URL(url).searchParams.get("dir"), workspaceDir);
});

test("activateAgentViewerWorkspace reads the catalog for the requested dir", async (t) => {
  const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-workspace-"));
  t.after(() => fs.rm(workspaceDir, { recursive: true, force: true }));
  const requestedUrls = [];

  const result = await activateAgentViewerWorkspace({
    baseUrl: "http://127.0.0.1:4178",
    workspaceDir,
    fetchImpl: async (url) => {
      requestedUrls.push(String(url));
      return {
        ok: true,
        json: async () => ({ entries: [] }),
      };
    },
  });

  assert.equal(result.workspaceDir, workspaceDir);
  assert.equal(new URL(result.viewerUrl).searchParams.get("dir"), workspaceDir);
  assert.equal(new URL(requestedUrls[0]).pathname, "/__cad/catalog");
  assert.equal(new URL(requestedUrls[0]).searchParams.get("dir"), workspaceDir);
});

test("resolveAgentViewerPort reuses matching registry servers before free lower ports", async () => {
  const probes = [];
  const result = await resolveAgentViewerPort({
    forwardedArgs: ["--host", "127.0.0.1", "--port", "4178"],
    git: "git-a",
    registryServers: [{
      app: "cad-viewer",
      serverApiVersion: 2,
      dynamicRoot: true,
      git: "git-a",
      port: 5173,
      url: "http://127.0.0.1:5173",
    }],
    probePort: async ({ host, port }) => {
      probes.push(`${host}:${port}`);
      return {
        status: "viewer",
        port,
        baseUrl: `http://${host}:${port}`,
        serverInfo: {
          app: "cad-viewer",
          serverApiVersion: 2,
          dynamicRoot: true,
          git: "git-a",
        },
      };
    },
  });

  assert.equal(result.action, "reuse");
  assert.equal(result.port, 5173);
  assert.deepEqual(probes, ["127.0.0.1:5173"]);
});

test("resolveAgentViewerPort skips other viewers and starts on the first closed port", async () => {
  const probes = [];
  const result = await resolveAgentViewerPort({
    forwardedArgs: ["--port", "4178"],
    git: "git-a",
    registryServers: [],
    portScanLimit: 3,
    probePort: async ({ host, port }) => {
      probes.push(port);
      if (port === 4178) {
        return {
          status: "viewer",
          port,
          baseUrl: `http://${host}:${port}`,
          serverInfo: {
            app: "cad-viewer",
            serverApiVersion: 2,
            dynamicRoot: true,
            git: "git-b",
          },
        };
      }
      return {
        status: "closed",
        port,
        baseUrl: `http://${host}:${port}`,
      };
    },
  });

  assert.equal(result.action, "start");
  assert.equal(result.port, 4179);
  assert.deepEqual(probes, [4178, 4179]);
});

test("probeAgentViewerPort reports permission-blocked local probes", async () => {
  const error = new TypeError("fetch failed");
  error.cause = { code: "EPERM" };
  const result = await probeAgentViewerPort({
    port: 4178,
    fetchImpl: async () => {
      throw error;
    },
  });

  assert.equal(result.status, "blocked");
  assert.equal(result.port, 4178);
});

test("resolveAgentStartLaunch starts the selected free port", async (t) => {
  const workspaceDir = await fs.mkdtemp(path.join(os.tmpdir(), "cad-viewer-agent-start-workspace-"));
  t.after(() => fs.rm(workspaceDir, { recursive: true, force: true }));

  const result = await resolveAgentStartLaunch({
    argv: ["--viewer-start-mode", "serve", "--host", "127.0.0.1", "--dir", workspaceDir, "--port", "4178", "--shutdown-after", "12h"],
    env: {},
    packageRoot: "/workspace/viewer",
    nodePath: "/node",
    registryServers: [],
    probePort: async ({ host, port }) => ({
      status: port === 4178 ? "occupied" : "closed",
      port,
      baseUrl: `http://${host}:${port}`,
    }),
  });

  assert.equal(result.action, "start");
  assert.equal(result.port, 4179);
  assert.deepEqual(result.command.args, [
    "/workspace/viewer/src/server/server.mjs",
    "--host",
    "127.0.0.1",
    "--dir",
    workspaceDir,
    "--port",
    "4179",
    "--shutdown-after",
    "12h",
  ]);
  assert.equal(new URL(result.viewerUrl).searchParams.get("dir"), workspaceDir);
});
