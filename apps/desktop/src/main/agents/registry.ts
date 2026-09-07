/**
 * The provider table (plan §5).
 *
 * Built from the public ACP agent registry —
 * https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json (the
 * `registryId` column is its `id`) and the agents page at
 * https://agentclientprotocol.com/get-started/agents — plus each agent's own
 * install and login docs. Launch lines are the registry's `distribution`
 * where one exists (npx/uvx entries pinned by the registry are launched
 * unpinned here, so the user's installed CLI and the adapter stay in step),
 * and the documented `<cli> acp` / `<cli> --acp` form otherwise.
 *
 * Data only. Nothing here runs anything; `detect.ts` probes, `install.ts`
 * and `auth.ts` run, `acp/connection.ts` launches.
 */
import { AgentProviderSchema, type AgentProvider, type InstallCommand } from "../../shared/agents";

const NPX = "npx";

const npm = (pkg: string): InstallCommand => ({
  label: "npm",
  command: `npm install -g ${pkg}`,
});
const brew = (formula: string, cask = false): InstallCommand => ({
  label: "Homebrew",
  command: `brew install ${cask ? "--cask " : ""}${formula}`,
});
const curl = (url: string, shell = "bash"): InstallCommand => ({
  label: "curl",
  command: `curl -fsSL ${url} | ${shell}`,
});
const winget = (id: string): InstallCommand => ({
  label: "winget",
  command: `winget install ${id}`,
});
const powershell = (url: string): InstallCommand => ({
  label: "PowerShell",
  command: `irm ${url} | iex`,
});
const uvTool = (pkg: string): InstallCommand => ({
  label: "uv",
  command: `uv tool install ${pkg}`,
});

const noPlugins = null;
const noAuthCheck = null;

const CAPS = {
  none: { subagents: false, terminals: false, modes: false, configOptions: false, loadSession: false },
  basic: { subagents: false, terminals: true, modes: false, configOptions: false, loadSession: false },
  full: { subagents: true, terminals: true, modes: true, configOptions: true, loadSession: true },
} as const;

