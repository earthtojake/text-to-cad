/**
 * resolveFileIconClass — framework-agnostic devicon class resolver.
 *
 * Returns the devicon CSS class string for a given filename (e.g.
 * `"devicon-typescript-plain colored"`), or `null` when no icon is registered.
 *
 * Consumers are responsible for rendering the class — for React use
 * `<i className={cls} />`, for Solid use `<i class={cls} />`.
 * devicon.min.css must be loaded by the host application.
 */

// ── Extension → devicon class ─────────────────────────────────────────────────

const EXTENSION_MAP: Record<string, string> = {
  // TypeScript / JavaScript
  ts: 'devicon-typescript-plain colored',
  tsx: 'devicon-react-original colored',
  js: 'devicon-javascript-plain colored',
  jsx: 'devicon-react-original colored',
  mjs: 'devicon-javascript-plain colored',
  cjs: 'devicon-javascript-plain colored',
  coffee: 'devicon-coffeescript-original colored',

  // Web
  html: 'devicon-html5-plain colored',
  htm: 'devicon-html5-plain colored',
  css: 'devicon-css3-plain colored',
  scss: 'devicon-sass-original colored',
  sass: 'devicon-sass-original colored',
  less: 'devicon-less-plain-wordmark colored',
  styl: 'devicon-stylus-original',
  pug: 'devicon-pug-plain',
  jade: 'devicon-pug-plain',

  // Data / config
  json: 'devicon-json-plain colored',
  yaml: 'devicon-yaml-plain colored',
  yml: 'devicon-yaml-plain colored',
  xml: 'devicon-xml-plain colored',
  graphql: 'devicon-graphql-plain colored',
  gql: 'devicon-graphql-plain colored',
  tf: 'devicon-terraform-plain colored',
  tfvars: 'devicon-terraform-plain colored',
  prisma: 'devicon-prisma-original colored',

  // Markup
  md: 'devicon-markdown-original',
  mdx: 'devicon-markdown-original',
  tex: 'devicon-latex-original',

  // Python
  py: 'devicon-python-plain colored',
  ipynb: 'devicon-jupyter-plain colored',

  // Go
  go: 'devicon-go-original colored',

  // Rust
  rs: 'devicon-rust-original',

  // PHP
  php: 'devicon-php-plain colored',

  // Ruby
  rb: 'devicon-ruby-plain colored',

  // Java / JVM
  java: 'devicon-java-plain colored',
  kt: 'devicon-kotlin-plain colored',
  kts: 'devicon-kotlin-plain colored',
  scala: 'devicon-scala-plain colored',
  sc: 'devicon-scala-plain colored',
  groovy: 'devicon-groovy-plain colored',
  clj: 'devicon-clojure-line colored',
  cljs: 'devicon-clojure-line colored',
  cljc: 'devicon-clojure-line colored',

  // C family
  c: 'devicon-c-plain colored',
  h: 'devicon-cplusplus-plain colored',
  cpp: 'devicon-cplusplus-plain colored',
  cc: 'devicon-cplusplus-plain colored',
  cxx: 'devicon-cplusplus-plain colored',
  hpp: 'devicon-cplusplus-plain colored',
  hh: 'devicon-cplusplus-plain colored',
  hxx: 'devicon-cplusplus-plain colored',
  cs: 'devicon-csharp-plain colored',

  // Apple ecosystem
  swift: 'devicon-swift-plain colored',
  mm: 'devicon-objectivec-plain',

  // Other languages
  dart: 'devicon-dart-plain colored',
  lua: 'devicon-lua-plain colored',
  r: 'devicon-r-plain colored',
  pl: 'devicon-perl-plain colored',
  pm: 'devicon-perl-plain colored',
  ex: 'devicon-elixir-plain colored',
  exs: 'devicon-elixir-plain colored',
  erl: 'devicon-erlang-plain colored',
  hrl: 'devicon-erlang-plain colored',
  hs: 'devicon-haskell-plain colored',
  lhs: 'devicon-haskell-plain colored',
  ml: 'devicon-ocaml-plain colored',
  mli: 'devicon-ocaml-plain colored',
  fs: 'devicon-fsharp-plain colored',
  fsx: 'devicon-fsharp-plain colored',
  fsi: 'devicon-fsharp-plain colored',
  elm: 'devicon-elm-plain colored',
  jl: 'devicon-julia-plain colored',
  nim: 'devicon-nim-plain colored',
  nims: 'devicon-nim-plain colored',
  zig: 'devicon-zig-original colored',
  cr: 'devicon-crystal-original',
  vala: 'devicon-vala-plain colored',
  sol: 'devicon-solidity-plain',
  wasm: 'devicon-wasm-original colored',
  wat: 'devicon-wasm-original colored',
  vim: 'devicon-vim-plain colored',

  // Database
  sqlite: 'devicon-sqlite-plain colored',
  db: 'devicon-sqlite-plain colored',

  // Shell
  sh: 'devicon-bash-plain colored',
  bash: 'devicon-bash-plain colored',
  zsh: 'devicon-bash-plain colored',
  fish: 'devicon-bash-plain colored',
  ps1: 'devicon-powershell-plain colored',

  // Frontend frameworks
  vue: 'devicon-vuejs-plain colored',
  svelte: 'devicon-svelte-plain colored',
  astro: 'devicon-astro-plain colored',
};

