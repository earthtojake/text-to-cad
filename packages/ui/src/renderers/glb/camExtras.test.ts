import { Group, Mesh } from 'three';
import { expect, it } from 'vitest';
import { camSourcePath, carriesCamJob, formatDuration, jobSummary, operationDetail, readCamJob, toolChangeWords, toolSpeeds } from '../../../dist/renderers/glb/cam/extras.js';
import { camExtras, camScene } from './__tests__/camFile';

it('reads the job a CAM result carries: verdict, setups, operations, errors first', () => {
  const job = readCamJob(camScene())!;
  expect(job.verdict).toEqual({ status: 'fix', headline: '1 to fix', errors: 1, warnings: 2, gcode: 'G-code not written: fix 1 error first' });
  expect(job.setups.map((setup: any) => [setup.id, setup.plain, setup.timeS, setup.operations.length])).toEqual([['top', 'Top', 90, 2]]);
  const pocket = job.operations[1];
  expect(pocket).toMatchObject({ index: 1, op: 'pocket', plain: 'Pocket', tool: 'T3', toolPlain: '4 mm ball', toolDiameterMm: 4, toolType: 'ball',
    rpm: 15000, feedMmMin: 900, timeS: 60, t0: 30, t1: 90, faces: ['#o1.f12', '#o1.f13'], limits: ['lite: engagement capped'], setup: 'top' });
  expect(job.findings.map((finding: any) => finding.level)).toEqual(['error', 'warning', 'warning']);
  expect(job.findings[0]).toMatchObject({ check: 'reach', message: 'Tool too long for this pocket', operation: 1, at: [4, 5, 6] });
  expect(job).toMatchObject({ durationS: 90, document: 'part.step', material: 'aluminum-6061', schema: 1 });
  expect(job.posts).toEqual([{ setup: 'top', file: 'part.top.nc', post: 'grbl', tool: '' }]);
  expect(operationDetail(job.operations[0])).toBe('6 mm flat · 30 s');
});

it('is no job for a plain GLB, nor for one that only names the generator or only carries extras', () => {
  const plain = new Group();
  plain.add(new Mesh());
  expect(carriesCamJob(plain)).toBe(false);
  expect(readCamJob(plain)).toBeNull();
  expect(readCamJob(camScene({ extras: null }))).toBeNull();
  expect(readCamJob(camScene({ generator: '' }))).toBeNull();
  expect(readCamJob(null)).toBeNull();
});

it('reads a sparse or malformed job forgivingly: places, clocks, plain words and a verdict from its errors', () => {
  const root = camScene({ extras: { setups: [{ operations: [{ op: 'drill', time_s: '12', tool_plain: '5 mm drill' }, 'junk', { op: 'contour', time_s: 30 }] }, 7],
    findings: [{ check: 'gouge', severity: 'error', summary: 'Cuts into the part' }, { level: 'error' }, 'junk'], verdict: 'bad' } });
  const job = readCamJob(root)!;
  expect(job.setups).toHaveLength(1);
  expect(job.setups[0]).toMatchObject({ id: 'setup-1', plain: 'setup-1', timeS: 42 });
  expect(job.operations.map((op: any) => [op.index, op.plain, op.t0, op.t1, op.toolDiameterMm])).toEqual([[0, 'drill', 0, 12, 5], [1, 'contour', 12, 42, null]]);
  expect(job.operations[0].summary).toBe('drill with 5 mm drill');
  // A finding with nothing to say is left out.
  expect(job.findings).toEqual([{ check: 'gouge', level: 'error', message: 'Cuts into the part', operation: null, operations: [], at: null }]);
  expect(job.verdict).toMatchObject({ status: 'fix', headline: '1 to fix', errors: 1, warnings: 0 });
  expect(job.durationS).toBe(42);
});

it('says a ready job in plain words when the file has no headline', () => {
  const extras = camExtras();
  extras.verdict = { status: 'ready' } as any;
  extras.findings = [];
  expect(readCamJob(camScene({ extras }))!.verdict).toEqual({ status: 'ready', headline: 'Ready to cut · 2 min · 2 tools', errors: 0, warnings: 0, gcode: '' });
});

