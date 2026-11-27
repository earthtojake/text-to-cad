import assert from 'node:assert/strict';
import { test } from 'node:test';
import { INDEX, MIN_AGE_MS, OLD_BELOW, feedsOf, heldOf, latestOf, pypiFeeds } from './versions.mjs';

// The clock the tests read: an hour is the age a release must reach before the feed names it.
const NOW = Date.parse('2026-11-17T12:00:00Z');
const MINUTE = 60_000;
const ago = minutes => new Date(NOW - minutes * MINUTE).toISOString();

// PyPI's simple index for cadgen, as uv reads it (PEP 691 JSON): a wheel and an sdist per release, each with
// the time PyPI took it (PEP 700).
const file = (filename, yanked = false, uploaded = ago(24 * 60)) => ({
  filename, yanked, hashes: {}, 'upload-time': uploaded, url: `https://files.pythonhosted.org/${filename}`,
});
const PAGE = {
  meta: { 'api-version': '1.4' },
  name: 'cadgen',
  versions: ['0.7.9', '0.7.10', '0.7.18', '0.8.0rc1', '0.8.1'],
  files: [
    file('cadgen-0.7.9-py3-none-any.whl'), file('cadgen-0.7.9.tar.gz'),
    file('cadgen-0.7.10-py3-none-any.whl'), file('cadgen-0.7.10.tar.gz'),
    file('cadgen-0.7.18-py3-none-any.whl'), file('cadgen-0.7.18.tar.gz', 'sdist rebuilt'),
    file('cadgen-0.8.0rc1-py3-none-any.whl'),
    file('cadgen-0.8.1-py3-none-any.whl', true), file('cadgen-0.8.1.tar.gz', 'broken'),
  ],
};
const at = { now: NOW };
const release = (version, uploaded) => [file(`cadgen-${version}-py3-none-any.whl`, false, uploaded), file(`cadgen-${version}.tar.gz`, false, uploaded)];
const pageWith = (...files) => ({ ...PAGE, files: [...PAGE.files, ...files.flat()] });

// PyPI over a fetch that counts what it was asked and answers `answer()`.
function pypi(answer) {
  const asked = [];
  return {
    asked,
    fetch: async (url, init) => { asked.push([url, init.headers.accept]); return answer(); },
  };
}
const json = body => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/vnd.pypi.simple.v1+json' } });
const quiet = () => {};

test('the feed names the newest release PyPI has an unyanked file of: never a pre-release or a yanked release', () => {
  // 0.7.10 is newer than 0.7.9 by number, not by text; 0.8.0rc1 is a pre-release; every file of 0.8.1 is yanked.
  assert.equal(latestOf(PAGE, at), '0.7.18');
  assert.equal(latestOf({ ...PAGE, files: PAGE.files.slice(0, 4) }, at), '0.7.10');
  for (const broken of [null, {}, { files: 'x' }, { files: [{ filename: 7 }, null, { filename: 'other-1.0.0.tar.gz' }] }]) {
    assert.equal(latestOf(broken, at), null);
  }
});

test("PyPI's index is read once for every request a few minutes bring, and kept while PyPI fails", async () => {
  let clock = NOW;
  let answer = () => json(PAGE);
  const index = pypi(() => answer());
  const { versions } = pypiFeeds({ fetch: index.fetch, now: () => clock, log: quiet });
  const [first, second] = await Promise.all([versions(), versions()]);
  assert.deepEqual([first, second], [{ latest: '0.7.18' }, { latest: '0.7.18' }]);
  assert.deepEqual(index.asked, [[INDEX, 'application/vnd.pypi.simple.v1+json']]);
  // A release lands: the feed names it once the instance asks again.
  answer = () => json(pageWith(release('0.8.2', ago(2 * 60))));
  clock += 60_000;
  assert.deepEqual(await versions(), { latest: '0.7.18' });
  clock += 5 * 60_000;
  assert.deepEqual(await versions(), { latest: '0.8.2' });
  // PyPI down, refusing or answering nonsense: what was read stands, and is asked again only minutes later.
  for (const failing of [() => { throw new TypeError('fetch failed'); }, () => new Response('', { status: 503 }), () => json({ files: [] })]) {
    answer = failing;
    clock += 5 * 60_000;
    const before = index.asked.length;
    assert.deepEqual(await versions(), { latest: '0.8.2' });
    assert.deepEqual(await versions(), { latest: '0.8.2' });
    assert.equal(index.asked.length, before + 1);
  }
});

