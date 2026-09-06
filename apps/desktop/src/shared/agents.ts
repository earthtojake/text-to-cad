/**
 * The shape of an agent provider (the registry's rows) and of the status the
 * detector decorates it with. The table itself is `src/main/agents/registry.ts`;
 * this file is the schema so the renderer can type the Agents page without
 * importing main.
 */
import { z } from "zod";

export const PlatformSchema = z.enum(["macos", "linux", "windows"]);
export type Platform = z.infer<typeof PlatformSchema>;

/** One way to install the agent on one platform. */
export const InstallCommandSchema = z.object({
  /** `Homebrew`, `npm`, `curl`, `winget`… */
  label: z.string(),
  /** A shell line, run in the user's login shell. */
  command: z.string(),
});
export type InstallCommand = z.infer<typeof InstallCommandSchema>;

export const AuthMethodSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("cli-login"),
    label: z.string(),
    /** argv after the binary, run in a pty because it is interactive. */
    args: z.array(z.string()),
  }),
  z.object({
    type: z.literal("api-key"),
    label: z.string(),
    /** Any one of these set in the environment is enough. */
    envVars: z.array(z.string()),
  }),
  z.object({ type: z.literal("none"), label: z.string() }),
]);
export type AuthMethod = z.infer<typeof AuthMethodSchema>;

export const LaunchSchema = z.object({
  command: z.string(),
  args: z.array(z.string()),
  env: z.record(z.string(), z.string()),
});
export type Launch = z.infer<typeof LaunchSchema>;

export const AgentCapabilitiesSchema = z.object({
  /** Native or flattened subagent transcripts. */
  subagents: z.boolean(),
  /** Uses the client's `terminal/*` methods. */
  terminals: z.boolean(),
  /** Offers `session/set_mode`. */
  modes: z.boolean(),
  /** Offers `session/set_config_option` (model, effort…). */
  configOptions: z.boolean(),
  /** Supports `session/load`. */
  loadSession: z.boolean(),
});
export type AgentCapabilities = z.infer<typeof AgentCapabilitiesSchema>;

/** How the app installs its bundled plugin into an agent with a plugin system (plan §8). */
export const PluginInstallSchema = z.object({
  /** argv (after the binary) that registers a marketplace directory; `<path>` is substituted. */
  marketplaceAdd: z.array(z.string()),
  /** argv that installs a plugin; `<plugin>` is substituted with `name@marketplace`. */
  install: z.array(z.string()),
});
export type PluginInstall = z.infer<typeof PluginInstallSchema>;

export const AgentProviderSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  websiteUrl: z.string(),
  docsUrl: z.string(),
  /** The public ACP registry's id for this agent, when it has one. */
  registryId: z.string().nullable(),
  /**
   * The agent's mark: the basename of a committed file in
   * `src/renderer/assets/agents/`, downloaded from the ACP registry by
   * `scripts/fetch-agent-icons.mjs`. Null for the agents the registry has no
   * logo for, which the UI draws as a letter instead.
   */
  icon: z.string().nullable(),
  /**
   * Executables `which` looks for, in preference order. Usually the agent's
   * own CLI: its presence is what "installed" means, and its home directory
   * is where auth and skills live.
   */
  binaryNames: z.array(z.string()),
  /** argv that prints the version; the first semver in the output wins. */
  versionArgs: z.array(z.string()),
  /**
   * False when the launch needs the binary on PATH (`gemini --acp`); true when
   * an `npx` adapter can run without it (Claude, Codex bundle their runtime).
   */
  launchWithoutBinary: z.boolean(),
  install: z.object({
    macos: z.array(InstallCommandSchema),
    linux: z.array(InstallCommandSchema),
    windows: z.array(InstallCommandSchema),
  }),
  authMethods: z.array(AuthMethodSchema),
  /**
   * Cheap signs of a completed login: credential files under the home
   * directory, or environment variables. Absent both, auth state is unknown
   * until the adapter's `initialize` says so.
   */
  authProbe: z.object({
    files: z.array(z.string()),
    envVars: z.array(z.string()),
    /**
     * argv (after the binary) whose exit status says whether the user is
     * logged in — `claude auth status`, `codex login status`. Preferred over
     * the file probe when present.
     */
    checkArgs: z.array(z.string()).nullable(),
  }),
  launch: LaunchSchema,
  capabilities: AgentCapabilitiesSchema,
  /** Where the agent loads skills from, `~`-relative, if documented. */
  skillsDir: z.string().nullable(),
  pluginInstall: PluginInstallSchema.nullable(),
});
export type AgentProvider = z.infer<typeof AgentProviderSchema>;

export const AuthStateSchema = z.enum(["unknown", "authenticated", "unauthenticated", "not-required"]);
export type AuthState = z.infer<typeof AuthStateSchema>;

/** A provider plus what the detector found on this machine. */
export const AgentStatusSchema = AgentProviderSchema.extend({
  installed: z.boolean(),
  binaryPath: z.string().nullable(),
  version: z.string().nullable(),
  auth: AuthStateSchema,
  /** Unix ms of the probe that produced this row. */
  checkedAt: z.number(),
});
export type AgentStatus = z.infer<typeof AgentStatusSchema>;

/** A chunk of an install or login run, streamed as it happens. */
export const AgentJobOutputSchema = z.object({
  jobId: z.string(),
  agentId: z.string(),
  kind: z.enum(["install", "login"]),
  data: z.string(),
  /** Set on the final chunk. */
  exitCode: z.number().int().nullable(),
});
export type AgentJobOutput = z.infer<typeof AgentJobOutputSchema>;
