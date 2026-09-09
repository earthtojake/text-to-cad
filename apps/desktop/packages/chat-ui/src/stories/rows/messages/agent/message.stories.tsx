/**
 * Agent message row stories — prose, code, tables, footer, and streaming.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Messages/Agent/Message',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

export const Prose: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'Sure! Here is a breakdown of the key changes needed:\n\n## Authentication\n\nWe will replace the session store with a **JWT signing key** stored in environment variables.\n\n- Generate tokens on login with `jsonwebtoken`\n- Validate on each request via middleware\n- Store refresh tokens in an `httpOnly` cookie',
        },
      ]}
      height={320}
    />
  ),
};

export const WithCode: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'Here is the middleware:\n\n```typescript\nfunction jwtMiddleware(req: Request, res: Response, next: NextFunction) {\n  const token = req.headers.authorization?.split(" ")[1];\n  if (!token) return res.status(401).json({ error: "Unauthorized" });\n  try {\n    req.user = jwt.verify(token, process.env.JWT_SECRET!);\n    next();\n  } catch {\n    res.status(403).json({ error: "Invalid token" });\n  }\n}\n```',
        },
      ]}
      height={400}
    />
  ),
};

export const WithTable: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'Comparison of authentication strategies:\n\n| Strategy | Pros | Cons |\n|----------|------|------|\n| JWT | Stateless, scalable | Cannot invalidate |\n| Session | Easy to invalidate | Requires store |\n| OAuth | Delegated auth | Complex setup |',
        },
      ]}
      height={340}
    />
  ),
};

/** Assistant message footer — copy button revealed on hover. */
export const Footer: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'The refactor is complete. I updated the authentication middleware to use JWT tokens stored in environment variables, replaced the session store, and added refresh-token handling via httpOnly cookies.',
        },
      ]}
      height={160}
    />
  ),
};

/** User message has no footer; assistant message has footer — confirms layout parity. */
export const Footers: Story = {
  render: () => (
    <ChatHost
      items={[
        { kind: 'message', id: 'u1', role: 'user', text: 'Can you summarise the changes?' },
        {
          kind: 'message',
          id: 'a2',
          role: 'assistant',
          text: 'Sure! The main change was replacing session-based auth with JWT middleware.',
        },
      ]}
      height={200}
    />
  ),
};

const PROSE_BODY = [
  'Here is how JWT authentication works:\n\n',
  '## Token structure\n\n',
  'A JWT has three parts: **header**, **payload**, and **signature**, ',
  'separated by dots.\n\n',
  '## Validation\n\n',
  'The server validates the signature using a secret key. ',
  'No database lookup is needed for stateless validation.\n\n',
  '## Security considerations\n\n',
  'Always use HTTPS to prevent token interception. ',
  'Short expiry times (15–60 min) reduce the attack window.',
].join('');

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={400}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'How does JWT work?' }])],
        streamMessage({ id: 'a1', text: PROSE_BODY, chunkMs: 60 })
      )}
    />
  ),
};

const CODE_BODY = [
  'Here is an example:\n\n',
  '```typescript\n',
  'import jwt from "jsonwebtoken";\n',
  '\nfunction createToken(userId: string): string {\n',
  '  return jwt.sign(\n',
  '    { sub: userId, iat: Date.now() },\n',
  '    process.env.JWT_SECRET!,\n',
  '    { expiresIn: "1h" }\n',
  '  );\n',
  '}\n',
  '```\n\n',
  'Store the secret in your `.env` file.',
].join('');

export const StreamingWithCode: Story = {
  render: () => (
    <ScriptedChat
      height={400}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Show me a JWT example' }])],
        streamMessage({ id: 'a1', text: CODE_BODY, chunkMs: 60 })
      )}
    />
  ),
};
