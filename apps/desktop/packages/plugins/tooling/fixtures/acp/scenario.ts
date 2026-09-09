/**
 * Ordered scenario for ACP transcript fixture generation.
 *
 * Each step is either a user `prompt` sent via session/prompt, or a control
 * action (setModel / setEffort / setMode) that exercises the config-option and
 * mode update surfaces.
 *
 * The scenario is designed to exercise (nearly) the full ACP SessionUpdate
 * event surface in a single session against the emdash repo:
 *
 *  Step 1  → agent_message_chunk, turn boundary
 *  Step 2  → agent_thought_chunk, tool_call (readFile), tool_call_update, message, resource_link?
 *  Step 3  → tool_call (search/grep), message
 *  Step 4  → multiple tool_call (read), message
 *  Step 5  → config_option_update (setModel control action)
 *  Step 6  → config_option_update (setEffort / thought_level control action)
 *  Step 7  → plan tool with pending / in_progress / completed transitions
 *  Step 8  → plan replacement / mutation
 *  Step 9  → tool_call (execute), createTerminal, terminal output, waitForTerminalExit, requestPermission
 *  Step 10 → second execute / terminal
 *  Step 11 → tool_call (edit/new-file), requestPermission, writeTextFile
 *  Step 12 → tool_call (edit/append), writeTextFile
 *  Step 13 → tool_call (move + delete)
 *  Step 14 → foreground subagent with nested tools
 *  Step 15 → parallel subagents
 *  Step 16 → background subagent launch
 *  Step 17 → background subagent result check
 *  Step 18 → current_mode_update (setMode control action)
 *  Step 19 → long multi-chunk agent_message_chunk
 *
 * usage_update and available_commands_update are emitted passively by the
 * agent and captured by the recording client without needing an explicit step.
 */

import type {
  SessionConfigOption,
  SessionConfigSelectOptions,
  SessionMode,
} from '@agentclientprotocol/sdk';

/** Re-exported under the shorter alias used by callers. */
export type ConfigOption = SessionConfigOption;
export type { SessionMode };

export interface PromptStep {
  kind: 'prompt';
  text: string;
}

/**
 * Resolve a model value dynamically from the initial session config options.
 * The callback receives the initialConfigOptions array and should return a model
 * string that is a valid option for this provider, or null to skip.
 */
export interface SetModelStep {
  kind: 'setModel';
  /**
   * Pick a model from the initialConfigOptions returned by newSession.
   * Called at runtime with the configOptions array; return the model string or
   * null to skip this step if no suitable alternative is found.
   */
  resolveModel: (configOptions: SessionConfigOption[]) => string | null;
}

/** Adjust the effort / thought_level config option, if advertised. */
export interface SetEffortStep {
  kind: 'setEffort';
  /** Pick an effort value. Receives the advertised effort options if any. */
  resolveEffort: (configOptions: SessionConfigOption[]) => string | null;
}

/** Switch to a different session mode, if the agent advertises more than one. */
export interface SetModeStep {
  kind: 'setMode';
  /** Receives the modes list; return a modeId to switch to or null to skip. */
  resolveMode: (modes: SessionMode[]) => string | null;
}

export type ScenarioStep = PromptStep | SetModelStep | SetEffortStep | SetModeStep;

/** Flatten grouped or flat SelectOptions to a uniform `{ value: string }[]`. */
function flattenSelectOptions(options: SessionConfigSelectOptions): { value: string }[] {
  return (options as ({ value: string } | { options: { value: string }[] })[]).flatMap((o) =>
    'options' in o ? o.options : [o]
  );
}

function pickDifferentModel(configOptions: SessionConfigOption[]): string | null {
  const modelConfig = configOptions.find(
    (c) => c.category === 'model' || c.id === 'model' || c.id.toLowerCase().includes('model')
  );
  if (!modelConfig || modelConfig.type !== 'select') return null;
  const current = modelConfig.currentValue;
  const alt = flattenSelectOptions(modelConfig.options).find((o) => o.value !== current);
  return alt?.value ?? null;
}

function pickEffortValue(configOptions: SessionConfigOption[]): string | null {
  const effortConfig = configOptions.find(
    (c) =>
      c.category === 'thought_level' ||
      c.id === 'thought_level' ||
      c.id === 'effort' ||
      c.id.toLowerCase().includes('effort') ||
      c.id.toLowerCase().includes('thinking')
  );
  if (!effortConfig || effortConfig.type !== 'select') return null;
  const current = effortConfig.currentValue;
  const alt = flattenSelectOptions(effortConfig.options).find((o) => o.value !== current);
  return alt?.value ?? null;
}

function pickDifferentMode(modes: SessionMode[]): string | null {
  if (modes.length < 2) return null;
  const alt = modes[1];
  return alt?.id ?? null;
}

