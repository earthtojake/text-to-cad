import assert from 'node:assert/strict';
import { test } from 'node:test';
import { INDEX, latestOf, pypiVersions } from './versions.mjs';

// PyPI's simple index for cadgen, as uv reads it (PEP 691 JSON): a wheel and an sdist per release.
const file = (filename, yanked = false) => ({ filename, yanked, hashes: {}, url: `https://files.pythonhosted.org/${filename}` });
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
  assert.equal(latestOf(PAGE), '0.7.18');
  assert.equal(latestOf({ ...PAGE, files: PAGE.files.slice(0, 4) }), '0.7.10');
  for (const broken of [null, {}, { files: 'x' }, { files: [{ filename: 7 }, null, { filename: 'other-1.0.0.tar.gz' }] }]) {
    assert.equal(latestOf(broken), null);
  }
});

test("PyPI's index is read once for every request a few minutes bring, and kept while PyPI fails", async () => {
  let clock = 0;
  let answer = () => json(PAGE);
  const index = pypi(() => answer());
  const versions = pypiVersions({ fetch: index.fetch, now: () => clock, log: quiet });
  const [first, second] = await Promise.all([versions(), versions()]);
  assert.deepEqual([first, second], [{ latest: '0.7.18' }, { latest: '0.7.18' }]);
  assert.deepEqual(index.asked, [[INDEX, 'application/vnd.pypi.simple.v1+json']]);
  // A release lands: the feed names it once the instance asks again.
  answer = () => json({ ...PAGE, files: [...PAGE.files, file('cadgen-0.8.2-py3-none-any.whl')] });
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
  const down = pypiVersions({ fetch: async () => new Response('', { status: 502 }), log: (...line) => logged.push(line.join(' ')) });
  assert.equal(await down(), null);
  // Its status alone is logged.
  assert.deepEqual(logged, ['version feed: PyPI failed: pypi_502']);
  const hung = pypiVersions({ fetch: (url, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(signal.reason))), log: quiet, timeout: 1 });
  assert.equal(await hung(), null);
});
