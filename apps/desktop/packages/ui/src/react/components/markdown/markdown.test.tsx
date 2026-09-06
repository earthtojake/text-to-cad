/**
 * @vitest-environment jsdom
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Markdown } from './markdown';
import { sanitizeSchema } from './sanitize-schema';

describe('Markdown', () => {
  describe('sanitize-before-KaTeX pipeline', () => {
    it('renders math because the sanitize schema preserves math classes', () => {
      const { container } = render(<Markdown content={'Inline $x^2$ math'} />);
      expect(container.querySelector('.katex')).not.toBeNull();
    });

    it('renders LaTeX-style delimiters via normalizeLatexDelimiters', () => {
      const { container } = render(<Markdown content={'Inline \\(x^2\\) math'} />);
      expect(container.querySelector('.katex')).not.toBeNull();
    });

    it('strips scripts and event handlers from raw HTML in the full variant', () => {
      const { container } = render(
        <Markdown
          variant="full"
          content={'<script>window.pwned = true;</script><b onclick="hack()">bold</b>'}
        />
      );
      expect(container.querySelector('script')).toBeNull();
      const bold = container.querySelector('b');
      expect(bold).not.toBeNull();
      expect(bold!.getAttribute('onclick')).toBeNull();
    });

    it('whitelists the data: img protocol and math classes in the sanitize schema', () => {
      // data: srcs from markdown source are still emptied by react-markdown's
      // default urlTransform (legacy parity); the schema whitelist ensures the
      // sanitize step itself never drops them, and resolveImage-injected data
      // URIs bypass the pipeline entirely (covered below).
      expect(sanitizeSchema.protocols?.['src']).toContain('data');
      const spanClasses = sanitizeSchema.attributes?.['span']?.find(
        (attr) => Array.isArray(attr) && attr[0] === 'className'
      );
      expect(spanClasses).toEqual(['className', 'math', 'math-inline', 'math-display']);
      const divClasses = sanitizeSchema.attributes?.['div']?.find(
        (attr) => Array.isArray(attr) && attr[0] === 'className'
      );
      expect(divClasses).toEqual(['className', 'math', 'math-inline', 'math-display']);
    });
  });

  describe('allowHtml variants', () => {
    it('renders raw HTML by default in the full variant', () => {
      const { container } = render(<Markdown variant="full" content={'before <em>markup</em>'} />);
      expect(container.querySelector('em')).not.toBeNull();
    });

    it('does not render raw HTML by default in the compact variant', () => {
      const { container } = render(
        <Markdown variant="compact" content={'before <em>markup</em>'} />
      );
      expect(container.querySelector('em')).toBeNull();
    });

    it('renders raw HTML in compact when allowHtml is set', () => {
      const { container } = render(
        <Markdown variant="compact" allowHtml content={'before <em>markup</em>'} />
      );
      expect(container.querySelector('em')).not.toBeNull();
    });
  });

  describe('images', () => {
    it('renders markdown images through the expandable image', () => {
      const { container } = render(
        <Markdown variant="compact" content={'![Screenshot](https://example.com/screenshot.png)'} />
      );
      const image = container.querySelector('img[src="https://example.com/screenshot.png"]');
      expect(image).not.toBeNull();
      expect(image!.getAttribute('alt')).toBe('Screenshot');
      expect(container.querySelector('button[aria-label="Expand image"]')).not.toBeNull();
    });

    it('resolves local images via resolveImage into a data URI', async () => {
      const dataUri = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
      const resolveImage = vi.fn(async () => dataUri);
      const { container } = render(
        <Markdown variant="full" content={'![Local](docs/img.png)'} resolveImage={resolveImage} />
      );
      expect(resolveImage).toHaveBeenCalledWith('docs/img.png');
      await waitFor(() => {
        expect(container.querySelector(`img[src="${dataUri}"]`)).not.toBeNull();
      });
    });

    it('shows a not-found placeholder when resolveImage returns null', async () => {
      const resolveImage = vi.fn(async () => null);
      render(
        <Markdown
          variant="full"
          content={'![Missing](docs/missing.png)'}
          resolveImage={resolveImage}
        />
      );
      await screen.findByText('[Image not found: docs/missing.png]');
    });

    it('does not resolve external images', () => {
      const resolveImage = vi.fn(async () => null);
      const { container } = render(
        <Markdown
          variant="full"
          content={'![Remote](https://example.com/a.png)'}
          resolveImage={resolveImage}
        />
      );
      expect(resolveImage).not.toHaveBeenCalled();
      expect(container.querySelector('img[src="https://example.com/a.png"]')).not.toBeNull();
    });
  });

  describe('task lists', () => {
    it('renders task-list checkboxes read-only instead of disabled', () => {
      const { container } = render(<Markdown variant="full" content={'- [x] done\n- [ ] todo'} />);
      const checkboxes = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
      expect(checkboxes.length).toBe(2);
      for (const checkbox of checkboxes) {
        expect(checkbox.disabled).toBe(false);
        expect(checkbox.readOnly).toBe(true);
        expect(checkbox.getAttribute('aria-disabled')).toBe('true');
        expect(checkbox.tabIndex).toBe(-1);
      }
      expect(checkboxes[0]!.checked).toBe(true);
      expect(checkboxes[1]!.checked).toBe(false);
    });
  });

  describe('code blocks', () => {
    it('highlights fenced code asynchronously with CSS-var token colors', async () => {
      const { container } = render(
        <Markdown variant="full" content={'```ts\nconst answer = 42;\n```'} />
      );
      // Plain text renders immediately; shiki tokens swap in once loaded.
      expect(container.textContent).toContain('const answer = 42;');
      await waitFor(
        () => {
          const coloredToken = container.querySelector('code span[style*="--em-syntax"]');
          expect(coloredToken).not.toBeNull();
        },
        { timeout: 10_000 }
      );
    });
  });

  describe('tables', () => {
    it('renders compact markdown tables with visible structure', () => {
      const { container } = render(
        <Markdown
          variant="compact"
          content={
            '| Layer | What | How |\n| --- | --- | --- |\n| Primary | Headline | Display size |'
          }
        />
      );
      expect(container.querySelector('table')).not.toBeNull();
      expect(container.querySelector('th')).not.toBeNull();
      expect(container.querySelector('td')).not.toBeNull();
      expect(container.textContent).toContain('Primary');
    });
  });

  describe('links', () => {
    it('prevents browser navigation when a link handler claims a relative href', () => {
      const onOpenLink = vi.fn(() => true);
      const { container } = render(
        <Markdown
          variant="full"
          content={'[booking.read](packages/trpc/server/routers/viewer/bookings/get.handler.ts)'}
          onOpenLink={onOpenLink}
        />
      );

      const link = container.querySelector<HTMLAnchorElement>('a[href]');
      expect(link).not.toBeNull();

      const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
      fireEvent(link!, clickEvent);

      expect(onOpenLink).toHaveBeenCalledWith(
        'packages/trpc/server/routers/viewer/bookings/get.handler.ts'
      );
      expect(clickEvent.defaultPrevented).toBe(true);
    });

    it('leaves the click unhandled when the handler declines', () => {
      const onOpenLink = vi.fn(() => false);
      const { container } = render(
        <Markdown variant="full" content={'[docs](https://example.com/)'} onOpenLink={onOpenLink} />
      );

      const link = container.querySelector<HTMLAnchorElement>('a[href]');
      const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
      fireEvent(link!, clickEvent);

      expect(onOpenLink).toHaveBeenCalledWith('https://example.com/');
      expect(clickEvent.defaultPrevented).toBe(false);
    });
  });
});