export const scenario: ScenarioStep[] = [
  // Step 1 — plain text answer, no tools
  {
    kind: 'prompt',
    text: 'In one sentence, without reading any files, what is emdash?',
  },

  // Step 2 — read AGENTS.md, thought + tool_call(read) + message + resource_link
  {
    kind: 'prompt',
    text:
      'Think about how to explore this repo, then read `AGENTS.md` and give me the ' +
      'Repository Structure section as exactly 3 bullet points.',
  },

  // Step 3 — search / grep tool
  {
    kind: 'prompt',
    text: 'Search the codebase for the definition of `toAgentUpdate` — give the file path and line number.',
  },

  // Step 4 — multiple read tool calls (multi-file surface)
  {
    kind: 'prompt',
    text:
      'Read `packages/core/src/acp/agent-update.ts` and ' +
      '`packages/core/src/acp/session-machine.ts`, then explain in two sentences how they relate.',
  },

  // Step 5 — setModel control action → config_option_update
  {
    kind: 'setModel',
    resolveModel: pickDifferentModel,
  },

  // Step 6 — setEffort / thought_level control action → config_option_update
  {
    kind: 'setEffort',
    resolveEffort: pickEffortValue,
  },

  // Step 7 — plan tool with pending / in_progress / completed transitions
  {
    kind: 'prompt',
    text:
      'Use your todo/task-tracking tool (TodoWrite or update_plan — do not just write a ' +
      'markdown list) to create exactly 4 items for auditing the ACP reducer module. ' +
      'Then actually complete items 1 and 2 using read-only work only: read ' +
      '`packages/core/src/acp/reducer/reducer.ts` for item 1 and search for ' +
      '`NormalizedEvent` in `packages/core/src/acp/reducer` for item 2. Before starting ' +
      'each item, mark it in_progress; after finishing each item, mark it completed. ' +
      'Leave items 3 and 4 pending and summarize what you did.',
  },

  // Step 8 — plan replacement / mutation
  {
    kind: 'prompt',
    text:
      'Update the existing todo/plan using the todo/task-tracking tool again: add a fifth ' +
      'item named "summarize parser fixture gaps", remove item 4 entirely, then mark every ' +
      'remaining item completed. Do not edit files.',
  },

  // Step 9 — execute tool → createTerminal + terminal output + waitForTerminalExit + requestPermission
  {
    kind: 'prompt',
    text: 'Run `git rev-parse --abbrev-ref HEAD` and tell me the current branch name.',
  },

  // Step 10 — second execute / terminal
  {
    kind: 'prompt',
    text: 'Run `ls packages` and list the workspace package names.',
  },

  // Step 11 — create new file (edit with oldText null) + permission + writeTextFile
  {
    kind: 'prompt',
    text:
      'Create the file `.acp-fixture-scratch/NOTES.md` containing exactly this line: ' +
      '`# ACP fixture notes`',
  },

  // Step 12 — append to file (edit with oldText present) + writeTextFile
  {
    kind: 'prompt',
    text: 'Append the line `generated by fixture script` to `.acp-fixture-scratch/NOTES.md`.',
  },

  // Step 13 — rename + delete (move + delete file-op kinds)
  {
    kind: 'prompt',
    text:
      'Rename `.acp-fixture-scratch/NOTES.md` to `.acp-fixture-scratch/NOTES2.md`, ' +
      'then delete `.acp-fixture-scratch/NOTES2.md`.',
  },

  // Step 14 — foreground subagent with nested tools / parentToolCallId surface
  {
    kind: 'prompt',
    text:
      'Launch a foreground subagent (Task tool) to read ' +
      '`packages/core/src/acp/reducer/decode.ts` and search ' +
      '`packages/core/src/acp/reducer` for `NormalizedEvent`, then summarize the files it ' +
      'looked at. The subagent should perform the read and search itself.',
  },

  // Step 15 — parallel subagents / interleaved parent attribution
  {
    kind: 'prompt',
    text:
      'Launch two subagents in parallel. The first should summarize ' +
      '`packages/core/src/acp/reducer/parser.ts`; the second should summarize ' +
      '`packages/core/src/acp/reducer/item-fold.ts`. Wait for both and then combine their ' +
      'answers in two short bullets.',
  },

  // Step 16 — background subagent launch / async Task surface
  {
    kind: 'prompt',
    text:
      'Launch a background subagent to search the repo for every usage of `stopReason` and ' +
      'write a short summary. Do not wait for it; answer immediately with the session id from ' +
      '`pwd` and say that the background task is running.',
  },

  // Step 17 — background subagent result / task notification surface
  {
    kind: 'prompt',
    text:
      'Check whether the background subagent from the previous step has finished. If it has, ' +
      'summarize its result; otherwise report that it is still running.',
  },

  // Step 18 — setMode control action → current_mode_update
  {
    kind: 'setMode',
    resolveMode: pickDifferentMode,
  },

  // Step 19 — long multi-chunk message
  {
    kind: 'prompt',
    text:
      'Explain the ACP session lifecycle in detail, using markdown headings for each phase ' +
      'and including a fenced code block showing an example sequence of events.',
  },
];
