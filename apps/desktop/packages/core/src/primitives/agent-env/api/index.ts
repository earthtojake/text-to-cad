export const AGENT_ENV_VARS = [
  'AIMLAPI_API_KEY',
  'ALL_PROXY',
  'AMP_API_KEY',
  'AMP_TOOLBOX',
  'ANTHROPIC_API_KEY',
  'ANTHROPIC_AUTH_TOKEN',
  'ANTHROPIC_BASE_URL',
  'ANTHROPIC_DEFAULT_HAIKU_MODEL',
  'ANTHROPIC_DEFAULT_OPUS_MODEL',
  'ANTHROPIC_DEFAULT_SONNET_MODEL',
  'ANTHROPIC_MODEL',
  'ANTHROPIC_SMALL_FAST_MODEL',
  'APPDATA',
  'AUTOHAND_API_KEY',
  'AUGMENT_SESSION_AUTH',
  'AWS_ACCESS_KEY_ID',
  'AWS_DEFAULT_REGION',
  'AWS_PROFILE',
  'AWS_REGION',
  'AWS_SECRET_ACCESS_KEY',
  'AWS_SESSION_TOKEN',
  'AZURE_OPENAI_API_ENDPOINT',
  'AZURE_OPENAI_API_KEY',
  'AZURE_OPENAI_KEY',
  'BAILIAN_CODING_PLAN_API_KEY',
  'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS',
  'CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS',
  'CLAUDE_CODE_SUBAGENT_MODEL',
  'CLAUDE_CODE_USE_BEDROCK',
  'CLAUDE_CODE_USE_VERTEX',
  'CLAUDE_CONFIG_DIR',
  'CODEBUFF_API_KEY',
  'CODEX_HOME',
  'COPILOT_HOME',
  'COPILOT_CLI_TOKEN',
  'CURSOR_API_KEY',
  'DASHSCOPE_API_KEY',
  'FACTORY_API_KEY',
  'GEMINI_API_KEY',
  'GH_TOKEN',
  'GITHUB_TOKEN',
  'GOOGLE_API_KEY',
  'GOOGLE_APPLICATION_CREDENTIALS',
  'GOOGLE_CLOUD_LOCATION',
  'GOOGLE_CLOUD_PROJECT',
  'GOOGLE_GENAI_API_VERSION',
  'GOOGLE_VERTEX_BASE_URL',
  'GOOSE_CONTEXT_LIMIT',
  'GOOSE_LEAD_MODEL',
  'GOOSE_LEAD_PROVIDER',
  'GOOSE_MODE',
  'GOOSE_MODEL',
  'GOOSE_PLANNER_MODEL',
  'GOOSE_PLANNER_PROVIDER',
  'GOOSE_PROVIDER',
  'GOOSE_PROVIDER__API_KEY',
  'GOOSE_PROVIDER__HOST',
  'GOOSE_PROVIDER__TYPE',
  'GROK_CODE_XAI_API_KEY',
  'GROK_DEPLOYMENT_KEY',
  'GROK_HOME',
  'GROK_POOL_IDLE_TIMEOUT_SECS',
  'GROK_PROXY_URL',
  'GROK_SANDBOX',
  'GROQ_API_KEY',
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'KIMI_API_KEY',
  'KIMI_CODE_HOME',
  'KIRO_HOME',
  'MISTRAL_API_KEY',
  'MIMOCODE_HOME',
  'MOONSHOT_API_KEY',
  'NO_PROXY',
  'OMP_AUTH_BROKER_SNAPSHOT_CACHE',
  'OMP_AUTH_BROKER_SNAPSHOT_TTL_MS',
  'OMP_AUTH_BROKER_URL',
  'OPENAI_API_KEY',
  'OPENAI_BASE_URL',
  'OPENAI_MODEL',
  'OPENAI_ORGANIZATION',
  'OPENAI_PROJECT',
  'OPENCODE_MODEL',
  'OPENCODE_CONFIG_DIR',
  'OPENROUTER_API_KEY',
  'OPENROUTER_BASE_URL',
  'PI_CODING_AGENT_DIR',
  'PI_CONFIG_DIR',
  'PI_NO_TITLE',
  'PI_PLAN_MODEL',
  'PI_SLOW_MODEL',
  'PI_SMOL_MODEL',
  'QWEN_CODE_SUPPRESS_YOLO_WARNING',
  'QWEN_DEFAULT_AUTH_TYPE',
  'QWEN_HOME',
  'QWEN_MODEL',
  'QWEN_RUNTIME_DIR',
  'QWEN_SANDBOX',
  'VIBE_HOME',
  'XAI_API_KEY',
  'XDG_CONFIG_HOME',
  'ZAI_API_KEY',
] as const;

const DISPLAY_ENV_VARS = [
  'DISPLAY',
  'XAUTHORITY',
  'WAYLAND_DISPLAY',
  'XDG_RUNTIME_DIR',
  'XDG_CURRENT_DESKTOP',
  'XDG_SESSION_TYPE',
  'DBUS_SESSION_BUS_ADDRESS',
] as const;

const GLOBAL_AGENT_ENV_VARS = ['EDITOR', 'VISUAL', 'GIT_EDITOR', 'HOSTNAME', 'LANG', 'TZ'] as const;

export interface BuildAllowlistedAgentEnvOptions {
  homeDir?: string;
  username?: string;
  includeShellVar?: boolean;
}

export function buildAllowlistedAgentEnv(
  sourceEnv: Record<string, string | undefined>,
  options: BuildAllowlistedAgentEnvOptions = {}
): Record<string, string> {
  const env: Record<string, string> = {
    TERM: 'xterm-256color',
    COLORTERM: 'truecolor',
    TERM_PROGRAM: 'emdash',
    HOME: sourceEnv.HOME ?? options.homeDir ?? '',
    USER: sourceEnv.USER ?? sourceEnv.USERNAME ?? options.username ?? '',
    PATH: sourceEnv.PATH ?? '',
    ...getAllowlistedEnv(sourceEnv, GLOBAL_AGENT_ENV_VARS),
    ...getAllowlistedEnv(sourceEnv, DISPLAY_ENV_VARS),
    ...getAllowlistedEnv(sourceEnv, AGENT_ENV_VARS),
  };

  if (sourceEnv.TMPDIR) env.TMPDIR = sourceEnv.TMPDIR;
  if (sourceEnv.SSH_AUTH_SOCK) env.SSH_AUTH_SOCK = sourceEnv.SSH_AUTH_SOCK;
  if (options.includeShellVar && sourceEnv.SHELL) env.SHELL = sourceEnv.SHELL;

  return env;
}

function getAllowlistedEnv(
  sourceEnv: Record<string, string | undefined>,
  keys: readonly string[]
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of keys) {
    const value = sourceEnv[key];
    if (value) env[key] = value;
  }
  return env;
}
