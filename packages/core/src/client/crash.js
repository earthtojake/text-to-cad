/**
 * A page's crash, as cadgen's telemetry takes one (`cadgen/analytics.py`: `signature`, and the server
 * checks it again): the error's type, whether the page went on, and its innermost frames, oldest first --
 * each a script file of the page's, a function, a line and a column. Never the error's message, a value,
 * or a URL: a frame names its script by the file's own name (`fileOf`), and anything else as `<?>`.
 *
 * A host reports through `createCrashReporter`, which sends each distinct crash once per page and only
 * a few in all: a page failing in a loop sends one report, not one a frame.
 */

const MAX_FRAMES = 30;
const MAX_REPORTS = 8;
const TYPE = /^[A-Za-z_][A-Za-z0-9_.]{0,127}$/;
const FUNCTION = /^[A-Za-z_$<][A-Za-z0-9_$.<>]{0,79}$/;
// A file's own name: letters, digits and `_.+-`, never `.` or `..` alone.
const FILE = /^(?!\.\.?$)[A-Za-z0-9_.+-]{1,64}$/;
// A frame of Chromium's (`    at name (url:line:column)`, `    at url:line:column`), and of every other
// engine's (`name@url:line:column`).
const CHROMIUM = /^\s+at (?:(.*?) \()?(.+?):(\d+):(\d+)\)?$/;
const OTHERS = /^(.*?)@(.+?):(\d+):(\d+)$/;

/** A script's URL as a frame names it: the file's own name, for a script the page loaded over http(s). */
export function scriptFileOf(url) {
  try {
    const { protocol, pathname } = new URL(url);
    if (protocol !== 'http:' && protocol !== 'https:') return '<?>';
    const name = decodeURIComponent(pathname.split('/').pop() ?? '');
    return FILE.test(name) ? name : '<?>';
  } catch {
    return '<?>';
  }
}

function functionOf(name) {
  const bare = String(name ?? '').replace(/^(?:async |new )+/, '').replace(/[/<*]+$/, '').trim();
  if (!bare) return '<anonymous>';
  return FUNCTION.test(bare) ? bare : '<?>';
}

/**
 * @param {unknown} error
 * @param {{ handled?: boolean, fileOf?: (url: string) => string }} [options]
 * @returns {import('./types.js').CadPageCrash | null} `null` for what is no error (a value thrown).
 */
export function crashOf(error, { handled = false, fileOf = scriptFileOf } = {}) {
  const stack = /** @type {{ stack?: unknown }} */ (error ?? {}).stack;
  if (typeof stack !== 'string') return null;
  const name = /** @type {{ name?: unknown }} */ (error).name;
  const lines = stack.split('\n');
  // Chromium's stack opens with the message, which may span lines and look like anything: only its
  // `at` lines are frames. Other engines' stacks are frames alone.
  const chromium = lines.some(line => /^\s+at /.test(line));
  const frames = [];
  for (const line of lines) {
    const match = chromium ? CHROMIUM.exec(line) : OTHERS.exec(line.trim());
    if (!match) continue;
    const file = fileOf(match[2]);
    frames.push({
      file: FILE.test(file) || file === '<?>' ? file : '<?>',
      function: functionOf(match[1]),
      line: Math.min(Number(match[3]), 9_999_999),
      column: Math.min(Number(match[4]), 9_999_999),
    });
  }
  return {
    where: 'page',
    type: typeof name === 'string' && TYPE.test(name) ? name : '<?>',
    handled: Boolean(handled),
    frames: frames.reverse().slice(-MAX_FRAMES),
  };
}

/**
 * @param {(crash: import('./types.js').CadPageCrash) => void} send the host's way to its server
 * @param {{ fileOf?: (url: string) => string, limit?: number }} [options]
 * @returns {(error: unknown, options?: { handled?: boolean }) => void} never throws
 */
export function createCrashReporter(send, { fileOf = scriptFileOf, limit = MAX_REPORTS } = {}) {
  const sent = new Set();
  return (error, { handled = false } = {}) => {
    try {
      const crash = crashOf(error, { handled, fileOf });
      if (!crash || sent.size >= limit) return;
      const key = JSON.stringify(crash);
      if (sent.has(key)) return;
      sent.add(key);
      send(crash);
    } catch {
      // A crash report never makes another.
    }
  };
}
