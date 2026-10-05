"""What a change can break: changed paths in, the Test jobs and test files to run out.

`test.yml`'s first job runs this. Every changed path -- added, modified or deleted -- goes
through RULES, a table of what READS that path: the tests that open it, scan it, import it,
build it or run it, and the jobs that build or ship it. A path selects the union of the
rules it matches, except that a FINAL rule ends the search (prose in a code tree). A path
no rule matches runs everything: a new kind of file is tested whole until someone writes
down what reads it. VERSION, the shared test machinery, the dependency manifests and
packages/core (which every runtime and app is built from) run everything too.

The light contracts -- every policy test but HEAVY_POLICY, and the skill suites in
LIGHT_SKILL_TESTS: tests that need nothing but Python's standard library, Node and the
repository's text -- run on every change, first and with nothing installed, so a path only
they read needs no rule beyond saying so. The rest -- the cadgen suite, the skill suites that
drive the CAD kernel, the policy tests that load cadgen or its built runtime, and each job --
run only on the paths that reach them.

Selection is by path, never by diff content: a comment in a module selects what the
module's code would.

Outputs (GITHUB_OUTPUT), one flag per job and the test paths the narrowed jobs take:

    cadgen  cadgen_tests          cadgen (Linux), cadgen (Windows)
    core_js                       core-js
    web  web_ui  web_client  web_viewer
    mcp
    skills  light_policy  light_tests  skills_policy  skills_tests  skills_runtime
    docs
    packaging
    full
    record                        the artifact name recording what this run tests

Test paths are repo-relative and space-separated; a suite's own directory means the whole
suite. A run's record is `tested-<tree>-<scope>`: the git tree it checked out, and `full`
or a digest of the selection. On a push, a successful run of this repository that already
recorded the same tree and scope (its pull request's, normally) stands in for this one, and
nothing runs again (tested_tree.py).

    python3 scripts/github-workflows/select_checks.py            # in CI: FULL, BEFORE, GITHUB_*
    python3 scripts/github-workflows/select_checks.py --paths a b  # the selection for some paths
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]

CADGEN_SUITE = "tests/python/packages/cadgen"
POLICY_SUITE = "tests/python/global"
SKILL_SUITES = "tests/python/skills"
FLAGS = ("core_js", "web_ui", "web_client", "web_viewer", "mcp", "docs", "packaging")


@dataclasses.dataclass(frozen=True)
class Select:
    """What one rule selects: job flags, and test files or suite directories."""

    flags: frozenset[str] = frozenset()
    cadgen: frozenset[str] = frozenset()
    policy: frozenset[str] = frozenset()
    skills: frozenset[str] = frozenset()
    full: bool = False

    def __or__(self, other: Select) -> Select:
        return Select(
            self.flags | other.flags, self.cadgen | other.cadgen, self.policy | other.policy,
            self.skills | other.skills, self.full or other.full,
        )


def select(*, flags: Iterable[str] = (), cadgen: Iterable[str] = (), policy: Iterable[str] = (),
           skills: Iterable[str] = (), full: bool = False) -> Select:
    unknown = set(flags) - set(FLAGS)
    if unknown:
        raise ValueError(f"unknown flags {sorted(unknown)}")
    return Select(frozenset(flags), frozenset(cadgen), frozenset(policy), frozenset(skills), full)


def policy(*names: str) -> Select:
    return select(policy=[f"{POLICY_SUITE}/{name}" for name in names])


EVERYTHING = select(full=True)
NOTHING = select()


# ---- the table ---------------------------------------------------------------------------------

# Policy tests that need the CAD kernel or the built runtime. Every other file in
# tests/python/global is a LIGHT contract: a new policy test is assumed light, and the light
# phase runs with nothing installed, so one that is not fails there until it is listed here
# with a rule for what it reads.
HEAVY_POLICY = {
    "test_cache_root_sync.py",              # cadgen's cache paths against core's tessellation cache
    "test_cli_stream_contract.py",          # cadgen CLIs, run
    "test_node_builder_bundles.py",         # the emitted Node builders (scripts/bundle)
    "test_sidecar_and_package_layering.py",  # cadgen's import layering, imported
    "test_snapshot_viewer_theme_parity.py",  # cadgen's snapshot against core's view settings
    "test_viewer_renders_emitted_dxf.py",   # a DXF cadgen emits, through the kernel
}
# Skill suites that need nothing installed: they read their skill's files.
LIGHT_SKILL_TESTS = (
    f"{SKILL_SUITES}/gcode",
    f"{SKILL_SUITES}/sendcutsend",
    f"{SKILL_SUITES}/step-parts",
)
# The skill suites that drive cadgen's CLIs, and so read everything cadgen reads.
CADGEN_SKILL_SUITES = (f"{SKILL_SUITES}/cad", f"{SKILL_SUITES}/dxf")

# Whatever runs cadgen: its suites on both platforms, the skill suites that drive it, the
# policy tests that load it, the viewer gates that serve and build through it, the wheel.
CADGEN_CONSUMERS = select(
    flags=["web_viewer", "packaging"], cadgen=[CADGEN_SUITE], skills=CADGEN_SKILL_SUITES,
    policy=[f"{POLICY_SUITE}/{name}" for name in sorted(HEAVY_POLICY)],
)


def _test_file(suite: str, whole: str | None = None) -> Callable[[str], Select]:
    """A test file selects itself; any other file in a suite (a helper, a fixture) selects
    the suite it belongs to -- `whole`, or the suite's top directory under `suite`."""
    def choose(path: str) -> Select:
        name = path.rsplit("/", 1)[-1]
        if name.startswith("test") and name.endswith(".py"):
            target = path
        elif whole is not None:
            target = whole
        else:
            target = "/".join(path.split("/")[: len(suite.split("/")) + 1])
        if suite == CADGEN_SUITE:
            return select(cadgen=[target])
        if suite == POLICY_SUITE:
            return select(policy=[target])
        return select(skills=[target])
    return choose


