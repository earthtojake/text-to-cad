import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chunkIdOf, crashOf, createCrashReporter, scriptFileOf } from './crash.js';

const chromium = Object.assign(new TypeError("Cannot read properties of undefined (reading 'secret-bracket')"), {
  stack: [
    "TypeError: Cannot read properties of undefined (reading 'secret-bracket')",
    '    at mesh.ts:1:2 is not a frame of a message at all',
    '    at Kt (http://127.0.0.1:3245/assets/index-Bx3k2.js:1:48213)',
    '    at async Object.load (http://127.0.0.1:3245/assets/vendor-three-9fA_2.js:2:100)',
    '    at http://127.0.0.1:3245/assets/index-Bx3k2.js?v=3:1:999',
    '    at new Sheet (file:///Users/someone/secret/app.js:10:5)',
    '    at chrome-extension://abcdefgh/inject.js:1:1',
  ].join('\n'),
});

test("a crash names its type and its script frames, oldest first, and never its message or a URL", () => {
  const crash = crashOf(chromium);
  assert.deepEqual(crash, {
    where: 'page', type: 'TypeError', handled: false,
    frames: [
      { file: '<?>', function: '<anonymous>', line: 1, column: 1 },
      { file: '<?>', function: 'Sheet', line: 10, column: 5 },
      { file: 'index-Bx3k2.js', function: '<anonymous>', line: 1, column: 999 },
      { file: 'vendor-three-9fA_2.js', function: 'Object.load', line: 2, column: 100 },
      { file: 'index-Bx3k2.js', function: 'Kt', line: 1, column: 48213 },
    ],
  });
  const said = JSON.stringify(crash);
  for (const secret of ['secret', 'someone', '127.0.0.1', 'abcdefgh', 'Cannot read']) assert.ok(!said.includes(secret), secret);
});

test("a frame in one of the page's own chunks names the chunk's debug id, which the build wrote into the page", () => {
  globalThis.__cadChunkIds = { 'index-Bx3k2.js': '0de4d024-c159-4f6d-b15a-cc4ef7a6856d', 'vendor-three-9fA_2.js': 'not an id' };
  try {
    const frames = crashOf(chromium).frames;
    assert.deepEqual(frames.map(frame => [frame.file, frame.chunk_id]), [
      ['<?>', undefined], ['<?>', undefined], ['index-Bx3k2.js', '0de4d024-c159-4f6d-b15a-cc4ef7a6856d'],
      ['vendor-three-9fA_2.js', undefined], ['index-Bx3k2.js', '0de4d024-c159-4f6d-b15a-cc4ef7a6856d'],
    ]);
    assert.equal(chunkIdOf('<?>'), undefined);
  } finally {
    delete globalThis.__cadChunkIds;
  }
});

test("other engines' stacks are frames alone, and a host can name its own scripts", () => {
  const firefox = Object.assign(new RangeError('x'), {
    stack: 'draw@blob:https://sandbox.example/1d7f-4c2e:1:3044\nrender/<@blob:https://sandbox.example/77aa-0b19:12:7\n@debugger eval code:1:1\n',
  });
  const chunks = { 'blob:https://sandbox.example/1d7f-4c2e': 'index-Bx3k2.js' };
  assert.deepEqual(crashOf(firefox, { handled: true, fileOf: url => chunks[url] ?? '<?>' }), {
    where: 'page', type: 'RangeError', handled: true,
    frames: [
      { file: '<?>', function: '<anonymous>', line: 1, column: 1 },
      { file: '<?>', function: 'render', line: 12, column: 7 },
      { file: 'index-Bx3k2.js', function: 'draw', line: 1, column: 3044 },
    ],
  });
  // A host's name for a script is taken only if it is a file's own name.
  assert.equal(crashOf(firefox, { fileOf: () => '/Users/someone/x.js' }).frames[0].file, '<?>');
});

test("what is no error -- a value thrown, a cross-origin script's error -- is no crash, and a type that is no name is <?>", () => {
  for (const thrown of ['a secret string', 42, null, undefined, { message: 'secret' }]) assert.equal(crashOf(thrown), null);
  assert.equal(crashOf(Object.assign(new Error('x'), { name: 'Error: secret part' })).type, '<?>');
  const deep = Object.assign(new Error('x'), { stack: Array.from({ length: 50 }, (_, i) => `    at f${i} (https://h/assets/a.js:${i + 1}:1)`).join('\n') });
  const frames = crashOf(deep).frames;
  assert.equal(frames.length, 30);
  assert.equal(frames.at(-1).function, 'f0', 'the innermost frame is kept');
});

test('a reporter sends each distinct crash once, a few in all, and never throws', () => {
  const sent = [];
  const report = createCrashReporter(crash => sent.push(crash), { limit: 2 });
  for (let i = 0; i < 100; i += 1) report(chromium); // a page failing in a loop
  report('not an error');
  report(Object.assign(new SyntaxError('x'), { stack: '    at a (https://h/assets/a.js:1:1)' }));
  report(Object.assign(new SyntaxError('y'), { stack: '    at b (https://h/assets/b.js:1:1)' }), { handled: true });
  assert.deepEqual(sent.map(crash => crash.type), ['TypeError', 'SyntaxError']);
  const broken = createCrashReporter(() => { throw new Error('the transport'); });
  assert.doesNotThrow(() => broken(chromium));
  assert.equal(scriptFileOf('not a url'), '<?>');
});