test('with nothing read and PyPI failing there is no feed, and a hang is a failure', async () => {
  const logged = [];
  const down = pypiFeeds({ fetch: async () => new Response('', { status: 502 }), log: (...line) => logged.push(line.join(' ')) }).versions;
  assert.equal(await down(), null);
  // Its status alone is logged.
  assert.deepEqual(logged, ['version feed: PyPI failed: pypi_502']);
  // A request in flight is what keeps a process waiting (a socket); `AbortSignal.timeout`'s timer alone does not,
  // so the hung request holds a timer of its own until it is aborted.
  const hang = (url, { signal }) => new Promise((_, reject) => {
    const held = setInterval(() => {}, 1000);
    signal.addEventListener('abort', () => { clearInterval(held); reject(signal.reason); });
  });
  const hung = pypiFeeds({ fetch: hang, log: quiet, timeout: 1 }).versions;
  assert.equal(await hung(), null);
});

test('a failed first read waits before retrying PyPI, then recovers when the interval expires', async () => {
  let clock = NOW;
  let answer = () => new Response('', { status: 503 });
  const index = pypi(() => answer());
  const { versions } = pypiFeeds({ fetch: index.fetch, now: () => clock, log: quiet });
  assert.deepEqual(await Promise.all([versions(), versions()]), [null, null]);
  assert.equal(index.asked.length, 1);
  assert.equal(await versions(), null);
  clock = NOW + 5 * 60_000 - 1;
  assert.equal(await versions(), null);
  assert.equal(index.asked.length, 1, 'a cold failure observes the same retry interval as a warm one');

  clock += 1;
  assert.deepEqual(await Promise.all([versions(), versions()]), [null, null]);
  assert.equal(index.asked.length, 2, 'concurrent callers share the retry');
  // PyPI recovers; the failure is not permanent, and a good feed resumes normal caching.
  answer = () => json(PAGE);
  clock += 5 * 60_000;
  assert.deepEqual(await versions(), { latest: '0.7.18' });
  assert.deepEqual(await versions(), { latest: '0.7.18' });
  assert.equal(index.asked.length, 3);
});

test('a release is named once every file of it has been on PyPI an hour: 59 minutes is too new, 61 is not', () => {
  assert.equal(MIN_AGE_MS, 60 * MINUTE);
  assert.equal(latestOf(pageWith(release('0.9.0', ago(59))), at), '0.7.18');
  assert.equal(latestOf(pageWith(release('0.9.0', ago(61))), at), '0.9.0');
  assert.equal(latestOf(pageWith(release('0.9.0', ago(60))), at), '0.9.0', 'an hour to the millisecond is old enough');
  // Its newest file decides: an sdist uploaded 59 minutes ago holds back a wheel uploaded the day before.
  assert.equal(latestOf(pageWith(file('cadgen-0.9.0-py3-none-any.whl', false, ago(24 * 60)), file('cadgen-0.9.0.tar.gz', false, ago(59))), at), '0.7.18');
  // A yanked file of it does not count, old or new.
  assert.equal(latestOf(pageWith(release('0.9.0', ago(61)), file('cadgen-0.9.0-cp314-none-any.whl', 'bad wheel', ago(1))), at), '0.9.0');
  // An upload time in the future (a clock that disagrees) is not old enough either.
  assert.equal(latestOf(pageWith(release('0.9.0', new Date(NOW + MINUTE).toISOString())), at), '0.7.18');
});

test('a release with no usable upload time is not old enough', () => {
  const timed = (filename, uploaded) => ({ ...file(filename), 'upload-time': uploaded });
  const untimed = filename => { const { 'upload-time': _, ...rest } = file(filename); return rest; };
  const without = [untimed('cadgen-0.9.0-py3-none-any.whl'), ...[null, '', 'yesterday', 1763380800, '2026-11-17', '2026-13-45T99:00:00Z']
    .map(uploaded => timed('cadgen-0.9.0-py3-none-any.whl', uploaded))];
  for (const each of without) {
    assert.equal(latestOf(pageWith(each), at), '0.7.18', String(each['upload-time']));
    // One file without a time holds back a release whose other file has one.
    assert.equal(latestOf(pageWith(file('cadgen-0.9.0.tar.gz', false, ago(120)), each), at), '0.7.18');
  }
  // PyPI's own shape (microseconds, Z) and an offset are both read.
  assert.equal(latestOf(pageWith(release('0.9.0', '2026-11-17T10:58:59.123456Z')), at), '0.9.0');
  assert.equal(latestOf(pageWith(release('0.9.0', '2026-11-17T11:58:59+01:00')), at), '0.9.0');
});