it('resolves the part the job was planned from against the GLB, and says durations plainly', () => {
  expect(camSourcePath('/work/out/part.cam.glb', 'part.step')).toBe('/work/out/part.step');
  expect(camSourcePath('/work/out/part.cam.glb', '../src/part.step')).toBe('/work/src/part.step');
  expect(camSourcePath('/work/out/part.cam.glb', '/abs/part.step')).toBe('/abs/part.step');
  expect(camSourcePath('/work/out/part.cam.glb', '')).toBe('');
  expect([0, 0.4, 35, 59.4, 60, 2520, 3900, 7200].map(formatDuration)).toEqual(['0 s', '1 s', '35 s', '59 s', '1 min', '42 min', '1 h 5 min', '2 h']);
});

it('takes a setup\'s tool axis from its matrix (a 3+2 tilt, an indexed rotary position), else from its orientation', () => {
  const extras = camExtras() as any;
  const c = Math.sqrt(3) / 2;
  extras.setups.push(
    { id: 'tilt', orientation: { a_deg: 30, c_deg: 0 }, matrix: [[1, 0, 0, 0], [0, c, -0.5, 0], [0, 0.5, c, -20], [0, 0, 0, 1]], operations: [] },
    { id: 'side', orientation: '-Y', operations: [] });
  extras.machine = { kind: 'mill5', post: 'linuxcnc' };
  extras.posts.push({ setup: 'top', file: 'part.top.T3.nc', post: 'grbl', tool: 'T3' });
  const job = readCamJob(camScene({ extras }))!;
  expect(job.machine).toBe('mill5');
  expect(job.setups.map((setup: any) => [setup.id, setup.orientation, setup.axis])).toEqual([
    ['top', '+Z', [0, 0, 1]], ['tilt', 'A 30°', [0, 0.5, c]], ['side', '-Y', [0, -1, 0]]]);
  expect(job.setups[1].across).toEqual([1, 0, 0]);
  expect(job.posts.map((post: any) => post.tool)).toEqual(['', 'T3']);
});

it('reads a finding as cadgen writes it: its operations and place in items', () => {
  const extras = camExtras() as any;
  extras.findings = [{ check: 'rapid_into_stock', severity: 'error', type: 'rapid_into_stock', summary: 'A rapid crashes into the stock',
    description: 'raise the clearance', items: [{ setup: 'top', operation: 1, move: 6, at: [20.7, 1, 12.4] }, { setup: 'top', operation: 0 }] }];
  const job = readCamJob(camScene({ extras }))!;
  expect(job.findings).toEqual([{ check: 'rapid_into_stock', level: 'error', message: 'A rapid crashes into the stock', operation: 1, operations: [1, 0], at: [20.7, 1, 12.4] }]);
});

it('reads an adapted step\'s words as cadgen writes them', () => {
  const extras = camExtras() as any;
  extras.adapted = [{ step: 'stock_grid', words: 'stock grid 0.5 mm -> 1 mm so the simulation fits 4,000,000 cells', accuracy: 'about 0.5 mm' }];
  expect(readCamJob(camScene({ extras }))!.adapted).toEqual([{ step: 'stock_grid', note: 'stock grid 0.5 mm -> 1 mm so the simulation fits 4,000,000 cells' }]);
});

it('reads the job\'s tools in the order the program uses them, each with the speeds its operations run it at', () => {
  const job = readCamJob(camScene())!;
  // An old file with no tool list: each tool from its operations.
  expect(job.tools).toEqual([
    { id: 'T1', label: 'T1', plain: '6 mm flat', type: '', diameterMm: 6, operations: [0], rpm: [12000, 12000], feedMmMin: [1440, 1440] },
    { id: 'T3', label: 'T3', plain: '4 mm ball', type: 'ball', diameterMm: 4, operations: [1], rpm: [15000, 15000], feedMmMin: [900, 900] }]);
  expect(toolSpeeds(job.tools[0])).toBe('12,000 rpm · 1,440 mm/min');
  expect(toolSpeeds({ rpm: [8000, 12000], feedMmMin: null })).toBe('8,000–12,000 rpm');
  expect(toolSpeeds({ rpm: null, feedMmMin: null })).toBe('');
  const extras = camExtras() as any;
  extras.tools = [{ id: 'T1', number: 1, type: 'flat_endmill', diameter_mm: 6, plain: '6 mm flat end mill' }, { id: '', number: 7, type: 'drill', diameter_mm: 3 }];
  const listed = readCamJob(camScene({ extras }))!;
  expect(listed.tools.map((tool: any) => [tool.label, tool.plain, tool.type, tool.operations])).toEqual([
    ['T1', '6 mm flat end mill', 'flat_endmill', [0]], ['T3', '4 mm ball', 'ball', [1]], ['T7', '3 mm drill', 'drill', []]]);
});

