import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';

vi.mock('@core/primitives/theme/browser', () => ({
  useTheme: () => ({ effectiveTheme: 'emdark' }),
}));

describe('AgentIcon', () => {
  it('renders nothing for an unknown agent id', () => {
    const html = renderToStaticMarkup(<AgentIcon id="unknown-agent-xyz" />);
    expect(html).toBe('');
  });

  it('renders grok in dark mode with invert filter applied', () => {
    const html = renderToStaticMarkup(<AgentIcon id="grok" size={16} />);
    expect(html).not.toBe('');
    expect(html).toContain('invert');
  });

  it('renders opencode in dark mode using the explicit white-fill SVG', () => {
    const html = renderToStaticMarkup(<AgentIcon id="opencode" size={16} />);
    expect(html).not.toBe('');
    expect(html).not.toContain('invert');
  });

  it('applies grayscale class when grayscale prop is true', () => {
    const html = renderToStaticMarkup(<AgentIcon id="claude" size={16} grayscale />);
    expect(html).toContain('grayscale');
  });

  it('passes className to the wrapper span', () => {
    const html = renderToStaticMarkup(<AgentIcon id="claude" size={16} className="rounded-sm" />);
    expect(html).toContain('rounded-sm');
  });
});
