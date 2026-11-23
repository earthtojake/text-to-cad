import { expect, it } from 'vitest';
import { SEARCH_LIMIT, searchGroups, searchRows } from '../../dist/search/searchRows.js';

// A library row, as a host lists it: a file unless said, opened at `opened` (seconds).
const doc = (path: string, extra: Record<string, unknown> = {}) => ({ path, id: `id:${path}`, name: path.split('/').pop()!, folder: '', opened: null,
  updated: null, created: null, pinned: false, missing: false, thumbnail: null, pictured: null, kind: 'file', ...extra }) as any;
const project = (id: string, name: string, documents: any[]) => ({ id, name, root: `/w/${name}`, opened: 1, missing: false, documents }) as any;

const model = doc('m1', { id: 'm1', name: 'actuator', kind: 'model', updated: 50 });
const gear = doc('/w/drive/gear.step', { opened: 100 });
const shaft = doc('/w/drive/STEP/shaft.stl', { opened: 10 });
const blank = doc('/w/examples/gear_blank.step', { opened: 70 });
const loose = doc('/tmp/gearbox.step', { opened: 90 });
const PROJECTS = [project('p1', 'drive', [model, shaft, gear]), project('p2', 'examples', [blank])];
// The documents opened before: one a project lists too (its own record, opened since), and one in no project.
const LIST = [{ ...gear, opened: 120, project: 'p1' }, { ...loose, project: null }];
const names = (groups: { id: string; rows: { model: { name: string } }[] }[]) => groups.map(group => [group.id, group.rows.map(row => row.model.name)]);

it('lists every document once, a project\'s with its project, one both lists carry by the opened list\'s record', () => {
  const rows = searchRows(LIST, PROJECTS);
  expect(rows.map(row => [row.model.name, row.project?.name ?? null])).toEqual([
    ['actuator', 'drive'], ['shaft.stl', 'drive'], ['gear.step', 'drive'], ['gear_blank.step', 'examples'], ['gearbox.step', null]]);
  expect(rows.find(row => row.model.name === 'gear.step')!.model.opened).toBe(120);
  // A row with no id is the same document by its path.
  expect(searchRows([{ ...gear, id: undefined }], PROJECTS)).toHaveLength(4);
  // With no projects read, a document opened before keeps the project its row names, unnamed.
  expect(searchRows(LIST, []).map(row => [row.model.name, row.project])).toEqual([['gear.step', null], ['gearbox.step', null]]);
});

it('with nothing typed lists the project on screen, in its page\'s order; with no project, the latest documents', () => {
  const rows = searchRows(LIST, PROJECTS);
  expect(names(searchGroups(rows, { query: '', project: 'p1' }).groups)).toEqual([['here', ['actuator', 'gear.step', 'shaft.stl']]]);
  expect(names(searchGroups(rows, { query: '', project: null }).groups)).toEqual([['recent', ['gear.step', 'gearbox.step', 'gear_blank.step', 'actuator', 'shaft.stl']]]);
});

it('finds as the home does, every word in a name or a file\'s path, the project on screen\'s first, then the rest latest first', () => {
  const rows = searchRows(LIST, PROJECTS);
  expect(names(searchGroups(rows, { query: 'gear', project: 'p1' }).groups)).toEqual([['here', ['gear.step']], ['other', ['gearbox.step', 'gear_blank.step']]]);
  // A file's folder is in its path: "step" finds shaft.stl under STEP/; a model is known by its name alone.
  expect(names(searchGroups(rows, { query: 'drive step', project: 'p2' }).groups)).toEqual([['other', ['gear.step', 'shaft.stl']]]);
  expect(names(searchGroups(rows, { query: 'ACT', project: null }).groups)).toEqual([['found', ['actuator']]]);
  expect(searchGroups(rows, { query: 'nothing here', project: 'p1' })).toEqual({ groups: [], total: 0 });
});

it(`draws at most ${SEARCH_LIMIT} rows, the first groups' first, and says how many there are`, () => {
  const many = Array.from({ length: 70 }, (_, index) => doc(`/w/drive/part-${index}.step`, { opened: index }));
  const rows = searchRows([], [project('p1', 'drive', many.slice(0, 30)), project('p2', 'other', many.slice(30))]);
  const { groups, total } = searchGroups(rows, { query: 'part', project: 'p1' });
  expect([total, groups.map(group => [group.id, group.rows.length])]).toEqual([70, [['here', 30], ['other', 20]]]);
  expect(searchGroups(rows, { query: 'part', project: 'p1', limit: 10 }).groups.map(group => group.id)).toEqual(['here']);
});
