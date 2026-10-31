/**
 * The debug id each chunk of a page goes by, for the CAD Viewer's and the CAD app's builds. A page names
 * its chunks' ids (`__cadChunkIds`, which ../src/client/crash.js reads into a crash's frames), and a release
 * files each chunk's source map in PostHog under the chunk's id, which keeps one map an id.
 *
 * So one id must name one chunk's text with one map, in every page and every release. A bundler's id
 * names the code alone (rolldown's does): the CAD app, which rewrites a chunk's imports, would run other
 * text under the id the CAD Viewer's copy of that chunk goes by, and a source change that moves no code,
 * such as a comment, would keep a chunk's id with a new map. A page's build therefore stamps each chunk
 * anew, with an id its text and its map decide together.
 */
import { createHash } from 'node:crypto';

// The bundler's closing `//# debugId=` line (its `sourcemapDebugIds`): where a chunk names its id.
const DEBUG_ID_LINE = /\/\/# debugId=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=\s*$)/;

/**
 * A chunk and its source map, stamped with the debug id their text decides: the chunk's closing
 * `//# debugId=` line and the map's `debugId` both name it. The line comes after the code, so the map fits
 * the chunk as it did.
 *
 * @param {string} code The chunk as the page runs it, ending with its bundler's `//# debugId=` line.
 * @param {string} map Its source map, as JSON.
 * @param {string} [file] The chunk's name, for an error.
 * @returns {{ code: string, map: string, debugId: string }}
 */
export function stampDebugId(code, map, file = 'A chunk') {
  if (!DEBUG_ID_LINE.test(code)) throw new Error(`${file} does not end with its bundler's //# debugId= line.`);
  const hex = createHash('sha256').update(code).update('\0').update(map).digest('hex');
  // Laid out as a version 4 UUID, as a debug id is.
  const debugId = [hex.slice(0, 8), hex.slice(8, 12), `4${hex.slice(13, 16)}`,
    (8 | (parseInt(hex[16], 16) & 3)).toString(16) + hex.slice(17, 20), hex.slice(20, 32)].join('-');
  return {
    code: code.replace(DEBUG_ID_LINE, () => `//# debugId=${debugId}`),
    map: JSON.stringify({ ...JSON.parse(map), debugId }),
    debugId,
  };
}