# The CAD Viewer's backend and the CAD app's server are leaves of cadgen: outside them and the
# commands that start them, nothing in cadgen imports either, except viewer.recents (the state
# directory's one definition) -- tests/python/global/test_viewer_and_mcp_boundary.py holds
# that. So a change confined to one of them reaches only the cadgen tests that import or
# start it, which name it (or a support module that does), and the tests that read or import
# all of cadgen at once; and, for the viewer, the gates that serve the bundled client. The
# skill suites and the heavy policy tests reach neither.
CADGEN_SRC = "packages/cadgen/src/cadgen"
VIEWER_CODE = (f"{CADGEN_SRC}/viewer/**", f"{CADGEN_SRC}/cli/viewer.py", f"{CADGEN_SRC}/cli/viewer_stop.py")
MCP_CODE = (f"{CADGEN_SRC}/mcp/**", f"{CADGEN_SRC}/cli/mcp.py")
VIEWER_SHARED = (f"{CADGEN_SRC}/viewer/__init__.py", f"{CADGEN_SRC}/viewer/recents.py")
_NAMES_VIEWER = r"cadgen\.viewer|cadgen\.mcp|cli\.viewer|cli\.mcp|[\"'](?:viewer|mcp)[\"' ]"
_NAMES_MCP = r"cadgen\.mcp|cli\.mcp|[\"']mcp[\"' ]"
# A test that reads every cadgen source, or imports modules it computes -- every command in
# the registry, say -- reaches both.
_READS_ALL = (r"_COMMANDS|walk_packages|iter_modules|r?glob\(\s*[\"'](?:\*\*/)?\*\.py[\"']"
              r"|import_module\(\s*(?![\"'])|__import__\(\s*(?![\"'])")


