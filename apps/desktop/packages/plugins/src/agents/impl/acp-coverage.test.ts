/**
 * Coverage contract for everything the Codex and Claude ACP adapters can send.
 *
 * The adapters' built bundles are scanned for the literals they emit (session
 * update kinds, content block types, tool kinds, `_meta` keys) and the client
 * methods they call. Every value found must appear in one of the tables below:
 * either the app renders it, or it is ignored on purpose with the reason
 * written down. A dependency bump that introduces a new shape fails here with
 * the new value's name, instead of silently dropping it from the thread.
 */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);

function bundle(specifier: string): string {
  return readFileSync(require.resolve(specifier), 'utf8');
}

const codex = bundle('@agentclientprotocol/codex-acp/dist/index.js');
const claude = [
  '@agentclientprotocol/claude-agent-acp/dist/acp-agent.js',
  '@agentclientprotocol/claude-agent-acp/dist/tools.js',
  '@agentclientprotocol/claude-agent-acp/dist/elicitation.js',
]
  .map(bundle)
  .join('\n');

function literals(source: string, pattern: RegExp): string[] {
  return [...new Set([...source.matchAll(pattern)].map((match) => match[1]!))].sort();
}

/** Session update kinds the decoder turns into events (`decode.ts`). */
const RENDERED_SESSION_UPDATES = new Set([
  'user_message_chunk',
  'agent_message_chunk',
  'agent_thought_chunk',
  'tool_call',
  'tool_call_update',
  'plan',
  'plan_update',
  'plan_removed',
  'available_commands_update',
  'current_mode_update',
  'config_option_update',
  'session_info_update',
  'usage_update',
]);

/** Content block types with a rendering path (message text, links, images, diffs, terminals). */
const RENDERED_CONTENT_TYPES = new Set([
  'text',
  'image',
  'resource_link',
  'resource',
  'diff',
  'terminal',
  'content',
]);
const IGNORED_CONTENT_TYPES: Record<string, string> = {
  audio: 'no audio rendering; neither adapter emits audio blocks today',
};

/** Every ACP tool kind maps to a row (file ops, execute, search, fetch, subagent, or a generic row). */
const RENDERED_TOOL_KINDS = new Set([
  'read',
  'edit',
  'delete',
  'move',
  'search',
  'execute',
  'think',
  'fetch',
  'switch_mode',
  'other',
]);

/** `_meta` keys the app consumes. */
const RENDERED_META_KEYS = new Set([
  'terminal_info',
  'terminal_output',
  'terminal_output_delta',
  'terminal_exit',
  'mcp_output_delta',
  'is_mcp_tool_call',
  'claudeCode',
  '_claude/rateLimit',
  '_claude/askUserQuestionOption',
]);
const IGNORED_META_KEYS: Record<string, string> = {
  codex:
    'provider thread metadata on session_info_update and per-option approval decisions; options round-trip by id',
  is_mcp_tool_approval:
    'marks an MCP approval permission request; the options already carry the decision',
  codex_approval_kind: 'permission-request classification read by the adapter itself',
  persist: 'auth/config persistence negotiation between adapter and agent',
  gateway: 'auth method capability negotiation, not a session update',
  kind: 'diff add/update/delete marker on diff blocks; derivable from oldText/newText',
  '_claude/origin': 'usage provenance (user turn vs task notification); kept in the raw log',
  '_claude/sdkMessage': 'opt-in raw SDK mirror; the app does not request it',
};

/** Client methods this app implements (see agent-client.ts). */
const IMPLEMENTED_CLIENT_METHODS = new Set([
  // Codex names them by CLIENT_METHODS key.
  'session_update',
  'session_request_permission',
  'fs_read_text_file',
  'fs_write_text_file',
  'terminal_create',
  'terminal_output',
  'terminal_wait_for_exit',
  'terminal_kill',
  'terminal_release',
  'elicitation_create',
  'elicitation_complete',
  // Claude names them by namespace.method.
  'session.update',
  'session.requestPermission',
  'fs.readTextFile',
  'fs.writeTextFile',
  'elicitation.create',
  'elicitation.complete',
]);