test('a held release is passed over, and the newest release that qualifies is named in its place', () => {
  const page = pageWith(release('0.9.0', ago(3 * 60)), release('0.9.1', ago(2 * 60)), release('0.9.2', ago(10)));
  // 0.9.2 is too new, so 0.9.1 is named; held, 0.9.1 gives way to 0.9.0, never to nothing.
  assert.equal(latestOf(page, at), '0.9.1');
  assert.equal(latestOf(page, { ...at, held: new Set(['0.9.1']) }), '0.9.0');
  assert.equal(latestOf(page, { ...at, held: new Set(['0.9.0', '0.9.1']) }), '0.7.18');
  // Holding a release that is too new anyway changes nothing; once it is old enough, the hold is what keeps it out.
  assert.equal(latestOf(page, { ...at, held: new Set(['0.9.2']) }), '0.9.1');
  assert.equal(latestOf(page, { now: NOW + 2 * 60 * MINUTE, held: new Set(['0.9.2']) }), '0.9.1');
  assert.equal(latestOf(page, { now: NOW + 2 * 60 * MINUTE }), '0.9.2');
});

test("the project's hold list is read from CAD_HELD_RELEASES, and anything but a release in it is ignored and logged", () => {
  const logged = [];
  const log = (...line) => logged.push(line.join(' '));
  assert.deepEqual([...heldOf({ CAD_HELD_RELEASES: ' 0.12.0, 0.12.1  0.13.0rc1,,v0.12.2 ' }, log)], ['0.12.0', '0.12.1']);
  assert.deepEqual(logged, [
    'version feed: CAD_HELD_RELEASES names no release: "0.13.0rc1"',
    'version feed: CAD_HELD_RELEASES names no release: "v0.12.2"',
    'version feed: holding 0.12.0, 0.12.1',
  ]);
  for (const env of [{}, { CAD_HELD_RELEASES: '' }, undefined, null]) assert.equal(heldOf(env, log).size, 0);
});

test("another owner's yanked releases are never named, whatever their number or age", () => {
  // PyPI's `cad` project holds 0.8.0 to 1.1.2 from 2020, every file yanked, some with a reason and some `true`;
  // the same in cadgen's index is passed over, and a `cad` file is never read as a cadgen release.
  const foreign = ['0.8.0', '0.9.9.1', '1.0', '1.0.4', '1.1.1', '1.1.2'].flatMap((version, i) => [
    file(`cadgen-${version}.tar.gz`, i % 2 ? true : 'This project changed hands on 2026-10-31.', '2020-09-10T02:27:23.207541Z'),
    file(`cad-${version}.tar.gz`, false, '2020-09-10T02:27:23.207541Z'),
  ]);
  assert.equal(latestOf(pageWith(foreign), at), '0.7.18');
  assert.equal(latestOf({ files: foreign.filter(each => each.filename.startsWith('cad-')) }, at), null);
  // A yank given as an empty reason, or anything but false, is still a yank.
  assert.equal(latestOf(pageWith(file('cadgen-1.1.2-py3-none-any.whl', '', ago(24 * 60))), at), '0.7.18');
});

test("the old address's answer keeps its shape, {latest} alone, held releases or not", async () => {
  const page = pageWith(release('0.9.0', ago(3 * 60)), release('0.9.1', ago(30)));
  for (const held of [new Set(), new Set(['0.9.0'])]) {
    const { versions } = pypiFeeds({ fetch: async () => json(page), now: () => NOW, log: quiet, held });
    const feed = await versions();
    assert.deepEqual(Object.keys(feed), ['latest']);
    assert.match(feed.latest, /^\d+\.\d+\.\d+$/);
    assert.equal(JSON.stringify(feed), `{"latest":"${held.size ? '0.7.18' : '0.9.0'}"}`);
  }
});

test('a release becomes the feed an hour after PyPI took it, on the read after that', async () => {
  let clock = NOW;
  const page = pageWith(release('0.9.0', new Date(NOW).toISOString()));
  const { versions } = pypiFeeds({ fetch: async () => json(page), now: () => clock, log: quiet });
  assert.deepEqual(await versions(), { latest: '0.7.18' });
  clock += 59 * MINUTE;
  assert.deepEqual(await versions(), { latest: '0.7.18' });
  clock += 6 * MINUTE;
  assert.deepEqual(await versions(), { latest: '0.9.0' });
});