def _cadgen_tests_naming(names: str, directories: tuple[str, ...]) -> list[str]:
    """The cadgen tests a change to a leaf can reach: those in `directories`, and those whose
    text names it, names a support module that does, or reads all of cadgen."""
    support = [path.stem for path in sorted((ROOT / "tests/python/support").glob("*.py"))
               if re.search(names, path.read_text(encoding="utf-8", errors="replace"))]
    pattern = re.compile("|".join([names, _READS_ALL] + [rf"\b{re.escape(stem)}\b" for stem in support]))
    found = []
    for path in sorted((ROOT / CADGEN_SUITE).rglob("test*.py")):
        relative = path.relative_to(ROOT).as_posix()
        inside = any(relative.startswith(f"{CADGEN_SUITE}/{directory}/") for directory in directories)
        if inside or pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            found.append(relative)
    return found


def _viewer_change(path: str) -> Select:
    return select(flags=["web_viewer", "packaging"], cadgen=_cadgen_tests_naming(_NAMES_VIEWER, ("viewer", "mcp")))


def _mcp_change(path: str) -> Select:
    return select(flags=["packaging"], cadgen=_cadgen_tests_naming(_NAMES_MCP, ("mcp",)))


_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def web_link_targets() -> list[str]:
    """The files apps/web's Markdown links to: its client tests require each to exist."""
    targets = set()
    for document in sorted((ROOT / "apps/web").rglob("*.md")):
        if "node_modules" in document.parts:
            continue
        for target in _MARKDOWN_LINK.findall(document.read_text(encoding="utf-8", errors="replace")):
            if re.match(r"(?:[a-z][a-z0-9+.-]*:|#|<)", target, re.I):
                continue
            resolved = (document.parent / target.split("#")[0]).resolve()
            try:
                targets.add(resolved.relative_to(ROOT).as_posix())
            except ValueError:
                continue
    return sorted(targets)


@dataclasses.dataclass(frozen=True)
class Rule:
    patterns: tuple[str, ...]
    selects: Select | Callable[[str], Select]
    final: bool = False


