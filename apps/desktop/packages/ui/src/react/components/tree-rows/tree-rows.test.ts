import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const stylesheetSource = readFileSync(new URL('./tree-rows.css.ts', import.meta.url), 'utf8');
const rowStyleSource = stylesheetSource.slice(
  stylesheetSource.indexOf('export const row = style({'),
  stylesheetSource.indexOf('export const chevron = style({')
);

describe('tree row interaction surfaces', () => {
  it('keeps an opened, unselected row transparent until hover', () => {
    expect(rowStyleSource).toMatch(/backgroundColor:\s*'transparent'/);
    expect(rowStyleSource).not.toContain('&[data-opened]');
    expect(rowStyleSource).toMatch(
      /'&:not\(:disabled\):hover':\s*{\s*backgroundColor:\s*vars\.surfaceHover,?\s*}/
    );
  });
});
