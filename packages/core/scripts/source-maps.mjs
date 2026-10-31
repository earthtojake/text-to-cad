/**
 * The shared packages' own source maps, for the CAD Viewer's and the CAD app's builds: a page's map leads a frame
 * in a package's code to that package's source (`src/`), with the source's text, and not to the compiled file in
 * `dist/` the page imports, so a crash there reaches PostHog as the source.
 *
 * A package's build writes a map beside each module in `dist/` (esbuild's, which keeps the source's text) and names
 * it on the module's last line (`//# sourceMappingURL=`). Rolldown reads no map a module names; it chains only the
 * map a plugin loads the module with. So a page's build loads each module of the packages it names with that map.
 * A module the package's build copied as it is (an `.mjs`) names none, and is its source: it loads with a map that
 * names the same line and column of its copy in `src/`. Once the chunks are made, a chunk whose map still ends in
 * a package's compiled code fails the build.
 */
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const MAP_LINE = /\n\/\/# sourceMappingURL=(\S+)\s*$/;
const BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function vlq(value) {
  let rest = value < 0 ? (-value << 1) | 1 : value << 1, text = '';
  do {
    const digit = rest & 31;
    rest >>>= 5;
    text += BASE64[rest ? digit | 32 : digit];
  } while (rest);
  return text;
}

// A map that sends every line and column of `code` to the same place in `source`, which `code` is a copy of.
function identityMap(code, source) {
  let mappings = '', line = 0, column = 0;  // where the previous segment points
  for (const [index, text] of code.split('\n').entries()) {
    if (index) mappings += ';';
    for (let at = 0; at < text.length; at++) {
      mappings += `${at ? ',' : ''}${vlq(at ? 1 : 0)}A${vlq(index - line)}${vlq(at - column)}`;
      line = index;
      column = at;
    }
  }
  return { version: 3, sources: [source], sourcesContent: [code], names: [], mappings };
}

/**
 * A module of a package's `dist/`, as the page's build loads it: its code, and the map that leads it to its source,
 * the one its build wrote (its sources made absolute) or, for a copy of its source, the identity. `null` for a
 * module that is neither.
 *
 * @param {string} file The module, an absolute path.
 * @param {string} dist The package's `dist/`.
 * @param {string} src The package's `src/`.
 * @returns {{ code: string, map: object } | null}
 */
export function loadWithMap(file, dist, src) {
  const code = fs.readFileSync(file, 'utf8');
  const named = MAP_LINE.exec(code);
  if (named) {
    const mapFile = path.resolve(path.dirname(file), named[1]);
    const { sourceRoot = '', ...map } = JSON.parse(fs.readFileSync(mapFile, 'utf8'));
    const base = path.resolve(path.dirname(mapFile), sourceRoot);
    return { code: code.slice(0, named.index + 1), map: { ...map, sources: map.sources.map(source => path.resolve(base, source)) } };
  }
  const twin = path.join(src, path.relative(dist, file));
  return fs.existsSync(twin) && fs.readFileSync(twin, 'utf8') === code ? { code, map: identityMap(code, twin) } : null;
}

/**
 * The Vite plugin a page's build adds, before any other that loads a module.
 *
 * @param {string[]} packages The packages whose maps the page chains, by name; the page resolves each.
 */
export function packageSourceMaps(packages) {
  let roots = [];
  const rootOf = file => roots.find(({ dist }) => file.startsWith(dist + path.sep));
  return {
    name: 'cad-package-source-maps',
    apply: 'build',
    enforce: 'pre',
    configResolved(config) {
      const require = createRequire(path.join(config.root, 'package.json'));
      roots = packages.map(name => {
        const root = fs.realpathSync(path.dirname(require.resolve(`${name}/package.json`)));
        return { name, dist: path.join(root, 'dist'), src: path.join(root, 'src') };
      });
    },
    load: {
      filter: { id: /[\\/]dist[\\/][^?]*\.m?js$/ },
      handler(id) {
        const file = path.resolve(id);
        const root = rootOf(file);
        return root ? loadWithMap(file, root.dist, root.src) : null;
      },
    },
    generateBundle: {
      order: 'pre',
      handler(options, bundle) {
        const out = options.dir ?? path.dirname(options.file);
        const compiled = [];
        for (const chunk of Object.values(bundle)) {
          if (chunk.type !== 'chunk' || !chunk.map) continue;
          for (const source of chunk.map.sources) {
            const file = path.resolve(out, path.dirname(chunk.fileName), source);
            const root = rootOf(file);
            // Code only: an image a module imports is named too, and no frame is ever in one.
            if (root && /\.m?js$/.test(file)) {
              compiled.push(`${chunk.fileName}: ${root.name}/${path.relative(path.dirname(root.dist), file).split(path.sep).join('/')}`);
            }
          }
        }
        if (compiled.length) this.error(`A chunk's map ends in a package's compiled code, not its source:\n  ${compiled.join('\n  ')}`);
      },
    },
  };
}