RULES: tuple[Rule, ...] = (
    # Prose inside a code tree is read by the policy contracts alone (the package boundary
    # law, documented commands), never by a build or a test of the code beside it. The one
    # exception, cadgen's README, is the wheel's long description.
    Rule(("packages/cadgen/README.md", "packages/cadgen/LICENSE"), select(flags=["packaging"]), final=True),
    Rule(("apps/web/**/*.md",), select(flags=["web_client"]), final=True),  # its links must resolve
    Rule(("packages/**/*.md", "apps/**/*.md"), NOTHING, final=True),

    # Shared by every job, or the selection itself: everything runs.
    Rule((
        "VERSION",                       # a release is tested whole
        "package.json", "package-lock.json", "requirements-dev.txt",
        ".github/workflows/test.yml", ".github/actions/**",
        "scripts/github-workflows/select_checks.py", "scripts/github-workflows/tested_tree.py",
        "scripts/test/common.sh", "scripts/test/unittest_files.py",
        "tests/python/support/**",
        "packages/core/**",              # bundled into cadgen's runtime and every app
        "scripts/build/**",              # core's and ui's library build
    ), EVERYTHING),

    # cadgen, and the runtime bundle it executes. The viewer's backend and the CAD app's
    # server reach only what names them (above).
    Rule(VIEWER_SHARED, CADGEN_CONSUMERS, final=True),
    Rule(VIEWER_CODE, _viewer_change, final=True),
    Rule(MCP_CODE, _mcp_change, final=True),
    Rule(("packages/cadgen/**", "scripts/bundle/**"), CADGEN_CONSUMERS),

    # The shared UI and the apps. The snapshot runtime is built from core alone, so ui
    # reaches the two hosts and the wheel, not cadgen's suites.
    Rule(("packages/ui/**",), select(flags=["web_ui", "web_client", "web_viewer", "mcp", "packaging"])),
    Rule(("apps/web/**",), select(flags=["web_client", "web_viewer", "packaging"])),
    Rule(("apps/mcp/**",), select(flags=["mcp", "packaging"])),
    Rule(("apps/docs/**",), select(flags=["docs"])),
    # check-dependencies.mjs walks every app's source and runs in core-js, the cheapest job
    # that has it.
    Rule(("apps/docs/src/**",), select(flags=["core_js"])),
    # The DXF suite renders ui's DXF fixture, and holds every JS file in packages/ to having
    # no second layer-intent table; cadgen's suite globs packages/ for vendored node runtimes.
    Rule(("packages/ui/src/renderers/dxf/__fixtures__/**",), select(skills=[f"{SKILL_SUITES}/dxf/test_snapshot_render.py"])),
    Rule(("packages/ui/**/*.js",), select(skills=[f"{SKILL_SUITES}/dxf/test_drawing_checks.py"])),
    Rule(("packages/ui/**/node_runtime.py",), select(cadgen=[f"{CADGEN_SUITE}/test_node_resolve_bootstrap.py"])),
    Rule(("tests/browser/**", "tests/fixtures/cad/**"), select(flags=["web_viewer"])),

    # Tests: a test file runs itself.
    Rule((f"{CADGEN_SUITE}/**",), _test_file(CADGEN_SUITE, whole=CADGEN_SUITE)),
    Rule((f"{POLICY_SUITE}/**",), _test_file(POLICY_SUITE, whole=POLICY_SUITE)),
    Rule((f"{SKILL_SUITES}/**",), _test_file(SKILL_SUITES)),

    # Skills. Their prose and metadata are read by the policy contracts (light, always) and by
    # the tests that run what a skill documents; scripts by their skill's suite.
    Rule(("skills/**",), NOTHING),
    Rule(("skills/cad/**",), select(skills=[f"{SKILL_SUITES}/cad/test_documented_models.py",
                                            f"{SKILL_SUITES}/cad/test_documented_project.py"])),
    Rule(("skills/cad/references/snapshot-review.md",), select(cadgen=[f"{CADGEN_SUITE}/test_snapshot_requests.py"])),
    Rule(("skills/dxf/**",), select(skills=[f"{SKILL_SUITES}/dxf/test_documented_commands.py"])),
    Rule(("skills/dfam-check/**",), select(skills=[f"{SKILL_SUITES}/dfam-check"])),
    Rule(("skills/dfm/**",), select(skills=[f"{SKILL_SUITES}/dfm"])),
    # Files that must never appear here: the test that refuses one runs when one does.
    Rule(("skills/**/node_runtime.py",), select(cadgen=[f"{CADGEN_SUITE}/test_node_resolve_bootstrap.py"])),
    Rule(("skills/*/scripts/packages/**",), policy("test_node_builder_bundles.py")),

    # The test runners and the gates each one feeds.
    Rule(("scripts/test/test-python.sh",), select(cadgen=[CADGEN_SUITE], skills=[SKILL_SUITES])),
    Rule(("scripts/test/test-global.sh",), select(policy=[POLICY_SUITE])),
    Rule(("scripts/test/test-js.sh", "scripts/test/check-*.mjs"), select(flags=["core_js", "web_ui", "web_client", "mcp"])),
    Rule(("scripts/test/test-docs.sh", "scripts/brand/**"), select(flags=["docs"])),
    Rule(("scripts/test/test-viewer-launch.sh", "scripts/test/test-viewer-browser.sh"), select(flags=["web_viewer"])),
    Rule(("scripts/test/test-installed.sh",), select(flags=["packaging"])),
    Rule(("scripts/test/test.sh",), NOTHING),  # chains the runners for a local run; CI calls them itself
    Rule(("scripts/bench/viewer-memory/**",), select(flags=["core_js"])),

    # What builds and checks the wheel: bundle.sh stamps metadata with sync-version.mjs.
    Rule((
        "scripts/release/sync-version.mjs", "scripts/release/check-wheel-contents.sh",
        "scripts/release/wheel_contents.py", "scripts/github-workflows/check-builds.sh",
    ), select(flags=["packaging"])),

    # Read by the policy contracts alone (light, always) -- or by nothing a test runs: the
    # release scripts and workflows the contracts pin, the plugin manifests, configs and
    # root prose, the deploy, and the sample models no test may read.
    Rule((
        "scripts/release/**", "scripts/install/**", "scripts/github-workflows/deploy-vercel-app.sh",
        "scripts/git-hooks/**", "scripts/bench/cadgen-performance/**", "scripts/README.md",
        ".github/workflows/release-publish.yml", ".github/workflows/release-prepare.yml",
        ".github/workflows/deploy-docs.yml",
        ".github/dependabot.yml", ".github/release.yml", ".githooks/**",
        ".claude-plugin/**", ".codex-plugin/**", ".cursor-plugin/**", "gemini-extension.json",
        "*.mcp.json", "skills.sh.json",
        "README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE", "docs/**",
        ".gitignore",
        "models/**",
    ), NOTHING),
)


