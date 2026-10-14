import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createPromptContext, formatPromptMessage } from '@text-to-cad/core/prompt';
import CamJobPanel, { camChoices } from '../../../dist/renderers/glb/CamJobPanel.js';
import { CAM_SHOWN, CamReadout, camDisplaySections, camHidden, camPathKinds, camReferences, paintCam, toggleCamHidden } from '../../../dist/renderers/glb/camView.js';
import { camOpColours } from '../../../dist/renderers/glb/cam/colours.js';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { camSceneMeshes } from '../../../dist/renderers/glb/cam/playback.js';
import { camExtras, camScene } from './__tests__/camFile';

beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const job = () => readCamJob(camScene())!;

it('leads with the verdict and its errors, then each setup with its operations: word, tool, time', () => {
  const onChoose = vi.fn();
  const { container } = render(<CamJobPanel active job={job()} colours={camOpColours(job())} chosen="" onChoose={onChoose} />);
  expect(screen.getByRole('region', { name: 'Job' })).toBeTruthy();
  const verdict = container.querySelector('[data-cam-verdict]')!;
  expect(verdict.getAttribute('data-cam-verdict')).toBe('fix');
  expect(verdict.querySelector('[data-cam-verdict-title]')!.textContent).toBe('1 to fix');
  // What the job takes, under the headline: its tool changes and the controller its G-code is for.
  expect(verdict.querySelector('[data-cam-summary]')!.textContent).toBe('1 tool change · grbl controller');
  expect(verdict.querySelector('[data-cam-verdict-caption]')!.textContent).toBe('G-code not written: fix 1 error first · 2 warnings');
  // Errors alone, in plain words, under the verdict; warnings go to the agent.
  expect([...verdict.querySelectorAll('[data-cam-finding]')].map((row) => row.textContent)).toEqual(['Tool too long for this pocket']);
  const rows = [...container.querySelectorAll('[data-cam-row]')].map((row) => [row.getAttribute('data-cam-row'), row.textContent]);
  expect(rows).toEqual([['setup:top', 'Top2 operations · 2 min'], ['op:0', 'Face6 mm flat · 30 s'], ['op:1', 'Pocket4 mm ball · 1 min'],
    // The tools after the operations, each with the speed and feed it runs at.
    ['tool:T1', 'T1 6 mm flat12,000 rpm · 1,440 mm/min'], ['tool:T3', 'T3 4 mm ball15,000 rpm · 900 mm/min']]);
  expect(container.querySelectorAll('[data-cam-swatch]')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Select Pocket' }));
  expect(onChoose).toHaveBeenLastCalledWith('op:1');
  fireEvent.click(screen.getByRole('button', { name: 'Select Tool too long for this pocket' }));
  expect(onChoose).toHaveBeenLastCalledWith('finding:0');
});

it('says under the verdict what the plan assumed, one small line each with its reason on hover', () => {
  const extras = camExtras();
  extras.assumed = [{ key: 'machine.post', value: 'fanuc', why: 'no machine model or post given' }, { key: 'machine.max_rpm', value: 8000, why: 'a spindle limit' }];
  const assumed = readCamJob(camScene({ extras }))!;
  const { container } = render(<CamJobPanel active job={assumed} colours={{}} chosen="" onChoose={() => {}} />);
  const lines = [...container.querySelectorAll('[data-cam-verdict] [data-cam-assumed] li')];
  expect(lines.map((line) => line.textContent)).toEqual(['Assumed machine.post fanuc', 'Assumed machine.max_rpm 8000']);
  expect(lines[0].getAttribute('title')).toBe('no machine model or post given');
  cleanup();
  const { container: plain } = render(<CamJobPanel active job={job()} colours={{}} chosen="" onChoose={() => {}} />);
  expect(plain.querySelector('[data-cam-assumed]')).toBeNull();
});

it('marks the row chosen, and keeps the panel mounted but hidden while Select is not the tool', () => {
  const { container, rerender } = render(<CamJobPanel active job={job()} colours={{}} chosen="op:0" onChoose={() => {}} />);
  expect(screen.getByRole('button', { name: 'Select Face' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Select Pocket' }).getAttribute('aria-pressed')).toBe('false');
  rerender(<CamJobPanel active={false} job={job()} colours={{}} chosen="" onChoose={() => {}} />);
  expect(container.querySelector('[data-cam-verdict]')).toBeTruthy();
  expect(screen.queryByRole('region', { name: 'Job' })).toBeNull();
});

it('carries a row into Quick Edit: the part\'s faces with the operation\'s sentence, or the whole part', () => {
  const choices = camChoices(job());
  const pocket = camReferences('/work/part.step', choices.get('op:1'));
  expect(pocket).toEqual([{ resource: { kind: 'workspace-file', path: '/work/part.step' }, target: { kind: 'cad-selector', selectors: ['o1.f12', 'o1.f13'] },
    summary: 'Pocket #o1.f12 with T3 4 mm ball, 60 s' }]);
  const message = formatPromptMessage(createPromptContext([{ id: 'r', kind: 'reference', reference: pocket[0] }]));
  expect(message).toContain('Pocket #o1.f12 with T3 4 mm ball, 60 s · /work/part.step#o1.f12,o1.f13');
  expect(camReferences('/work/part.step', choices.get('op:0'))[0].target).toEqual({ kind: 'whole-resource' });
  expect(choices.get('setup:top')).toMatchObject({ ops: [0, 1], faces: ['#o1.f12', '#o1.f13'], summary: 'Top setup: Face, Pocket, 2 min' });
  expect(choices.get('finding:0')).toMatchObject({ ops: [1], summary: 'Tool too long for this pocket (Pocket #o1.f12 with T3 4 mm ball, 60 s)' });
  // A result with no part to name has no references; nothing chosen, none either.
  expect(camReferences('', choices.get('op:1'))).toEqual([]);
  expect(camReferences('/work/part.step', null)).toEqual([]);
});

it('paints a choice as its operations isolated, and a moment as the tool on the path', () => {
  const root = camScene();
  const parsed = readCamJob(root)!;
  const paths = { update: vi.fn(() => true), toolAt: vi.fn(() => ({ point: [1, 2, 3], op: 1, setup: 'top' })) };
  const tool = { show: vi.fn(), hide: vi.fn() };
  const shown = { toolpaths: true, rapids: false, stock: false, part: true };
  paintCam({ controller: { paths, tool }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: new Set([1]), moment: null });
  expect(paths.update).toHaveBeenLastCalledWith({ toolpaths: true, rapids: false, isolate: new Set([1]), hidden: null, time: null, setup: null });
  expect(tool.hide).toHaveBeenCalled();
  const painted = paintCam({ controller: { paths, tool }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: null, moment: { t: 45, setup: null } });
  expect(painted).toEqual({ changed: true, place: { point: [1, 2, 3], op: 1, setup: 'top' } });
  // The tool as it reaches the moment: an operation's last moment leaves it on that operation.
  expect(paths.toolAt.mock.lastCall![0]).toBeCloseTo(45, 5);
  expect(paths.toolAt.mock.lastCall![0]).toBeLessThan(45);
  expect(tool.show).toHaveBeenLastCalledWith({ point: [1, 2, 3], op: 1, setup: 'top' });
});

it('puts away the operations hidden by their eyes, the tool when Display says, and shows the fixtures of the setup in view', () => {
  const root = camScene();
  const parsed = readCamJob(root)!;
  const paths = { update: vi.fn(() => true), toolAt: vi.fn(() => ({ point: [1, 2, 3], op: 1, setup: 'top' })) };
  const tool = { show: vi.fn(), hide: vi.fn() };
  const fixtures = { update: vi.fn(() => false) };
  const shown = { ...CAM_SHOWN, tool: false, fixtures: true, hidden: [0, 7] };
  const painted = paintCam({ controller: { paths, tool, fixtures }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: null, moment: { t: 45, setup: null } });
  // An index the job does not have is dropped.
  expect(paths.update.mock.lastCall![0].hidden).toEqual(new Set([0]));
  // The tool gate off: the tool stays put away while the clip plays, and the readout still knows where it is.
  expect(tool.show).not.toHaveBeenCalled();
  expect(tool.hide).toHaveBeenCalled();
  expect(painted.place).toMatchObject({ op: 1 });
  // While playing, the fixtures of the setup under way; with a row chosen, its setups'; else the first setup's with any.
  expect(fixtures.update).toHaveBeenLastCalledWith({ shown: true, setups: new Set(['top']) });
  paintCam({ controller: { paths, tool, fixtures }, meshes: camSceneMeshes(root), job: parsed, shown: { ...shown, fixtures: false }, isolate: new Set([0]), moment: null });
  expect(fixtures.update).toHaveBeenLastCalledWith({ shown: false, setups: new Set(['top']) });
  paintCam({ controller: { paths, tool, fixtures }, meshes: camSceneMeshes(root), job: parsed, shown, isolate: null, moment: null });
  expect(fixtures.update).toHaveBeenLastCalledWith({ shown: true, setups: null });
  expect(camHidden(parsed, CAM_SHOWN)).toBeNull();
  expect(toggleCamHidden({ hidden: [1] }, 0)).toEqual([0, 1]);
  expect(toggleCamHidden({ hidden: [0, 1] }, 0)).toEqual([1]);
  expect(toggleCamHidden({}, 1)).toEqual([1]);
});

it('gives each operation a Hide/Reveal eye, kept on its row while the operation is hidden', () => {
  const onToggleHidden = vi.fn();
  const onChoose = vi.fn();
  const { container } = render(<CamJobPanel active job={job()} colours={camOpColours(job())} chosen="" onChoose={onChoose}
    hidden={new Set([1])} onToggleHidden={onToggleHidden} />);
  fireEvent.click(screen.getByRole('button', { name: 'Hide Face' }));
  expect(onToggleHidden).toHaveBeenLastCalledWith(0);
  // The eye is not the row: it neither chooses nor isolates.
  expect(onChoose).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Reveal Pocket' })).toBeTruthy();
  expect(container.querySelector('[data-cam-row="op:1"]')!.hasAttribute('data-cam-hidden')).toBe(true);
  expect(container.querySelector('[data-cam-row="op:0"]')!.hasAttribute('data-cam-hidden')).toBe(false);
  // Setups and tools have no eye.
  expect(screen.queryByRole('button', { name: 'Hide Top' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Hide T1/ })).toBeNull();
});

it('lists each tool with its speed and feed, a range where its operations differ, and carries it into Quick Edit', () => {
  const extras = camExtras() as any;
  extras.tools = [{ id: 'T3', number: 3, type: 'ball_endmill', diameter_mm: 4, plain: '4 mm ball end mill' },
    { id: 'T1', number: 1, type: 'flat_endmill', diameter_mm: 6 }, { id: 'T9', number: 9, type: 'drill', diameter_mm: 5 }];
  extras.setups[0].operations.push({ index: 2, op: 'contour', plain: 'Profile', tool: 'T1', tool_plain: '6 mm flat', rpm: 10000, feed_mm_min: 1440,
    time_s: 10, t0: 90, t1: 100, summary: 'Profile', faces: ['#o1.f2'], limits: [] });
  const parsed = readCamJob(camScene({ extras }))!;
  render(<CamJobPanel active job={parsed} colours={{}} chosen="tool:T1" onChoose={() => {}} />);
  const tools = screen.getByRole('region', { name: 'Tools' });
  expect([...tools.querySelectorAll('[data-cam-row]')].map((row) => row.textContent)).toEqual([
    'T1 6 mm flat10,000–12,000 rpm · 1,440 mm/min', 'T3 4 mm ball end mill15,000 rpm · 900 mm/min', 'T9 5 mm drill']);
  expect(screen.getByRole('button', { name: 'Select T1 6 mm flat' }).getAttribute('aria-pressed')).toBe('true');
  const choices = camChoices(parsed);
  expect(choices.get('tool:T1')).toEqual({ id: 'tool:T1', ops: [0, 2], faces: ['#o1.f2'],
    summary: 'T1 6 mm flat at 10,000–12,000 rpm, 1,440 mm/min: Face, Profile' });
  expect(choices.get('tool:T9')).toMatchObject({ ops: [], summary: 'T9 5 mm drill, unused' });
  expect(camReferences('/work/part.step', choices.get('tool:T1'))[0]).toMatchObject({ target: { kind: 'cad-selector', selectors: ['o1.f2'] } });
});

it('says over the playbar where a playing clip is, and is away while none plays', () => {
  const readoutRef: { current: any } = { current: null };
  const { container } = render(<CamReadout readoutRef={readoutRef} />);
  const box = container.querySelector('[data-cam-readout]') as HTMLElement;
  expect(box.style.display).toBe('none');
  expect(box.getAttribute('aria-hidden')).toBe('true');
  readoutRef.current({ operation: 'Pocket', time: '0:45 / 1:30', speed: '3× speed' });
  expect(box.style.display).toBe('');
  expect(box.textContent).toBe('Pocket0:45 / 1:303× speed');
  readoutRef.current(null);
  expect(box.style.display).toBe('none');
});

it('gates what Display shows of a result: toolpaths, rapids, stock and part, each only where the file has it', () => {
  const root = camScene();
  const onChange = vi.fn();
  const sections = camDisplaySections({ job: job(), meshes: camSceneMeshes(root), paths: camPathKinds(root), shown: CAM_SHOWN, onChange });
  expect(sections.map((section: any) => [section.id, section.title, section.enabled])).toEqual([
    ['cam-toolpaths', 'Toolpaths', true], ['cam-rapids', 'Rapids', true], ['cam-tool', 'Tool', true], ['cam-stock', 'Stock', false], ['cam-part', 'Part', true]]);
  sections[3].onEnabledChange(true);
  expect(onChange).toHaveBeenLastCalledWith({ stock: true });
  sections[2].onEnabledChange(false);
  expect(onChange).toHaveBeenLastCalledWith({ tool: false });
  root.remove(...camSceneMeshes(root).stock.map((entry: any) => entry.object));
  expect(camDisplaySections({ job: job(), meshes: camSceneMeshes(root), paths: { feed: true, rapid: false }, shown: CAM_SHOWN, onChange })
    .map((section: any) => section.title)).toEqual(['Toolpaths', 'Tool', 'Part']);
  // Fixtures only where the file has a fixture box.
  const extras = camExtras() as any;
  extras.setups[0].fixtures = [{ name: 'vise jaw', min_mm: [-5, -10, -20], max_mm: [5, 10, 0] }];
  const fixtured = camDisplaySections({ job: readCamJob(camScene({ extras }))!, meshes: camSceneMeshes(root), paths: { feed: true, rapid: false },
    shown: { ...CAM_SHOWN, fixtures: false }, onChange });
  expect(fixtured.map((section: any) => [section.title, section.enabled])).toEqual([['Toolpaths', true], ['Tool', true], ['Fixtures', false], ['Part', true]]);
  fixtured[2].onEnabledChange(true);
  expect(onChange).toHaveBeenLastCalledWith({ fixtures: true });
});
