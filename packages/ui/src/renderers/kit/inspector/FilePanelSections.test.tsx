import React, { useEffect } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import FilePanelSections from '../../../../dist/renderers/kit/inspector/FilePanelSections.js';
import InspectorSplit from '../../../../dist/renderers/kit/inspector/InspectorSplit.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// A section's content that says when it mounts and unmounts: folding must do neither.
const lifecycle: string[] = [];
function Tracked({ name }: { name: string }) {
  useEffect(() => { lifecycle.push(`mount ${name}`); return () => { lifecycle.push(`unmount ${name}`); }; }, [name]);
  return <p>{name} rows</p>;
}

it('a lone section is the panel heading and cannot be folded away', () => {
  render(<FilePanelSections sections={[{ id: 'features', title: 'Features', content: <Tracked name="features" /> }]} />);
  expect(screen.getByRole('heading', { name: 'Features' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Collapse|Expand/ })).toBeNull();
});

it('beside another, each heading folds its section away and back without unmounting it', () => {
  lifecycle.length = 0;
  render(<FilePanelSections sections={[
    { id: 'features', title: 'Features', content: <Tracked name="features" /> },
    { id: 'position', title: 'Position', content: <Tracked name="position" /> },
  ]} />);
  const rows = screen.getByText('features rows');
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Features' }));
  expect(rows.closest('[hidden]')).toBeTruthy();
  expect(screen.getByText('position rows').closest('[hidden]')).toBeNull();
  // Folded, the title is the way back in, as a Display gate's is.
  fireEvent.click(screen.getByRole('button', { name: 'Features' }));
  expect(rows.closest('[hidden]')).toBeNull();
  expect(lifecycle).toEqual(['mount features', 'mount position']);
});

it("a pick's details are pinned at the panel's foot, under every section, even with their own folded", () => {
  const { container } = render(<FilePanelSections sections={[
    { id: 'features', title: 'Features', content: <InspectorSplit title="Reference" label="Reference details" details={<p>base</p>}><p>tree</p></InspectorSplit> },
    { id: 'position', title: 'Position', content: <p>joints</p> },
  ]} />);
  const foot = container.querySelector('[data-file-panel-reference]')!;
  expect(foot.contains(screen.getByRole('region', { name: 'Reference details' }))).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Features' }));
  expect(screen.getByRole('region', { name: 'Reference details' }).closest('[hidden]')).toBeNull();
});