# Rules for files that must not exist: they match nothing until someone adds one.
ABSENT_ON_PURPOSE = frozenset({
    "skills/**/node_runtime.py", "skills/*/scripts/packages/**", "packages/ui/**/node_runtime.py",
})


def compile_glob(pattern: str) -> re.Pattern[str]:
    """`**` crosses directories, `*` and `?` do not."""
    expression = ""
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            expression += "(?:.*/)?"
            index += 3
        elif pattern.startswith("**", index):
            expression += ".*"
            index += 2
        elif pattern[index] == "*":
            expression += "[^/]*"
            index += 1
        elif pattern[index] == "?":
            expression += "[^/]"
            index += 1
        else:
            expression += re.escape(pattern[index])
            index += 1
    return re.compile(expression + r"\Z")


def rules() -> tuple[Rule, ...]:
    """RULES, after the rules read from the checkout: the files apps/web's Markdown links to."""
    return (Rule(tuple(web_link_targets()), select(flags=["web_client"])),) + RULES


def select_paths(paths: Iterable[str]) -> Select:
    compiled = [([compile_glob(pattern) for pattern in rule.patterns], rule) for rule in rules()]
    chosen = NOTHING
    for path in paths:
        matched = False
        for patterns, rule in compiled:
            if any(pattern.match(path) for pattern in patterns):
                matched = True
                chosen |= rule.selects(path) if callable(rule.selects) else rule.selects
                if rule.final:
                    break
        if not matched:
            chosen |= EVERYTHING
    return chosen


def light_policy() -> list[str]:
    return sorted(
        path.relative_to(ROOT).as_posix() for path in (ROOT / POLICY_SUITE).glob("test_*.py")
        if path.name not in HEAVY_POLICY
    )


def _light(path: str) -> bool:
    return path in light_policy() or any(path == light or path.startswith(light + "/") for light in LIGHT_SKILL_TESTS)


def _narrow(paths: Iterable[str], suite: str) -> list[str]:
    """Sorted paths to pass a runner: the suite alone when it is selected whole, and only
    what exists -- a deleted test file has nothing left to run."""
    paths = set(paths)
    if suite in paths:
        return [suite]
    kept = sorted(path for path in paths if (ROOT / path).exists())
    return [path for path in kept if not any(path.startswith(other + "/") for other in kept if other != path)]


def _heavy(paths: list[str], suite: str) -> list[str]:
    """What the heavy phase runs: the selection less the light tests, which always run."""
    if paths == [suite]:
        if suite == POLICY_SUITE:
            return [f"{POLICY_SUITE}/{name}" for name in sorted(HEAVY_POLICY)]
        return [directory.relative_to(ROOT).as_posix() for directory in sorted((ROOT / suite).iterdir())
                if directory.is_dir() and any(directory.rglob("test*.py"))
                and directory.relative_to(ROOT).as_posix() not in LIGHT_SKILL_TESTS]
    return [path for path in paths if not _light(path)]