export const AGENT_PROVIDERS: readonly AgentProvider[] = [
  {
    id: "claude-code",
    name: "Claude Code",
    description: "Anthropic's coding agent, through the Claude Agent SDK's ACP adapter.",
    websiteUrl: "https://claude.com/claude-code",
    docsUrl: "https://github.com/agentclientprotocol/claude-agent-acp",
    registryId: "claude-acp",
    icon: "claude-code",
    binaryNames: ["claude"],
    versionArgs: ["--version"],
    // The adapter bundles the Agent SDK's own runtime; the CLI is where the
    // login, settings, skills and plugins live.
    launchWithoutBinary: true,
    install: {
      macos: [curl("https://claude.ai/install.sh"), brew("claude-code", true), npm("@anthropic-ai/claude-code")],
      linux: [curl("https://claude.ai/install.sh"), npm("@anthropic-ai/claude-code")],
      windows: [powershell("https://claude.ai/install.ps1"), npm("@anthropic-ai/claude-code")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in with your Anthropic account", args: ["auth", "login"] },
      { type: "api-key", label: "Anthropic API key", envVars: ["ANTHROPIC_API_KEY"] },
    ],
    authProbe: {
      files: [".claude/.credentials.json"],
      envVars: ["ANTHROPIC_API_KEY"],
      checkArgs: ["auth", "status"],
    },
    // An explicit tag prevents npx selecting an older global adapter and its bundled SDK.
    launch: { command: NPX, args: ["-y", "@agentclientprotocol/claude-agent-acp@latest"], env: {} },
    capabilities: CAPS.full,
    skillsDir: "~/.claude/skills",
    // `marketplace add` keeps the snapshot it first took and `install` answers
    // "already installed" at the old version, so an update is the two extra
    // verbs (src/main/cad/plugin.ts).
    pluginInstall: {
      marketplaceAdd: ["plugin", "marketplace", "add", "<path>"],
      marketplaceUpdate: ["plugin", "marketplace", "update", "<marketplace>"],
      install: ["plugin", "install", "<plugin>"],
      update: ["plugin", "update", "<plugin>"],
    },
  },
  {
    id: "codex",
    name: "Codex",
    description: "OpenAI's coding agent, through the codex-acp adapter over the Codex App Server.",
    websiteUrl: "https://developers.openai.com/codex/cli",
    docsUrl: "https://github.com/agentclientprotocol/codex-acp",
    registryId: "codex-acp",
    icon: "codex",
    binaryNames: ["codex"],
    versionArgs: ["--version"],
    // The npm package carries a compatible @openai/codex of its own; the
    // user's binary is for login, config and skills (CODEX_PATH would point
    // the adapter at it, but its bundled copy is the one it was tested with).
    launchWithoutBinary: true,
    install: {
      macos: [npm("@openai/codex"), brew("codex", true)],
      linux: [npm("@openai/codex")],
      windows: [npm("@openai/codex")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in with ChatGPT", args: ["login"] },
      { type: "api-key", label: "OpenAI API key", envVars: ["CODEX_API_KEY", "OPENAI_API_KEY"] },
    ],
    authProbe: {
      files: [".codex/auth.json"],
      envVars: ["CODEX_API_KEY", "OPENAI_API_KEY"],
      checkArgs: ["login", "status"],
    },
    launch: { command: NPX, args: ["-y", "@agentclientprotocol/codex-acp@latest"], env: {} },
    capabilities: CAPS.full,
    skillsDir: "~/.codex/skills",
    pluginInstall: {
      marketplaceAdd: ["plugin", "marketplace", "add", "<path>"],
      install: ["plugin", "add", "<plugin>"],
    },
  },
  {
    id: "gemini-cli",
    name: "Gemini CLI",
    description: "Google's open-source coding agent; ACP is built in behind --acp.",
    websiteUrl: "https://geminicli.com",
    docsUrl: "https://github.com/google-gemini/gemini-cli",
    registryId: "gemini",
    icon: "gemini-cli",
    binaryNames: ["gemini"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [npm("@google/gemini-cli"), brew("gemini-cli")],
      linux: [npm("@google/gemini-cli")],
      windows: [npm("@google/gemini-cli")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in with Google (runs gemini once)", args: [] },
      { type: "api-key", label: "Gemini API key", envVars: ["GEMINI_API_KEY", "GOOGLE_API_KEY"] },
    ],
    authProbe: {
      files: [".gemini/oauth_creds.json"],
      envVars: ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
      checkArgs: noAuthCheck,
    },
    launch: { command: "gemini", args: ["--acp"], env: {} },
    capabilities: { subagents: false, terminals: true, modes: true, configOptions: false, loadSession: false },
    skillsDir: "~/.gemini/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "github-copilot",
    name: "GitHub Copilot CLI",
    description: "GitHub's terminal agent; ACP support is in public preview behind --acp.",
    websiteUrl: "https://github.com/features/copilot/cli/",
    docsUrl: "https://github.com/github/copilot-cli",
    registryId: "github-copilot-cli",
    icon: "github-copilot",
    binaryNames: ["copilot"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://gh.io/copilot-install"), brew("copilot-cli"), npm("@github/copilot")],
      linux: [curl("https://gh.io/copilot-install"), npm("@github/copilot")],
      windows: [winget("GitHub.Copilot"), npm("@github/copilot")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in with GitHub", args: ["login"] },
      { type: "api-key", label: "GitHub token", envVars: ["GH_TOKEN", "GITHUB_TOKEN"] },
    ],
    authProbe: { files: [], envVars: ["GH_TOKEN", "GITHUB_TOKEN"], checkArgs: noAuthCheck },
    launch: { command: "copilot", args: ["--acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: "~/.copilot/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "opencode",
    name: "OpenCode",
    description: "The open-source terminal agent from anomaly; `opencode acp` serves ACP.",
    websiteUrl: "https://opencode.ai",
    docsUrl: "https://opencode.ai/docs/acp/",
    registryId: "opencode",
    icon: "opencode",
    binaryNames: ["opencode"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://opencode.ai/install"), npm("opencode-ai"), brew("anomalyco/tap/opencode")],
      linux: [curl("https://opencode.ai/install"), npm("opencode-ai")],
      windows: [npm("opencode-ai")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to a provider", args: ["auth", "login"] },
      {
        type: "api-key",
        label: "Provider API key",
        envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"],
      },
    ],
    authProbe: {
      files: [".local/share/opencode/auth.json"],
      envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"],
      checkArgs: noAuthCheck,
    },
    launch: { command: "opencode", args: ["acp"], env: {} },
    capabilities: { subagents: false, terminals: true, modes: true, configOptions: false, loadSession: false },
    skillsDir: "~/.config/opencode/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "amp",
    name: "Amp",
    description: "Sourcegraph's frontier coding agent, through the amp-acp adapter.",
    websiteUrl: "https://ampcode.com",
    docsUrl: "https://github.com/tao12345666333/amp-acp",
    registryId: "amp-acp",
    icon: "amp",
    binaryNames: ["amp"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://ampcode.com/install.sh"), npm("@sourcegraph/amp")],
      linux: [curl("https://ampcode.com/install.sh"), npm("@sourcegraph/amp")],
      windows: [npm("@sourcegraph/amp")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to Amp", args: ["login"] },
      { type: "api-key", label: "Amp API key", envVars: ["AMP_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["AMP_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: NPX, args: ["-y", "amp-acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: "~/.config/amp/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "qwen-code",
    name: "Qwen Code",
    description: "Alibaba's coding agent for Qwen models; ACP behind --acp.",
    websiteUrl: "https://qwenlm.github.io/qwen-code-docs/en/users/overview",
    docsUrl: "https://github.com/QwenLM/qwen-code",
    registryId: "qwen-code",
    icon: "qwen-code",
    binaryNames: ["qwen"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [npm("@qwen-code/qwen-code@latest"), brew("qwen-code")],
      linux: [npm("@qwen-code/qwen-code@latest")],
      windows: [npm("@qwen-code/qwen-code@latest")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in with Qwen OAuth (runs qwen once)", args: [] },
      { type: "api-key", label: "OpenAI-compatible API key", envVars: ["OPENAI_API_KEY"] },
    ],
    authProbe: { files: [".qwen/oauth_creds.json"], envVars: ["OPENAI_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: "qwen", args: ["--acp", "--experimental-skills"], env: {} },
    capabilities: { subagents: false, terminals: true, modes: true, configOptions: false, loadSession: false },
    skillsDir: "~/.qwen/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "kiro",
    name: "Kiro CLI",
    description: "AWS's Kiro agent in the terminal; `kiro-cli acp` serves ACP.",
    websiteUrl: "https://kiro.dev",
    docsUrl: "https://kiro.dev/docs/cli/acp/",
    registryId: null,
    icon: "kiro",
    binaryNames: ["kiro-cli"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [brew("kiro-cli", true), curl("https://cli.kiro.dev/install.sh")],
      linux: [curl("https://cli.kiro.dev/install.sh")],
      windows: [],
    },
    authMethods: [{ type: "cli-login", label: "Sign in to Kiro", args: ["login"] }],
    authProbe: { files: [], envVars: [], checkArgs: noAuthCheck },
    launch: { command: "kiro-cli", args: ["acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "auggie",
    name: "Auggie",
    description: "Augment Code's CLI agent; ACP behind --acp.",
    websiteUrl: "https://www.augmentcode.com/",
    docsUrl: "https://docs.augmentcode.com/cli/acp",
    registryId: "auggie",
    icon: "auggie",
    binaryNames: ["auggie"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [npm("@augmentcode/auggie")],
      linux: [npm("@augmentcode/auggie")],
      windows: [npm("@augmentcode/auggie")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to Augment", args: ["login"] },
      { type: "api-key", label: "Augment session token", envVars: ["AUGMENT_SESSION_AUTH"] },
    ],
    authProbe: { files: [".augment/session.json"], envVars: ["AUGMENT_SESSION_AUTH"], checkArgs: noAuthCheck },
    launch: { command: "auggie", args: ["--acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "goose",
    name: "Goose",
    description: "Block's open-source agent; `goose acp` serves ACP.",
    websiteUrl: "https://block.github.io/goose/",
    docsUrl: "https://block.github.io/goose/docs/guides/acp-clients",
    registryId: "goose",
    icon: "goose",
    binaryNames: ["goose"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [
        curl("https://github.com/block/goose/releases/download/stable/download_cli.sh"),
        brew("block-goose-cli"),
      ],
      linux: [curl("https://github.com/block/goose/releases/download/stable/download_cli.sh")],
      windows: [],
    },
    authMethods: [
      { type: "cli-login", label: "Configure a provider", args: ["configure"] },
      {
        type: "api-key",
        label: "Provider API key",
        envVars: ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"],
      },
    ],
    authProbe: {
      files: [".config/goose/config.yaml"],
      envVars: ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"],
      checkArgs: noAuthCheck,
    },
    launch: { command: "goose", args: ["acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "mistral-vibe",
    name: "Mistral Vibe",
    description: "Mistral's coding agent; installs the vibe-acp server alongside vibe.",
    websiteUrl: "https://mistral.ai/products/vibe",
    docsUrl: "https://github.com/mistralai/mistral-vibe/blob/main/docs/acp-setup.md",
    registryId: "mistral-vibe",
    icon: "mistral-vibe",
    binaryNames: ["vibe-acp", "vibe"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://mistral.ai/vibe/install.sh"), uvTool("mistral-vibe")],
      linux: [curl("https://mistral.ai/vibe/install.sh"), uvTool("mistral-vibe")],
      windows: [uvTool("mistral-vibe")],
    },
    authMethods: [
      { type: "cli-login", label: "Set up Vibe (runs vibe once)", args: [] },
      { type: "api-key", label: "Mistral API key", envVars: ["MISTRAL_API_KEY"] },
    ],
    authProbe: { files: [".vibe/config.toml"], envVars: ["MISTRAL_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: "vibe-acp", args: [], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "cursor-agent",
    name: "Cursor Agent",
    description: "Cursor's CLI agent; `cursor-agent acp` serves ACP.",
    websiteUrl: "https://cursor.com",
    docsUrl: "https://cursor.com/docs/cli/acp",
    registryId: "cursor",
    icon: "cursor-agent",
    binaryNames: ["cursor-agent"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://cursor.com/install")],
      linux: [curl("https://cursor.com/install")],
      windows: [powershell("https://cursor.com/install")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to Cursor", args: ["login"] },
      { type: "api-key", label: "Cursor API key", envVars: ["CURSOR_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["CURSOR_API_KEY"], checkArgs: ["status"] },
    launch: { command: "cursor-agent", args: ["acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: "~/.cursor/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "droid",
    name: "Factory Droid",
    description: "Factory's Droid CLI; ACP through `droid exec --output-format acp-daemon`.",
    websiteUrl: "https://factory.ai/product/cli",
    docsUrl: "https://docs.factory.ai/cli",
    registryId: "factory-droid",
    icon: "droid",
    binaryNames: ["droid"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://app.factory.ai/cli", "sh")],
      linux: [curl("https://app.factory.ai/cli", "sh")],
      windows: [powershell("https://app.factory.ai/cli/windows")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to Factory (runs droid once)", args: [] },
      { type: "api-key", label: "Factory API key", envVars: ["FACTORY_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["FACTORY_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: "droid", args: ["exec", "--output-format", "acp-daemon"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: "~/.factory/skills",
    pluginInstall: noPlugins,
  },
  {
    id: "hermes",
    name: "Hermes Agent",
    description: "Nous Research's agent; `hermes acp` serves ACP.",
    websiteUrl: "https://hermes-agent.nousresearch.com",
    docsUrl: "https://hermes-agent.nousresearch.com/docs/user-guide/features/acp",
    registryId: null,
    icon: "hermes",
    binaryNames: ["hermes"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [curl("https://hermes-agent.nousresearch.com/install.sh")],
      linux: [curl("https://hermes-agent.nousresearch.com/install.sh")],
      windows: [],
    },
    authMethods: [
      { type: "cli-login", label: "Run the ACP setup", args: ["acp", "--setup"] },
      {
        type: "api-key",
        label: "Provider API key",
        envVars: ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
      },
    ],
    authProbe: {
      files: [],
      envVars: ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
      checkArgs: ["acp", "--check"],
    },
    launch: { command: "hermes", args: ["acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "cline",
    name: "Cline",
    description: "Cline's CLI; ACP behind --acp.",
    websiteUrl: "https://cline.bot/cli",
    docsUrl: "https://github.com/cline/cline",
    registryId: "cline",
    icon: "cline",
    binaryNames: ["cline"],
    versionArgs: ["--version"],
    launchWithoutBinary: true,
    install: {
      macos: [npm("cline")],
      linux: [npm("cline")],
      windows: [npm("cline")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to Cline", args: ["auth"] },
      {
        type: "api-key",
        label: "Provider API key",
        envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"],
      },
    ],
    authProbe: {
      files: [],
      envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"],
      checkArgs: noAuthCheck,
    },
    launch: { command: NPX, args: ["-y", "cline", "--acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "kimi",
    name: "Kimi CLI",
    description: "Moonshot's terminal agent; `kimi acp` serves ACP after /login.",
    websiteUrl: "https://moonshotai.github.io/kimi-cli/",
    docsUrl: "https://github.com/MoonshotAI/kimi-cli",
    registryId: "kimi",
    icon: "kimi",
    binaryNames: ["kimi"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: {
      macos: [uvTool("kimi-cli")],
      linux: [uvTool("kimi-cli")],
      windows: [uvTool("kimi-cli")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in (send /login once kimi starts)", args: [] },
      { type: "api-key", label: "Moonshot API key", envVars: ["KIMI_API_KEY", "MOONSHOT_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["KIMI_API_KEY", "MOONSHOT_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: "kimi", args: ["acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "kilo",
    name: "Kilo",
    description: "Kilo Code's CLI; `kilo acp` serves ACP.",
    websiteUrl: "https://kilo.ai/",
    docsUrl: "https://github.com/Kilo-Org/kilocode",
    registryId: "kilo",
    icon: "kilo",
    binaryNames: ["kilo"],
    versionArgs: ["--version"],
    launchWithoutBinary: true,
    install: {
      macos: [npm("@kilocode/cli")],
      linux: [npm("@kilocode/cli")],
      windows: [npm("@kilocode/cli")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to Kilo", args: ["login"] },
      { type: "api-key", label: "Kilo API key", envVars: ["KILOCODE_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["KILOCODE_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: NPX, args: ["-y", "@kilocode/cli", "acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "qoder",
    name: "Qoder CLI",
    description: "Qoder's terminal agent; ACP behind --acp.",
    websiteUrl: "https://qoder.com",
    docsUrl: "https://docs.qoder.com/cli/acp",
    registryId: "qoder",
    icon: "qoder",
    binaryNames: ["qodercli"],
    versionArgs: ["--version"],
    launchWithoutBinary: true,
    install: {
      macos: [npm("@qoder-ai/qodercli")],
      linux: [npm("@qoder-ai/qodercli")],
      windows: [npm("@qoder-ai/qodercli")],
    },
    authMethods: [{ type: "cli-login", label: "Sign in to Qoder", args: ["login"] }],
    authProbe: { files: [], envVars: [], checkArgs: noAuthCheck },
    launch: { command: NPX, args: ["-y", "@qoder-ai/qodercli", "--acp"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "grok-build",
    name: "Grok Build",
    description: "xAI's coding agent CLI; `grok agent stdio` serves ACP.",
    websiteUrl: "https://x.ai/cli",
    docsUrl: "https://x.ai/cli",
    registryId: "grok-build",
    icon: "grok-build",
    binaryNames: ["grok"],
    versionArgs: ["--version"],
    launchWithoutBinary: true,
    install: {
      macos: [npm("@xai-official/grok")],
      linux: [npm("@xai-official/grok")],
      windows: [npm("@xai-official/grok")],
    },
    authMethods: [
      { type: "cli-login", label: "Sign in to xAI", args: ["login"] },
      { type: "api-key", label: "xAI API key", envVars: ["XAI_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["XAI_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: NPX, args: ["-y", "@xai-official/grok", "agent", "stdio"], env: {} },
    capabilities: CAPS.basic,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "deepagents",
    name: "DeepAgents",
    description: "LangChain's deep agents harness, through the deepagents-acp adapter.",
    websiteUrl: "https://docs.langchain.com/oss/javascript/deepagents/overview",
    docsUrl: "https://github.com/langchain-ai/deepagentsjs",
    registryId: "deepagents",
    icon: "deepagents",
    binaryNames: ["deepagents-acp"],
    versionArgs: ["--version"],
    launchWithoutBinary: true,
    install: {
      macos: [npm("deepagents-acp")],
      linux: [npm("deepagents-acp")],
      windows: [npm("deepagents-acp")],
    },
    authMethods: [
      { type: "api-key", label: "Model provider API key", envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: NPX, args: ["-y", "deepagents-acp"], env: {} },
    capabilities: CAPS.none,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "fast-agent",
    name: "fast-agent",
    description: "The fast-agent MCP framework's ACP server, run with uvx.",
    websiteUrl: "https://fast-agent.ai",
    docsUrl: "https://fast-agent.ai/acp",
    registryId: "fast-agent",
    icon: "fast-agent",
    binaryNames: ["fast-agent-acp"],
    versionArgs: ["--version"],
    launchWithoutBinary: true,
    install: {
      macos: [uvTool("fast-agent-acp")],
      linux: [uvTool("fast-agent-acp")],
      windows: [uvTool("fast-agent-acp")],
    },
    authMethods: [
      { type: "api-key", label: "Model provider API key", envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: "uvx", args: ["fast-agent-acp", "-x"], env: {} },
    capabilities: CAPS.none,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "junie",
    name: "Junie",
    description: "JetBrains' coding agent, distributed as a standalone ACP binary.",
    websiteUrl: "https://junie.jetbrains.com",
    docsUrl: "https://github.com/JetBrains/junie-acp-release",
    registryId: "junie",
    icon: "junie",
    binaryNames: ["junie"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: { macos: [], linux: [], windows: [] },
    authMethods: [{ type: "cli-login", label: "Sign in with your JetBrains account", args: ["login"] }],
    authProbe: { files: [], envVars: [], checkArgs: noAuthCheck },
    launch: { command: "junie", args: [], env: {} },
    capabilities: CAPS.none,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
  {
    id: "devin",
    name: "Devin",
    description: "Cognition's Devin CLI, distributed as a standalone ACP binary.",
    websiteUrl: "https://docs.devin.ai/cli",
    docsUrl: "https://github.com/CognitionAI/devin-cli",
    registryId: "devin",
    icon: "devin",
    binaryNames: ["devin"],
    versionArgs: ["--version"],
    launchWithoutBinary: false,
    install: { macos: [], linux: [], windows: [] },
    authMethods: [
      { type: "cli-login", label: "Sign in to Devin", args: ["login"] },
      { type: "api-key", label: "Devin API key", envVars: ["DEVIN_API_KEY"] },
    ],
    authProbe: { files: [], envVars: ["DEVIN_API_KEY"], checkArgs: noAuthCheck },
    launch: { command: "devin", args: ["acp"], env: {} },
    capabilities: CAPS.none,
    skillsDir: null,
    pluginInstall: noPlugins,
  },
].map((provider) => AgentProviderSchema.parse(provider));

/** Look a provider up by id. */
export function agentProvider(id: string): AgentProvider | null {
  const provider = AGENT_PROVIDERS.find((candidate) => candidate.id === id) ?? null;
  return provider && FAKE_AGENT ? { ...provider, launch: FAKE_AGENT } : provider;
}

/**
 * `HARDCORE_FAKE_AGENT=<path to a stdio ACP agent>`: launch that instead of
 * whatever the table says, for every provider.
 *
 * The Playwright suite needs a session — a real thread with a real cwd — to
 * check anything about git modes, worktrees or reviews, and it cannot have
 * one without an agent to talk to. `tests/fake-agent/index.mjs` is that agent
 * and always has been; this is the one line that lets the built app reach it.
 *
 * Read once at load, from the *process* environment, so it can only be set by
 * whoever started the binary. The renderer cannot reach it, and a packaged app
 * launched normally never sees it.
 */
const FAKE_AGENT: AgentProvider["launch"] | null = process.env.HARDCORE_FAKE_AGENT
  ? {
      // Electron's own binary as the runtime, rather than whatever `node` the
      // login shell finds: `ELECTRON_RUN_AS_NODE` makes it a plain Node, and
      // a machine with no `node` on its PATH still runs the suite.
      command: process.execPath,
      args: [process.env.HARDCORE_FAKE_AGENT],
      env: { ELECTRON_RUN_AS_NODE: "1" },
    }
  : null;
