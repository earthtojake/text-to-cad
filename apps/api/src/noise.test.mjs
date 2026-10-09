import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import { handle } from './handler.mjs';
import { NEVER_OURS, withoutNoise } from './noise.mjs';

const USER = { file: '<user>', function: '<user>', line: 0 };
const crash = (fields, frames = []) => ({ event: 'exception', handled: true, count: 1, frames, ...fields });

// Each signature on the drop list, as released clients sent it to PostHog.
const NOISE = {
  page_left: [
    crash({ where: 'route', type: 'ConnectionAbortedError' }, [{ file: 'cadgen/viewer/response.py', function: 'Response._begin', line: 130 },
      { file: 'http/server.py', function: 'BaseHTTPRequestHandler.end_headers', line: 549 }, { file: 'socketserver.py', function: '_SocketWriter.write', line: 845 }]),
    ...['ConnectionResetError', 'BrokenPipeError', 'ConnectionError'].map(type => crash({ where: 'route', type })),
  ],
  output_closed: [crash({ where: 'command', type: 'BrokenPipeError', handled: false },
    [{ file: 'cadgen/cli/__init__.py', function: 'main', line: 288 }, { file: 'cadgen/cli/store.py', function: '_why_one', line: 193 }])],
  no_such_build123d_name: [crash({ where: 'build', type: 'AttributeError' },
    [{ file: 'cadgen/cli/_run_model.py', function: '_run', line: 185 }, USER, { file: 'cadgen/build123d.py', function: '__getattr__', line: 49 }])],
  colour_not_a_string: [crash({ where: 'build', type: 'AttributeError' },
    [USER, { file: 'cadgen/color.py', function: 'srgb', line: 66 }, { file: 'cadgen/color.py', function: '_parse_hex', line: 42 }])],
  worker_stopped: [-15, -2, -1].map(status => crash({ where: 'build', type: 'WorkerDied', handled: false, status })),
  their_recursion: [crash({ where: 'build', type: 'RecursionError' }, [
    ...Array(14).fill([USER, { file: 'cadgen/authoring.py', function: '_decorator.<locals>._apply.<locals>.model', line: 573 }]).flat(),
    { file: 'cadgen/authoring.py', function: '_same_file', line: 223 }, { file: 'pathlib/_local.py', function: 'PurePath.__str__', line: 233 }])],
};

// cadgen's bugs, which look like noise in one way or another: every one goes on to PostHog.
const BUGS = [
  crash({ where: 'tool', tool: 'cad_show', type: 'ConnectionAbortedError' }), // only a route's peer leaving is no bug
  crash({ where: 'command', type: 'ConnectionResetError' }),
  crash({ where: 'request', type: 'BrokenPipeError' }),
  crash({ where: 'build', type: 'WorkerDied', handled: false }), // no status: Windows says nothing of a signal
  ...[-11, -6, -9, 1, 106].map(status => crash({ where: 'build', type: 'WorkerDied', handled: false, status })),
  crash({ where: 'build', type: 'AttributeError' }, [{ file: 'cadgen/_internal/mesh_export.py', function: 'run_mesh_exporter', line: 137 }]),
  // build123d's own name lookup failing deeper in, or cadgen's code (not the person's) asking for a name.
  crash({ where: 'build', type: 'AttributeError' }, [USER, { file: 'cadgen/build123d.py', function: '__getattr__', line: 49 },
    { file: 'build123d/__init__.py', function: '<module>', line: 3 }]),
  crash({ where: 'build', type: 'AttributeError' }, [{ file: 'cadgen/_internal/generation.py', function: 'build', line: 9 },
    { file: 'cadgen/build123d.py', function: '__getattr__', line: 49 }]),
  crash({ where: 'build', type: 'KeyError' }, [USER, { file: 'cadgen/color.py', function: '_parse_hex', line: 42 }]),
  crash({ where: 'build', type: 'RecursionError' }, Array(30).fill({ file: 'cadgen/_internal/tree.py', function: 'walk', line: 12 })),
  crash({ where: 'tool', tool: 'cad_sync', type: 'OSError' }, [{ file: 'cadgen/_internal/atomic_replace.py', function: 'write_bytes_atomic', line: 246 },
    { file: 'pathlib/_local.py', function: 'Path.open', line: 537 }]),
  crash({ where: 'page', type: 'NotFoundError' }, [{ file: 'assets/vendor-react.js', function: 'Au', line: 8, column: 109111 }]),
];

test('each signature on the drop list leaves out the crashes it names, counted by name', () => {
  assert.deepEqual(Object.keys(NOISE), NEVER_OURS.map(({ name }) => name), 'every signature is tested');
  for (const [name, rows] of Object.entries(NOISE)) {
    const { rows: kept, dropped } = withoutNoise(rows.map(row => ({ ...row, count: 2 })));
    assert.deepEqual([kept, [...dropped]], [[], [[name, 2 * rows.length]]], name);
  }
});

test("cadgen's own bugs, and every row that is not a crash, all go on", () => {
  const counts = [{ event: 'tool', tool: 'cad_show', calls: 3, errors: 1 }, { event: 'health', workers: 1, crashes: 1, recycles: 0, refusals: 0 },
    // Not a crash, whatever it says.
    { event: 'build', where: 'route', type: 'ConnectionAbortedError', status: -15, frames: [], count: 1 }];
  const { rows, dropped } = withoutNoise([...BUGS, ...counts]);
  assert.deepEqual([rows, dropped.size], [[...BUGS, ...counts], 0]);
});

const INSTALL = '8c347ec3-1342-4db5-a19a-491cbc8c59be';
const SESSION = '0b1e6f1a-6a52-4c39-9d43-2f5e0f0b9d11';
const batch = events => ({ schema: 3, install: INSTALL, session: SESSION, process: 'viewer', version: '0.7.17', channel: 'codex-github',
  platform: 'win32', arch: 'AMD64', client: { name: 'cadgen-viewer' }, presentation: 'browser', events });
const named = ({ event, ...fields }) => ({ name: event, ...fields });

test('a batch with noise in it is taken whole: its other rows are stored, and one line counts what was left out', async () => {
  const stored = [];
  const store = { async insert(rows) { stored.push(rows); }, async forget() {}, async ready() {} };
  const lines = [];
  const info = mock.method(console, 'info', (...args) => lines.push(args.join(' ')));
  const post = events => handle(new Request('https://api.texttocad.dev/v1/events', {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(batch(events)),
  }), store, { country: 'DE' });
  try {
    const left = { ...named(NOISE.page_left[0]), count: 3 };
    const bug = named(BUGS.at(-2));
    assert.equal((await post([{ name: 'view', calls: 4 }, left, named(NOISE.page_left[1]), bug])).status, 204);
    assert.deepEqual(stored.map(rows => rows.map(row => row.event)), [['view', 'exception']]);
    assert.equal(stored[0][1].type, 'OSError');
    // Nothing but noise: taken, and nothing for PostHog.
    assert.equal((await post([named(NOISE.worker_stopped[0])])).status, 204);
    // Nothing dropped: nothing said.
    assert.equal((await post([{ name: 'view', calls: 1 }])).status, 204);
  } finally { info.mock.restore(); }
  assert.equal(stored.length, 2);
  assert.deepEqual(lines, [
    'telemetry dropped page_left 4 (schema 3, cadgen 0.7.17)',
    'telemetry dropped worker_stopped 1 (schema 3, cadgen 0.7.17)',
  ]);
});
