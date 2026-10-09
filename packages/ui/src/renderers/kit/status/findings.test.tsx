import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FindingsList, { findingBlocks, findingsAlert, findingsLabel } from './findings.jsx';
Object.assign(globalThis, { React });
afterEach(cleanup);

const error = (index: number, summary: string) => ({ index, severity: 'error', summary, description: `${summary} in full`, items: [] });
const note = (index: number, summary: string) => ({ index, severity: 'warning', summary, description: '', items: [] });

it('names what is found as the card and its icon say it: errors to fix, then suggestions', () => {
  expect(findingBlocks(error(0, 'a'))).toBe(true);
  expect(findingBlocks(note(0, 'a'))).toBe(false);
  expect(findingsLabel([error(0, 'a'), error(1, 'b'), note(2, 'c'), note(3, 'd'), note(4, 'e')])).toBe('2 to fix, 3 suggestions');
  expect(findingsLabel([error(0, 'a')])).toBe('1 to fix');
  expect(findingsLabel([note(0, 'a')])).toBe('1 suggestion');
  expect(findingsLabel([note(0, 'a'), note(1, 'b')])).toBe('2 suggestions');
});

it('raises an alert for what is found: an error to fix opens the card, suggestions alone are a warning, and the sentences are its key', () => {
  expect(findingsAlert([])).toBeNull();
  expect(findingsAlert(null)).toBeNull();
  const fix = findingsAlert([note(0, 'soft'), error(1, 'hard')])!;
  expect(fix).toMatchObject({ severity: 'error', blocking: false, report: false, title: '1 to fix, 1 suggestion' });
  const soft = findingsAlert([note(0, 'soft')])!;
  expect(soft.severity).toBe('warning');
  expect(findingsAlert([note(0, 'softer')])!.key).not.toBe(soft.key);
  expect(findingsAlert([note(0, 'soft')])!.key).toBe(soft.key);
});

it('lists the errors under the renderer\'s heading, then Suggestions, each sentence whole, and hands the one chosen over', () => {
  const onChoose = vi.fn();
  const findings = [note(0, 'Soft one'), error(1, 'Hard one'), note(2, 'Soft two')];
  const { container } = render(<FindingsList findings={findings} headings={{ fix: 'Fix before ordering', suggestions: 'Suggestions' }} onChoose={onChoose} />);
  expect(Array.from(container.querySelectorAll('h3')).map(h => h.textContent)).toEqual(['Fix before ordering', 'Suggestions']);
  expect(Array.from(container.querySelectorAll('[data-finding-row]')).map(row => row.textContent)).toEqual(['Hard one', 'Soft one', 'Soft two']);
  fireEvent.click(screen.getByText('Soft two'));
  expect(onChoose).toHaveBeenCalledWith(findings[2]);
  cleanup();
  const other = render(<FindingsList findings={[error(0, 'x')]} headings={{ fix: 'Fix before using', suggestions: 'Suggestions' }} onChoose={onChoose} />);
  expect(other.container.querySelector('h3')!.textContent).toBe('Fix before using');
  expect(other.container.querySelectorAll('h3').length).toBe(1);
});
