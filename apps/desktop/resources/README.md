# resources/

What ships beside the app instead of inside the asar. `electron-builder.yml`
copies each directory here into the packaged app's `Resources/`, and
`process.resourcesPath` is where main reads them back.

| Directory | Filled by | Contents |
| --- | --- | --- |
| `runtime/<os>-<arch>/` | `npm run bundle:runtime` (`scripts/bundle-runtime.mjs`), and the release workflow per leg | **The CAD runtime.** A pinned python-build-standalone (`scripts/python-build.json`) with cadgen and its whole dependency closure installed into its site-packages, pruned of what a runtime never reads, bytecode-compiled, and marked complete by `runtime.json`. About 1.2 GB per target; the app resolves it first after an explicit override (`src/main/cad/runtime.ts`). Packaged as `Resources/runtime/<os>-<arch>/`, the same layout as here. |
| `cadgen/` | the release workflow, or `npm run cad:resources` (`scripts/cad-resources.mjs`) | the `cadgen` wheel for this version and `constraints.txt`, the dependency closure frozen from the development venv — what the bundler installs from (the wheel by its path, `-c` that file) |
| `skills/` | `npm run build` (`scripts/build-skills.mjs`) | the app's skills — the repo's authoring skills plus the focused skills declared in the integration registry (including the embedded `cad-viewer` override), one directory each. `src/main/integrations/skills.ts` copies them into `<userData>/skills/<version>/` in both native layouts and hands that directory to every session; nothing is installed into an agent's own configuration |
| `sample/` | committed | the sample project onboarding offers: `l_bracket.py` and the `l_bracket.step` it builds. Main copies it to `~/Documents/text-to-cad Sample` the first time someone asks for it (`src/main/onboarding.ts`). |
| `text-to-cad-mcp/` | committed source | the text-to-cad MCP server (`server.mjs`); NOT an extraResource — the build bundles it into `out/text-to-cad-mcp/`, which ships unpacked beside the asar |
| `brand/` | `npm run brand` (`scripts/make-brand.mjs`), committed | the TEXT-TO-CAD wordmark as PNGs, plus the JetBrains Mono ExtraBold Italic face they are set in and its OFL licence. NOT an extraResource either — `scripts/make-icons.mjs` reads `brand/text-to-cad-h.png` at development time to write `build/icon.png`, and nothing here is opened at run time. See the README's **Brand** section |

The first three are build outputs: gitignored under a committed `.gitkeep`,
and `scripts/package.mjs` recreates the directories before every build.
electron-builder 26 tolerates a missing `extraResources` source (checked,
26.15.3: the build succeeds and copies nothing), but a tolerance is a thing a
minor release can withdraw, and the alternative — generating the config per
build — is worse than three empty directories.

## The runtime

```sh
scripts/bundle/bundle.sh --clean               # build cadgen's ignored package runtime
npm run cad:resources                       # the wheel + constraints, from the checkout's .venv
npm run bundle:runtime                      # this machine's target (mac-arm64 here)
npm run bundle:runtime -- --target mac-x64  # a foreign target, from this machine
```

Targets are electron-builder's `<os>-<arch>` names: `mac-arm64`, `mac-x64`,
`win-x64`, `linux-x64`. Per target the bundler downloads the pinned
interpreter into `~/.cache/text-to-cad/python` (or `--cache`, or
`TEXT_TO_CAD_RUNTIME_CACHE`; sha256-checked), unpacks it,
runs `pip install --only-binary=:all: --platform <tags> --target
<site-packages> cadgen==<VERSION> -c constraints.txt`, prunes (`tests/`,
`__pycache__`, the stdlib's test suite, static libraries, the `bin/` of
console scripts pip wrote with a build-machine shebang, and the interpreter's
own `pip*`, `idle*`, `wheel*` and `*-config` launchers in `python/bin/` or
`python/Scripts/`), writes PEP 668's `EXTERNALLY-MANAGED` into the stdlib
directory, compiles every module
to `unchecked-hash` pycs — the bundle is read-only once installed, and the app
runs it with `PYTHONDONTWRITEBYTECODE` — probes it (`import cadgen`,
`import cadgen.viewer`, the version equals the app's), and writes
`runtime.json` last.

**Cross-target works from one host** because pip never runs the target's
interpreter: with `--platform` and `--only-binary=:all:` it only picks wheels
for it, and cadgen's closure is wheels on every packaged target (checked from
this Mac: win_amd64, manylinux_2_31/2014 x86_64, macosx_11_0 x86_64). A
foreign target uses a host Python for pip and — if it is the pin's minor
(3.13) — for the bytecode; without one the bundle ships without pycs and says
so. A foreign bundle is checked on disk (the dist-info, the package, the
viewer), not probed: this machine cannot run it. The release workflow
therefore bundles per leg — macOS builds `mac-arm64` natively and `mac-x64`
cross (probed under Rosetta when the runner has it), Windows and Linux build
their own — and never ships a bundle that was not at least resolved on the
leg that packages it.

**Agents cannot install into it.** A session's PATH carries `cadgen`,
`python3` and `python` launchers from `<userData>/bin` that run the bundled
interpreter (`CadRuntime.sessionPath`), never the bundle's own `bin/`. The
bundle is inside a signed, read-only app and its packages are the closure
cadgen was validated with, so `python3 -m pip install -U numpy` from an agent
is refused by the `EXTERNALLY-MANAGED` marker with a message naming the app
and the way out — `python3 -m venv --system-site-packages .venv`, which still
imports the CAD packages — instead of breaking the signature and the pins or
failing with EACCES. `pip install --target <dir>` is still allowed.

`scripts/package.mjs` refuses to package a target whose runtime is missing,
is not this version of cadgen, or was built from another interpreter pin
(`runtime.json`'s `python` and `release` against `scripts/python-build.json`)
(`--no-runtime` overrides, for a build whose purpose is not CAD). It also
refuses to run without a real VERSION: `scripts/app-version.mjs` answers
`0.0.0` when the file is missing, and an installer stamped 0.0.0 would never
be offered an update. An app packaged without one says "The CAD runtime did not start" on
its first STEP file, which is the report this refusal exists to prevent.

### Signing, later

The runtime's `bin/python3.13`, `lib/*.dylib` and every `*.so` under
site-packages are Mach-O and will need signing when mac signing lands
(`mac.binaries` in `electron-builder.yml`, or a walk in an `afterSign` hook).
`Resources/` is a fine home for them as long as each is signed; the layout
does not have to change. electron-builder copies extraResources with mode
bits and symlinks intact (`python/bin/python3 -> python3.13`), and the dmg and
zip carry both.

Nothing in here is generated by `scripts/bundle/bundle.sh`; the desktop app
ships its runtime from PyPI wheels and python-build-standalone, not from the
repo's JS bundlers (repo AGENTS.md).