def outputs(chosen: Select, *, changed: bool = True) -> dict[str, str]:
    """The step outputs for a selection. `changed` is false when nothing runs at all."""
    if chosen.full:
        chosen = Select(frozenset(FLAGS), frozenset({CADGEN_SUITE}), frozenset({POLICY_SUITE}),
                        frozenset({SKILL_SUITES}), True)
    cadgen = _narrow(chosen.cadgen, CADGEN_SUITE)
    heavy_policy = _heavy(_narrow(chosen.policy, POLICY_SUITE), POLICY_SUITE)
    heavy_skills = _heavy(_narrow(chosen.skills, SKILL_SUITES), SKILL_SUITES)
    result = {flag: flag in chosen.flags for flag in FLAGS}
    result.update({
        "cadgen": bool(cadgen),
        "cadgen_tests": " ".join(cadgen),
        "web": result["web_ui"] or result["web_client"] or result["web_viewer"],
        "skills": changed,
        "light_policy": " ".join(light_policy()) if changed else "",
        "light_tests": " ".join(LIGHT_SKILL_TESTS) if changed else "",
        "skills_policy": " ".join(heavy_policy),
        "skills_tests": " ".join(heavy_skills),
        "skills_runtime": bool(heavy_policy or heavy_skills),
        "full": chosen.full,
    })
    return {key: (("true" if value else "false") if isinstance(value, bool) else value) for key, value in result.items()}


def scope(selected: dict[str, str]) -> str:
    if selected["full"] == "true":
        return "full"
    digest = hashlib.sha256(json.dumps(selected, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def changed_paths(before: str) -> list[str] | None:
    """Every path the change touches, or None when it cannot be known (then: everything).

    A pull request is tested on its merge commit, whose first parent is the target branch
    as it is now. A push compares against `before`, fetched when the checkout lacks it.
    """
    try:
        if not before:
            _git("rev-parse", "--verify", "--quiet", "HEAD^2")  # a merge commit, or no diff to take
            base = "HEAD^1"
        elif set(before) == {"0"}:
            return None
        else:
            if subprocess.run(["git", "cat-file", "-e", f"{before}^{{commit}}"], cwd=ROOT,
                              capture_output=True).returncode != 0:
                _git("fetch", "--quiet", "--depth=1", "origin", before)
            base = before
        listing = _git("diff", "--no-renames", "--name-only", "-z", base, "HEAD")
    except subprocess.CalledProcessError:
        return None
    return [path for path in listing.split("\0") if path]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--paths"]:
        print(json.dumps(outputs(select_paths(argv[1:]), changed=len(argv) > 1), indent=2))
        return 0

    full = os.environ.get("FULL", "") == "true"
    paths = None if full else changed_paths(os.environ.get("BEFORE", ""))
    chosen = EVERYTHING if paths is None else select_paths(paths)
    selected = outputs(chosen, changed=paths is None or bool(paths))
    tree = _git("rev-parse", "HEAD^{tree}").strip()
    record = f"tested-{tree}-{scope(selected)}"
    note = f"Selected from {'everything' if paths is None else f'{len(paths)} changed path(s)'}."

    # A push repeats what its pull request ran on the same tree: skip it when that run
    # succeeded. (tested_tree.py treats any failure to look as "not tested".)
    if not full and paths and os.environ.get("GITHUB_EVENT_NAME") == "push":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import tested_tree

        names = [record] + ([] if selected["full"] == "true" else [f"tested-{tree}-full"])
        if tested_tree.main(names) == 0:
            selected = outputs(NOTHING, changed=False)
            record = ""
            note = "This tree was already tested with this selection; nothing runs again."

    summary = {"tree": tree, "paths": paths, **selected}
    temp = Path(os.environ.get("RUNNER_TEMP") or ROOT / "tmp")
    temp.mkdir(parents=True, exist_ok=True)
    (temp / "selection.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            for key, value in {**selected, "record": record}.items():
                handle.write(f"{key}={value}\n")
    print(note)
    print(json.dumps({**selected, "record": record}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
