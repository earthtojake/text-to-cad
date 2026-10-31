/**
 * The host's name as a person knows it, from what it calls itself at `ui/initialize` (`hostInfo.name`,
 * MCP Apps: "codex", "Claude", "cursor-mcp-client"...): the word a notice uses where it says what to
 * quit and reopen. A host this page cannot name gives null, and the notice says "this app".
 *
 * This app may name hosts; the shared packages never do (the viewer's strings carry a `{host}`
 * placeholder, filled here).
 */
const HOSTS: readonly [RegExp, string][] = [
  [/codex/i, 'Codex'],
  [/chatgpt/i, 'ChatGPT'],
  [/claude/i, 'Claude'],
  [/cursor/i, 'Cursor'],
  [/gemini/i, 'Gemini'],
  [/grok/i, 'Grok'],
  [/copilot|vscode|visual studio code/i, 'VS Code'],
  [/windsurf/i, 'Windsurf'],
  [/goose/i, 'Goose'],
];

export function hostDisplayName(name: string | null | undefined): string | null {
  const text = String(name || '').trim();
  if (!text) return null;
  return HOSTS.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}