// ── Full-filename overrides for well-known config files ───────────────────────

const FILENAME_MAP: Record<string, string> = {
  Dockerfile: 'devicon-docker-plain colored',
  dockerfile: 'devicon-docker-plain colored',
  '.dockerignore': 'devicon-docker-plain colored',
  'docker-compose.yml': 'devicon-docker-plain colored',
  'docker-compose.yaml': 'devicon-docker-plain colored',
  '.gitignore': 'devicon-git-plain colored',
  '.gitattributes': 'devicon-git-plain colored',
  '.gitmodules': 'devicon-git-plain colored',
  '.eslintrc': 'devicon-eslint-plain colored',
  '.eslintrc.js': 'devicon-eslint-plain colored',
  '.eslintrc.cjs': 'devicon-eslint-plain colored',
  '.eslintrc.json': 'devicon-eslint-plain colored',
  '.eslintignore': 'devicon-eslint-plain colored',
  'eslint.config.js': 'devicon-eslint-plain colored',
  'eslint.config.mjs': 'devicon-eslint-plain colored',
  'eslint.config.ts': 'devicon-eslint-plain colored',
  '.babelrc': 'devicon-babel-plain colored',
  'babel.config.js': 'devicon-babel-plain colored',
  'babel.config.json': 'devicon-babel-plain colored',
  'vite.config.ts': 'devicon-vitejs-plain colored',
  'vite.config.js': 'devicon-vitejs-plain colored',
  'vitest.config.ts': 'devicon-vitest-plain colored',
  'vitest.config.js': 'devicon-vitest-plain colored',
  'webpack.config.js': 'devicon-webpack-plain colored',
  'webpack.config.ts': 'devicon-webpack-plain colored',
  'rollup.config.js': 'devicon-rollup-plain colored',
  'rollup.config.ts': 'devicon-rollup-plain colored',
  'jest.config.js': 'devicon-jest-plain colored',
  'jest.config.ts': 'devicon-jest-plain colored',
  'tailwind.config.js': 'devicon-tailwindcss-original colored',
  'tailwind.config.ts': 'devicon-tailwindcss-original colored',
  'postcss.config.js': 'devicon-postcss-original colored',
  'postcss.config.cjs': 'devicon-postcss-original colored',
  'CMakeLists.txt': 'devicon-cmake-plain colored',
  Gemfile: 'devicon-ruby-plain colored',
  'Gemfile.lock': 'devicon-ruby-plain colored',
  'package.json': 'devicon-npm-original-wordmark colored',
  'package-lock.json': 'devicon-npm-original-wordmark colored',
  'pnpm-lock.yaml': 'devicon-pnpm-plain colored',
  'pnpm-workspace.yaml': 'devicon-pnpm-plain colored',
  'yarn.lock': 'devicon-yarn-original colored',
  '.nvmrc': 'devicon-nodejs-plain colored',
  '.node-version': 'devicon-nodejs-plain colored',
  'go.mod': 'devicon-go-original colored',
  'go.sum': 'devicon-go-original colored',
  'Cargo.toml': 'devicon-rust-original',
  'Cargo.lock': 'devicon-rust-original',
};

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Resolve a devicon CSS class string for the given filename.
 *
 * Checks full-filename overrides first (for well-known config files), then
 * falls back to the file extension. Returns `null` when no icon is registered.
 *
 * The returned string already includes the `colored` modifier where appropriate.
 * Pass it directly to `className` (React) or `class` (Solid/HTML).
 *
 * @example
 * resolveFileIconClass('index.ts')         // "devicon-typescript-plain colored"
 * resolveFileIconClass('package.json')     // "devicon-npm-original-wordmark colored"
 * resolveFileIconClass('unknown.xyz')      // null
 */
export function resolveFileIconClass(filename: string): string | null {
  if (FILENAME_MAP[filename]) return FILENAME_MAP[filename]!;
  const dot = filename.lastIndexOf('.');
  if (dot < 0) return null;
  const ext = filename.slice(dot + 1).toLowerCase();
  return EXTENSION_MAP[ext] ?? null;
}