it('counts the tool changes: cadgen\'s where it writes them, else from the operations in program order', () => {
  const job = readCamJob(camScene())!;
  expect(job.toolChanges).toEqual({ count: 1, order: ['T1', 'T3'] });
  expect(job.post).toBe('grbl');
  expect(jobSummary(job)).toBe('1 tool change · grbl controller');
  const extras = camExtras() as any;
  extras.tool_changes = { count: 3, order: ['T1', 'T3', 'T1', 'T3'] };
  extras.machine = { kind: 'mill' };
  extras.posts = [{ setup: 'top', file: 'part.top.nc', post: 'linuxcnc' }];
  extras.warnings = ['G-code not written: fix 1 error first', '', 7];
  const written = readCamJob(camScene({ extras }))!;
  expect(written.toolChanges).toEqual({ count: 3, order: ['T1', 'T3', 'T1', 'T3'] });
  // The controller from the posts when the machine does not name one; the run's warnings, strings alone.
  expect(written.post).toBe('linuxcnc');
  expect(written.warnings).toEqual(['G-code not written: fix 1 error first', '7']);
  expect(jobSummary(written)).toBe('3 tool changes · linuxcnc controller');
  // One tool, no controller named.
  const single = camExtras() as any;
  single.setups[0].operations[1].tool = 'T1';
  single.machine = 'mill';
  single.posts = [];
  expect(jobSummary(readCamJob(camScene({ extras: single }))!)).toBe('No tool changes');
  expect([0, 1, 2].map(toolChangeWords)).toEqual(['No tool changes', '1 tool change', '2 tool changes']);
  expect(readCamJob(camScene())!.warnings).toEqual([]);
});

it('reads each setup\'s fixture boxes in part coordinates, leaving out one with a corner missing', () => {
  const extras = camExtras() as any;
  extras.setups[0].fixtures = [{ name: 'vise jaw', min_mm: [-5, -10, -20], max_mm: [5, 10, 0] }, { name: 'bad', min_mm: [0, 0], max_mm: [1, 1, 1] },
    { min_mm: ['2', 0, 0], max_mm: [1, 1, 1] }];
  const job = readCamJob(camScene({ extras }))!;
  expect(job.setups[0].fixtures).toEqual([{ name: 'vise jaw', min: [-5, -10, -20], max: [5, 10, 0] }, { name: 'Fixture 3', min: [1, 0, 0], max: [2, 1, 1] }]);
  expect(readCamJob(camScene())!.setups[0].fixtures).toEqual([]);
});

it('reads what the plan assumed: each key with its value in words and why, an entry without a key left out', () => {
  const extras = camExtras();
  extras.assumed = [{ key: 'machine.post', value: 'fanuc', why: 'no machine model or post given' },
    { key: 'machine.rigid_tap', value: false, why: 'not known' }, { key: 'machine.travel_mm', value: [300, 200, 80] },
    { value: 1 }, 'nope'];
  expect(readCamJob(camScene({ extras }))!.assumed).toEqual([{ key: 'machine.post', value: 'fanuc', why: 'no machine model or post given' },
    { key: 'machine.rigid_tap', value: 'false', why: 'not known' }, { key: 'machine.travel_mm', value: '300, 200, 80', why: '' }]);
  expect(readCamJob(camScene())!.assumed).toEqual([]);
});