function metaKeys(source: string): string[] {
  return [
    ...literals(source, /_meta: \{\s*([A-Za-z_]+)/g),
    ...literals(source, /terminalMeta\["([a-z_]+)"\]/g),
    ...literals(source, /"(_claude\/[A-Za-z]+)"/g),
  ];
}

function expectCovered(
  values: string[],
  rendered: Set<string>,
  ignored: Record<string, string>,
  what: string
): void {
  const unknown = values.filter((value) => !rendered.has(value) && !(value in ignored));
  expect(unknown, `${what} without a disposition: ${unknown.join(', ')}`).toEqual([]);
}

describe('ACP adapter coverage', () => {
  describe('Codex', () => {
    it('every session update kind is decoded', () => {
      const kinds = literals(codex, /sessionUpdate: "([a-z_]+)"/g);
      expect(kinds.length).toBeGreaterThan(5);
      expectCovered(kinds, RENDERED_SESSION_UPDATES, {}, 'Codex session update kinds');
    });

    it('every content block type has a rendering path', () => {
      const types = literals(
        codex,
        /type: "(text|image|audio|resource_link|resource|diff|terminal|content)"/g
      );
      expectCovered(types, RENDERED_CONTENT_TYPES, IGNORED_CONTENT_TYPES, 'Codex content types');
    });

    it('every tool kind maps to a row', () => {
      const kinds = literals(
        codex,
        /kind: "(read|edit|delete|move|search|execute|think|fetch|switch_mode|other)"/g
      );
      expectCovered(kinds, RENDERED_TOOL_KINDS, {}, 'Codex tool kinds');
    });

    it('every _meta key is consumed or ignored on purpose', () => {
      expectCovered(metaKeys(codex), RENDERED_META_KEYS, IGNORED_META_KEYS, 'Codex _meta keys');
    });

    it('only calls client methods this app implements', () => {
      const methods = literals(codex, /CLIENT_METHODS\.([a-z_]+)/g);
      expect(methods.length).toBeGreaterThan(0);
      expectCovered(methods, IMPLEMENTED_CLIENT_METHODS, {}, 'Codex client methods');
    });
  });

  describe('Claude', () => {
    it('every session update kind is decoded', () => {
      const kinds = literals(claude, /sessionUpdate: "([a-z_]+)"/g);
      expect(kinds.length).toBeGreaterThan(5);
      expectCovered(kinds, RENDERED_SESSION_UPDATES, {}, 'Claude session update kinds');
    });

    it('every content block type has a rendering path', () => {
      const types = literals(
        claude,
        /type: "(text|image|audio|resource_link|resource|diff|terminal|content)"/g
      );
      expectCovered(types, RENDERED_CONTENT_TYPES, IGNORED_CONTENT_TYPES, 'Claude content types');
    });

    it('every tool kind maps to a row', () => {
      const kinds = literals(
        claude,
        /kind: "(read|edit|delete|move|search|execute|think|fetch|switch_mode|other)"/g
      );
      expectCovered(kinds, RENDERED_TOOL_KINDS, {}, 'Claude tool kinds');
    });

    it('every _meta key is consumed or ignored on purpose', () => {
      expectCovered(metaKeys(claude), RENDERED_META_KEYS, IGNORED_META_KEYS, 'Claude _meta keys');
    });

    it('only calls client methods this app implements', () => {
      const methods = literals(claude, /methods\.client\.([a-z]+\.[A-Za-z]+)/g);
      expect(methods.length).toBeGreaterThan(0);
      expectCovered(methods, IMPLEMENTED_CLIENT_METHODS, {}, 'Claude client methods');
    });

    it('gates its terminal narration and AskUserQuestion on flags this app sets', () => {
      // If either gate changes name, the capability advertisement must follow.
      expect(claude).toContain('clientCapabilities?._meta?.["terminal_output"] === true');
      expect(claude).toContain('this.clientCapabilities?.elicitation?.form');
    });
  });
});