test('every release held or too new with nothing read before: no feed, as when PyPI fails', async () => {
  const page = { files: release('0.9.0', ago(10)) };
  const logged = [];
  const { versions } = pypiFeeds({ fetch: async () => json(page), now: () => NOW, log: (...line) => logged.push(line.join(' ')) });
  assert.equal(await versions(), null);
  assert.deepEqual(logged, ['version feed: PyPI failed: pypi_no_release']);
});

// The two addresses: `/v1/releases` (`releases`) for cad 0.11.12 and later, `/v1/versions` (`versions`) frozen for
// 0.7.12 to 0.11.11, which names nothing at or above 0.12.0.
const LATER = pageWith(
  release('0.11.11', ago(30 * 24 * 60)), release('0.11.14', ago(3 * 60)), release('0.12.0', ago(2 * 60)),
  release('0.12.3', ago(90)), release('1.0.2', ago(80)), release('1.4.0', ago(70)), release('2.0.0', ago(65)),
);

test('the old address names the newest 0.11.x once later releases exist, and the new one each major and the newest', () => {
  assert.equal(OLD_BELOW, '0.12.0');
  const { releases, versions } = feedsOf(LATER, at);
  assert.deepEqual(versions, { latest: '0.11.14' });
  assert.deepEqual(releases, { latest: '2.0.0', lines: { 0: '0.12.3', 1: '1.4.0', 2: '2.0.0' } });
  // One entry per major, keyed by its number as JSON keys are, smallest first.
  assert.equal(JSON.stringify(releases), '{"latest":"2.0.0","lines":{"0":"0.12.3","1":"1.4.0","2":"2.0.0"}}');
  assert.equal(JSON.stringify(versions), '{"latest":"0.11.14"}');
  // 0.12.0 alone above 0.11 is enough to keep it out of the old address.
  assert.deepEqual(feedsOf(pageWith(release('0.11.14', ago(3 * 60)), release('0.12.0', ago(2 * 60))), at).versions,
    { latest: '0.11.14' });
});

test('with nothing at or above 0.12.0, the old address answers exactly what it did, and the new one the same latest', () => {
  for (const page of [PAGE, pageWith(release('0.9.0', ago(61))), pageWith(release('0.11.14', ago(61)), release('0.11.9', ago(600)))]) {
    const { releases, versions } = feedsOf(page, at);
    assert.deepEqual(versions, { latest: latestOf(page, at) });
    assert.deepEqual(releases, { latest: versions.latest, lines: { 0: versions.latest } });
  }
  assert.equal(feedsOf({ files: release('0.9.0', ago(10)) }, at), null, 'no release at all: no feed at either');
});

test('a held or too new release is passed over at both addresses', () => {
  // Too new: 2.0.0 (an hour less a minute) and 0.11.15; held: 1.4.0 and 0.11.14.
  const page = pageWith(LATER.files, release('2.0.0', ago(59)), release('0.11.15', ago(30)));
  const held = new Set(['1.4.0', '0.11.14']);
  const { releases, versions } = feedsOf(page, { ...at, held });
  assert.deepEqual(versions, { latest: '0.11.11' });
  assert.deepEqual(releases, { latest: '1.0.2', lines: { 0: '0.12.3', 1: '1.0.2' } });
  // A major whose every release is held or too new has no line, never an empty one.
  assert.equal('2' in releases.lines, false);
  // Every release at or above 0.12.0 qualifies and nothing below it does: the old address has no feed (503), the new one does.
  const above = feedsOf({ files: [...release('0.11.14', ago(10)), ...release('0.12.0', ago(120))] }, at);
  assert.deepEqual([above.versions, above.releases], [null, { latest: '0.12.0', lines: { 0: '0.12.0' } }]);
});

test('both addresses come from one read of PyPI, each in its own shape', async () => {
  const index = pypi(() => json(LATER));
  const { releases, versions } = pypiFeeds({ fetch: index.fetch, now: () => NOW, log: quiet });
  const [both, old] = await Promise.all([releases(), versions()]);
  assert.deepEqual(Object.keys(both), ['latest', 'lines']);
  assert.deepEqual(Object.keys(old), ['latest']);
  assert.deepEqual([both.latest, old.latest], ['2.0.0', '0.11.14']);
  assert.deepEqual(await releases(), both);
  assert.equal(index.asked.length, 1);
  // PyPI failing with nothing read: neither has a feed.
  const down = pypiFeeds({ fetch: async () => new Response('', { status: 502 }), log: quiet });
  assert.deepEqual([await down.releases(), await down.versions()], [null, null]);
});
