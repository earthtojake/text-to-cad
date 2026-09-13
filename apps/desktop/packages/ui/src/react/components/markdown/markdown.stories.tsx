import type { Meta, StoryObj } from '@storybook/react-vite';
import { InlineMarkdown } from './inline-markdown';
import { Markdown } from './markdown';

const meta: Meta<typeof Markdown> = {
  title: 'Components/Markdown',
  component: Markdown,
  parameters: { layout: 'padded' },
};
export default meta;

type Story = StoryObj<typeof Markdown>;

const KITCHEN_SINK = `# Document heading

Paragraph with **bold**, *italic*, ~~strikethrough~~, \`inline code\`, and a
[link to the docs](https://example.com/docs).

## Second-level heading

> A blockquote with some quoted wisdom about markdown rendering.

### Lists

- First bullet
- Second bullet with nested content
  - Nested bullet
1. Ordered item
2. Another ordered item

### Table

| Feature | Status | Notes |
| --- | --- | --- |
| GFM | Done | Tables, strikethrough, task lists |
| Math | Done | KaTeX via remark-math |
| Mermaid | Done | beautiful-mermaid SVG |

---

#### Task list

- [x] Ship the markdown component
- [ ] Delete the legacy renderer
`;

const MATH_CONTENT = `# Math

Inline math with dollar delimiters: $E = mc^2$, and with LaTeX delimiters: \\(a^2 + b^2 = c^2\\).

Display math:

$$
\\int_{-\\infty}^{\\infty} e^{-x^2} \\, dx = \\sqrt{\\pi}
$$

LaTeX-style display block:

\\[
\\frac{d}{dx} \\left( \\sin x \\right) = \\cos x
\\]
`;

const CODE_CONTENT = `# Code highlighting

TypeScript:

\`\`\`ts
interface Task {
  id: string;
  title: string;
  done: boolean;
}

// Reduce over the open tasks.
export function openCount(tasks: Task[]): number {
  return tasks.filter((task) => !task.done).length;
}
\`\`\`

Python:

\`\`\`python
def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
\`\`\`

Unknown language falls back to plain text:

\`\`\`some-unknown-lang
plain text, no highlighting
\`\`\`
`;

const MERMAID_CONTENT = `# Mermaid

Hover the diagram for the expand affordance; Enter/Space also expands.

\`\`\`mermaid
flowchart LR
  User[User] --> Renderer[React renderer]
  Renderer --> RPC[Typed RPC]
  RPC --> Main[Electron main]
  Main --> DB[(SQLite)]
\`\`\`

Invalid source shows the error state with the source dump:

\`\`\`mermaid
this is not a valid diagram %%%
\`\`\`
`;

const IMAGE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="480" height="240" viewBox="0 0 480 240">
  <rect width="480" height="240" fill="#3b82f6" rx="12"/>
  <circle cx="120" cy="120" r="60" fill="#fbbf24"/>
  <text x="300" y="130" font-size="24" font-family="sans-serif" fill="#ffffff" text-anchor="middle">
    Sample image
  </text>
</svg>`;

const IMAGE_SRC = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(IMAGE_SVG)}`;

const IMAGE_CONTENT = `# Images

External images render through the expandable image viewer (hover to expand):

![Sample diagram](https://placehold.co/480x240/3b82f6/ffffff.png)

Local images resolve through the injected \`resolveImage\` callback:

![Local screenshot](docs/screenshot.png)

A missing local image shows the not-found placeholder:

![Missing](docs/missing.png)
`;

export const Full: Story = {
  args: { content: KITCHEN_SINK, variant: 'full' },
};

export const Compact: Story = {
  args: { content: KITCHEN_SINK, variant: 'compact' },
};

export const Math: Story = {
  args: { content: MATH_CONTENT, variant: 'full' },
};

export const CodeHighlighting: Story = {
  name: 'Code highlighting (shiki)',
  args: { content: CODE_CONTENT, variant: 'full' },
};

export const MermaidDiagrams: Story = {
  args: { content: MERMAID_CONTENT, variant: 'full' },
};

export const MermaidCompact: Story = {
  args: { content: MERMAID_CONTENT, variant: 'compact' },
};

export const Images: Story = {
  args: {
    content: IMAGE_CONTENT,
    variant: 'full',
    resolveImage: async (src: string) => {
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 400));
      return src === 'docs/screenshot.png' ? IMAGE_SRC : null;
    },
  },
};

export const RawHtml: Story = {
  name: 'Raw HTML (full only)',
  args: {
    content:
      'Full variant renders sanitized HTML: <em>emphasis</em>, <kbd>Cmd+K</kbd>.<br>' +
      '<script>alert("stripped")</script> Scripts are stripped by the sanitize schema.',
    variant: 'full',
  },
};

export const LinkInjection: Story = {
  name: 'Link injection (onOpenLink)',
  args: {
    content:
      'Clicking [an external link](https://example.com) or [a relative link](docs/readme.md) ' +
      'routes through the injected `onOpenLink` handler (see the alert).',
    variant: 'full',
    onOpenLink: (href: string) => {
      // eslint-disable-next-line no-alert
      alert(`onOpenLink: ${href}`);
      return true;
    },
  },
};

export const Inline: Story = {
  name: 'InlineMarkdown',
  render: () => (
    <div style={{ maxWidth: 420 }}>
      <InlineMarkdown
        content={
          '# Heading\n\nSome **bold** text with `code`, a [link](https://x.com) and\n- a list'
        }
      />
    </div>
  ),
};
