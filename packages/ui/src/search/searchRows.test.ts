import { expect, it } from 'vitest';
import { SEARCH_LIMIT, searchGroups } from '../../dist/search/searchRows.js';

// A row, as a host lists it, opened at `opened` (seconds).
const doc = (path: string, extra: Record<string, unknown> = {}) => ({ path, id: `id:${path}`, name: path.split('/').pop()!, folder: '', opened: null,
  updated: null, created: null, pinned: false, missing: false, thumbnail: null, pictured: null, ...extra }) as any;

const actuator = doc('/w/drive/actuator.xbf', { updated: 50, project: 'p1' });
const gear = doc('/w/drive/gear.step', { opened: 100, project: 'p1' });
const shaft = doc('/w/drive/STEP/shaft.stl', { opened: 10, project: 'p1' });
const blank = doc('/w/examples/gear_blank.step', { opened: 70, project: 'p2' });
const loose = doc('/tmp/gearbox.step', { opened: 90, project: null });
// The library's documents: one of the project on screen (opened since), one of another project and one of none.
const LIST = [{ ...gear, opened: 120 }, blank, loose];
const NAMES = new Map([['p1', 'drive'], ['p2', 'examples']]);
const DRIVE = { id: 'p1', name: 'drive' };
const names = (groups: { id: string; rows: { model: { name: string } }[] }[]) => groups.map(group => [group.id, group.rows.map(row => row.model.name)]);

it('with nothing typed lists the folder of the project on screen as its host answered it; with no project, the latest documents', () => {
  const folder = [actuator, gear];
  expect(names(searchGroups({ list: LIST, here: folder, names: NAMES, query: '', project: DRIVE }).groups)).toEqual([['here', ['actuator.xbf', 'gear.step']]]);
  const { groups } = searchGroups({ list: LIST, names: NAMES, query: '' });
  expect(names(groups)).toEqual([['recent', ['gear.step', 'gearbox.step', 'gear_blank.step']]]);
  // Each row says its project, by name; one of none says nothing.
  expect(groups[0].rows.map(row => row.project?.name ?? null)).toEqual(['drive', null, 'examples']);
});

it("typed, lists the project's files its host found, then the library's documents elsewhere that hold every word, the latest first", () => {
  // What the host found below the project's root; the library's own row of a file of that project is not listed again.
  const found = [gear, shaft];
  expect(names(searchGroups({ list: LIST, here: found, names: NAMES, query: 'gear', project: DRIVE }).groups))
    .toEqual([['here', ['gear.step']], ['other', ['gearbox.step', 'gear_blank.step']]]);
  // The words narrow what is in hand too, so an answer for fewer words stands until the one for these comes.
  expect(names(searchGroups({ list: LIST, here: found, names: NAMES, query: 'step shaft', project: DRIVE }).groups)).toEqual([['here', ['shaft.stl']]]);
  // A path's folder is a word of it: "examples" finds the file under it; with no project on screen, one list.
  expect(names(searchGroups({ list: LIST, names: NAMES, query: 'EXAMPLES', project: null }).groups)).toEqual([['found', ['gear_blank.step']]]);
  expect(searchGroups({ list: LIST, here: found, names: NAMES, query: 'nothing here', project: DRIVE })).toEqual({ groups: [], total: 0 });
});

it(`draws at most ${SEARCH_LIMIT} rows, the first groups' first, and says how many there are`, () => {
  const many = Array.from({ length: 70 }, (_, index) => doc(`/w/drive/part-${index}.step`, { opened: index, project: index < 30 ? 'p1' : 'p2' }));
  const { groups, total } = searchGroups({ list: many.slice(30), here: many.slice(0, 30), names: NAMES, query: 'part', project: DRIVE });
  expect([total, groups.map(group => [group.id, group.rows.length])]).toEqual([70, [['here', 30], ['other', 20]]]);
  expect(searchGroups({ list: many.slice(30), here: many.slice(0, 30), query: 'part', project: DRIVE, limit: 10 }).groups.map(group => group.id)).toEqual(['here']);
});
