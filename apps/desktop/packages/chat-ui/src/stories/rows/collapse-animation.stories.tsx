/**
 * Collapse/expand animation story.
 *
 * All collapsible row types start pre-expanded. Click any header to toggle.
 * The animation duration is adjustable via the `durationMs` control — it writes
 * to `collapseAnimationDefaults` so the change takes effect on the next toggle.
 *
 * Row types exercised:
 *   - thinking (done)
 *   - file-op (multi-file)
 *   - execute
 *   - plan
 *   - user message card (long text — click the bubble to expand)
 */

import { collapseAnimationDefaults } from '@components/engine/create-height-tween';
import { createEffect } from 'solid-js';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ChatItem } from '@/model';
import { ChatHost, ChatHostExpanded } from '@/stories/_harness/chat-host';

// ── Seed items ────────────────────────────────────────────────────────────────

const ITEMS: ChatItem[] = [
  { kind: 'message', id: 'u1', role: 'user', text: 'Please refactor the authentication module' },
  {
    kind: 'thinking',
    id: 'think1',
    text: 'The authentication module has several concerns to untangle. First, session management is mixed with token validation. Second, the refresh-token logic has a race condition when multiple tabs are open. Third, the error messages leak implementation details to the client.\n\nMy plan: extract a `TokenService`, move session handling to a dedicated `SessionStore`, add mutex locking on the refresh path, and audit all error responses against OWASP guidance.',
    status: 'done',
    durationMs: 4200,
    startedAt: Date.now() - 4200,
  },
  {
    kind: 'file-op',
    id: 'fop1',
    op: 'edit',
    status: 'done',
    ops: [
      { path: 'src/auth/token-service.ts' },
      { path: 'src/auth/session-store.ts' },
      { path: 'src/auth/refresh-mutex.ts' },
      { path: 'src/auth/errors.ts' },
      { path: 'src/auth/index.ts' },
    ],
  },
  {
    kind: 'execute',
    id: 'exec1',
    command:
      'pnpm run typecheck --filter=@emdash/desktop && pnpm run test --filter=@emdash/desktop -- --run',
    status: 'done',
    startedAt: Date.now() - 2000,
  },
  {
    kind: 'plan',
    id: 'plan1',
    entries: [
      {
        content: 'Extract `TokenService` with sign/verify helpers',
        status: 'completed',
        priority: 'high',
      },
      {
        content: 'Move session state to `SessionStore` (Map + TTL)',
        status: 'completed',
        priority: 'high',
      },
      {
        content: 'Add async mutex on the token-refresh critical section',
        status: 'completed',
        priority: 'medium',
      },
      { content: 'Audit and sanitize all error messages', status: 'completed', priority: 'medium' },
      { content: 'Update unit tests for each new service', status: 'completed', priority: 'low' },
    ],
  },
  {
    kind: 'message',
    id: 'a1',
    role: 'assistant',
    text: 'Done. Here is a summary of the changes:\n\n## TokenService\n\nWraps `jsonwebtoken` with a consistent sign/verify API and centralizes the algorithm and secret config.\n\n## SessionStore\n\nA `Map<string, Session>` with a configurable TTL and a `sweep()` method called on a background interval.\n\n## Refresh mutex\n\nUses a per-user `Promise` chain so concurrent tabs share one in-flight refresh call rather than each issuing their own, eliminating the race condition.\n\n## Error responses\n\nAll 401 and 403 responses now return a generic `{ error: "Unauthorized" }` body, removing stack traces and internal type names from the client-visible surface.',
  },
  {
    kind: 'message',
    id: 'u2',
    role: 'user',
    text: 'This looks great. One follow-up: can we add rate limiting to the login endpoint to mitigate brute-force attacks? We should also make sure to log failed attempts with the IP address so we can detect patterns. Ideally the threshold and window should be configurable via environment variables rather than hardcoded constants.',
  },
];

// ── Playground ────────────────────────────────────────────────────────────────

type PlaygroundArgs = {
  /** Collapse/expand animation duration in ms. Applied on the next toggle. */
  durationMs: number;
};

/**
 * Interactive playground with all collapsible row types.
 *
 * All rows start expanded — click any header/bubble to collapse, click again
 * to expand. The `durationMs` slider controls animation speed; the change is
 * applied on the next toggle (the module-level default is updated reactively).
 */
function CollapsePlayground(args: PlaygroundArgs) {
  // Write to the module-level default so the next tween picks it up.
  createEffect(() => {
    collapseAnimationDefaults.durationMs = args.durationMs;
  });

  return <ChatHostExpanded items={ITEMS} expandId="think1" height={900} />;
}

const meta: Meta<PlaygroundArgs> = {
  title: 'Rows/CollapseAnimation',
  parameters: { layout: 'centered' },
  render: (args) => <CollapsePlayground {...args} />,
  argTypes: {
    durationMs: {
      control: { type: 'range', min: 0, max: 1200, step: 25 },
      description: 'Animation duration in ms. Applied on the next collapse/expand toggle.',
    },
  },
  args: {
    durationMs: 200,
  },
};
export default meta;

type Story = StoryObj<PlaygroundArgs>;

/** Full interactive playground with all collapsible row types. */
export const Playground: Story = {};

// ── Individual row stories ────────────────────────────────────────────────────

/** Thinking row — click the "Thought for Xs" header to collapse/expand. */
export const Thinking: Story = {
  render: () => (
    <ChatHostExpanded
      items={[
        { kind: 'message', id: 'u1', role: 'user', text: 'Explain the plan' },
        {
          kind: 'thinking',
          id: 'think-solo',
          text: 'This is a completed thought block with several sentences of reasoning. It should collapse down to just the header row and expand back to reveal the full text with a smooth animation.\n\nThe reveal direction is: on expand the height grows from headerH → full height (clip opens downward); on collapse it shrinks back.',
          status: 'done',
          durationMs: 1800,
          startedAt: Date.now() - 1800,
        },
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'The animation tween runs in `UnitRow` and drives `virt.setSize` every rAF tick so rows below slide in lockstep.',
        },
      ]}
      expandId="think-solo"
      height={400}
    />
  ),
};

/** Execute row — click the header to toggle. */
export const Execute: Story = {
  render: () => (
    <ChatHostExpanded
      items={[
        { kind: 'message', id: 'u1', role: 'user', text: 'Run the build' },
        {
          kind: 'execute',
          id: 'exec-solo',
          command: 'pnpm run build --filter=@emdash/chat-ui',
          status: 'done',
          startedAt: Date.now() - 800,
        },
        { kind: 'message', id: 'a1', role: 'assistant', text: 'Build complete.' },
      ]}
      expandId="exec-solo"
      height={300}
    />
  ),
};

/** File-op row — click the header to toggle (multi-file). */
export const FileOp: Story = {
  render: () => (
    <ChatHost
      items={[
        { kind: 'message', id: 'u1', role: 'user', text: 'Apply the changes' },
        {
          kind: 'file-op',
          id: 'fop-solo',
          op: 'edit',
          status: 'done',
          ops: [
            { path: 'src/auth/token-service.ts' },
            { path: 'src/auth/session-store.ts' },
            { path: 'src/auth/refresh-mutex.ts' },
            { path: 'src/auth/errors.ts' },
          ],
        },
        { kind: 'message', id: 'a1', role: 'assistant', text: 'Files written successfully.' },
      ]}
      height={300}
    />
  ),
};
