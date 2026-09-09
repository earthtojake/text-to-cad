/**
 * User message row stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep } from '@/stories/_harness/streaming/scenario';
import { applyTurnEvent } from '@/stories/_harness/turn-reducer';

const meta: Meta = {
  title: 'Rows/Messages/User',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

export const Short: Story = {
  render: () => (
    <ChatHost
      items={[{ kind: 'message', id: 'u1', role: 'user', text: 'Hello, can you help me?' }]}
      height={120}
    />
  ),
};

export const Long: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'u1',
          role: 'user',
          text: 'Can you refactor the authentication module to use JWT tokens instead of session cookies, and add rate limiting middleware for the API endpoints?',
        },
      ]}
      height={140}
    />
  ),
};

const USER_OVERFLOW_TEXT = [
  'Please refactor the authentication module to use JWT tokens:',
  '',
  '1. Replace the session store with a JWT signing key stored in environment variables.',
  '2. Generate tokens on login with `jsonwebtoken` and validate on each request via middleware.',
  '3. Store refresh tokens in an `httpOnly` cookie with a 7-day expiry.',
  '4. Add rate limiting middleware (100 req/min per IP) to all auth endpoints.',
  '5. Write unit tests for the new middleware covering success, expiry, and tampered-token cases.',
  '6. Update the OpenAPI spec to document the Authorization header.',
  '7. Add a `POST /auth/refresh` endpoint that accepts the refresh token cookie and returns a new access token.',
  '',
  'Make sure backward compatibility is preserved for existing sessions during the migration period.',
].join('\n');

/** User message that overflows the 120px collapsed cap — click to expand to 360px. */
export const Overflowing: Story = {
  render: () => (
    <ChatHost
      items={[{ kind: 'message', id: 'u1', role: 'user', text: USER_OVERFLOW_TEXT }]}
      height={300}
    />
  ),
};

/**
 * User message while the agent is generating — shows the hover border and
 * stop button overlay on hover. Clicking the stop button dispatches
 * `turn_cancelled` (via the harness default onStop), removing the button.
 *
 * To see the stop button: hover the user message card.
 */
export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={260}
      script={scenario(
        [
          // Seed the user message into committed first
          seedStep([
            {
              kind: 'message',
              id: 'u1',
              role: 'user',
              text: 'Can you refactor the authentication module to use JWT tokens?',
            },
          ]),
        ],
        [
          // Start an assistant turn so turnStatus becomes 'generating'
          {
            kind: 'call',
            fn: (api) => {
              const ev = {
                type: 'message_chunk' as const,
                id: 'a1',
                role: 'assistant' as const,
                text: 'Sure! ',
              };
              api.activeTurn.set(applyTurnEvent(api.activeTurn.get(), ev), 'generating');
            },
          },
          { kind: 'wait', ms: 600 },
          {
            kind: 'call',
            fn: (api) => {
              const ev = {
                type: 'message_chunk' as const,
                id: 'a1',
                role: 'assistant' as const,
                text: 'I will start by replacing the session store with a JWT signing key…',
              };
              api.activeTurn.set(applyTurnEvent(api.activeTurn.get(), ev), 'generating');
            },
          },
          // No turn_done — leaves the turn open so turnStatus stays 'generating'
        ]
      )}
    />
  ),
};
