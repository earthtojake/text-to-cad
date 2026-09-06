import { Dialog } from '@emdash/ui/react/primitives';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ExternalLinkChoiceDialog } from './external-link-choice-dialog';

vi.mock('@core/manifests/browser/modal-api', () => ({
  useModalController: () => ({
    complete: vi.fn(),
    dismiss: vi.fn(),
    setCloseGuard: vi.fn(),
    hasActiveCloseGuard: false,
  }),
}));

describe('ExternalLinkChoiceDialog', () => {
  it('offers a copy action inside the displayed external link', () => {
    const html = renderToStaticMarkup(
      createElement(
        Dialog.Root,
        { open: true },
        createElement(ExternalLinkChoiceDialog, {
          url: 'https://example.com/docs',
          canOpenInEmdashBrowser: true,
          onCopy: vi.fn(() => true),
        })
      )
    );

    expect(html).toContain('https://example.com/docs');
    expect(html).toContain('aria-label="Copy link"');
  });
});
