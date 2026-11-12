"""What a change can break: changed paths in, the Test jobs and test files to run out.

`test.yml`'s first job runs this. Every changed path -- added, modified or deleted -- goes
through RULES, a short table of components: the directories whose change a job or a suite
has to see. A path selects the union of the rules it matches, except that a FINAL rule ends
the search (prose in a code tree). A path no rule matches runs everything, as do VERSION, the
dependency manifests, packages/core and the test machinery. Selection is by path, never by
what a file says: a comment in a module selects what the module's code would, and no rule
reads a file to decide.

One flag, one job: a job runs whole on its flag or is skipped. `static` needs none: the
version and tree checks, the light contracts (every policy test but HEAVY_POLICY, and
LIGHT_SKILL_TESTS: tests that need nothing installed) and the API's tests run on every change,
so a path only they read selects nothing. The release tier (`floor`, `installer`) runs on a
full run: a VERSION change, the nightly schedule, a dispatch, Publish Release's call.

Outputs (GITHUB_OUTPUT): a flag per job (FLAGS, and `packages`, `skills`), the test paths the
package and skills jobs take (`packages_tests`, `skills_policy`, `skills_tests`: repo-relative,
space-separated, a suite's own directory meaning all of it), the shards the package suites are
split over (`linux_shards`, `windows_shards`), the package test files the change itself touches
(`changed_tests`, run first), `full`, and `record`, the artifact naming what this run tests:
`tested-<tree>-<scope>`. A push whose tree a successful run already recorded with the same
scope runs nothing again, and neither does the nightly run for a tree tested in full
(tested_tree.py).

    python3 scripts/github-workflows/select_checks.py            # in CI: FULL, BEFORE, GITHUB_*
    python3 scripts/github-workflows/select_checks.py --paths a b  # the selection for some paths
    python3 scripts/github-workflows/select_checks.py --light policy|skills  # the light contracts
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

# The three packages' suites, one folder each under it: the library's (cad), the server's
# (cad_server) and the shim's (cad_mcp). The packages jobs run them all.
PACKAGES_SUITE = "tests/python/packages"
POLICY_SUITE = "tests/python/global"
SKILL_SUITES = "tests/python/skills"
FLAGS = ("core_js", "web_ui", "web_client", "web_viewer", "mcp", "docs", "packaging", "kicad", "fea", "bpy", "floor",
         "routing", "installer")
# How many jobs the packages' suites are split over when they run whole (CAD_TEST_SHARD); a
# narrowed selection runs in one. Windows starts every process slower, so it takes one more.
SHARDS = {"linux": 2, "windows": 3}


@dataclasses.dataclass(frozen=True)
class Select:
    """What one rule selects: job flags, and test files or suite directories."""

    flags: frozenset[str] = frozenset()
    packages: frozenset[str] = frozenset()
    policy: frozenset[str] = frozenset()
    skills: frozenset[str] = frozenset()
    full: bool = False

    def __or__(self, other: Select) -> Select:
        return Select(
            self.flags | other.flags, self.packages | other.packages, self.policy | other.policy,
            self.skills | other.skills, self.full or other.full,
        )


def select(*, flags: Iterable[str] = (), packages: Iterable[str] = (), policy: Iterable[str] = (),
           skills: Iterable[str] = (), full: bool = False) -> Select:
    unknown = set(flags) - set(FLAGS)
    if unknown:
        raise ValueError(f"unknown flags {sorted(unknown)}")
    return Select(frozenset(flags), frozenset(packages), frozenset(policy), frozenset(skills), full)


def policy(*names: str) -> Select:
    return select(policy=[f"{POLICY_SUITE}/{name}" for name in names])


EVERYTHING = select(full=True)
NOTHING = select()


# ---- the table ---------------------------------------------------------------------------------

# Policy tests that need the CAD kernel or the built runtime. Every other file in
# tests/python/global is a LIGHT contract: a new policy test is assumed light, and `static`
# runs with nothing installed, so one that is not fails there until it is listed here.
HEAVY_POLICY = {
    "test_cli_stream_contract.py",          # the server's commands, run
    "test_viewer_renders_emitted_dxf.py",   # a DXF the library emits, through the kernel
}
# Skill suites that need nothing installed: they read their skill's files.
LIGHT_SKILL_TESTS = (
    f"{SKILL_SUITES}/print3d",
    f"{SKILL_SUITES}/render",
    f"{SKILL_SUITES}/sendcutsend",
)

# The three distributions, the deprecated alias, and the bundle the server's wheel carries.
PACKAGE_PROJECTS = ("packages/cad", "packages/cad-server", "packages/cad-mcp")
PACKAGES = (*(f"{project}/**" for project in PACKAGE_PROJECTS), "packages/aliases/**", "scripts/bundle/**")
# Whatever runs the packages: their suites on both platforms, the policy tests and skill suites
# that load them, the wheels, the bundled viewer served through them, and the jobs that run them
# with a tool installed as a person has it (netgen and CalculiX, KiCad, Blender) or on the third
# C library. Those four are minutes together and never the longest job, so every package change
# runs them: a list of the modules each one reaches was the table's most intricate part, and
# the one a new import silently outgrew.
PACKAGE_CONSUMERS = select(
    flags=["packaging", "web_viewer", "fea", "kicad", "bpy", "routing"],
    packages=[PACKAGES_SUITE], policy=[POLICY_SUITE], skills=[SKILL_SUITES],
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
        if suite == PACKAGES_SUITE:
            return select(packages=[target])
        if suite == POLICY_SUITE:
            return select(policy=[target])
        return select(skills=[target])
    return choose


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
    # Prose inside a code tree is read by the light contracts alone, never by a build or a test
    # of the code beside it. The exceptions: each distribution's README and LICENSE ship in its
    # wheel, and apps/web's Markdown links are resolved by its client tests.
    Rule((*(f"{project}/{name}" for project in PACKAGE_PROJECTS for name in ("README.md", "LICENSE")),
          "packages/aliases/*/README.md"), select(flags=["packaging"]), final=True),
    Rule(("apps/web/**/*.md",), select(flags=["web_client"]), final=True),
    Rule(("packages/**/*.md", "apps/**/*.md"), NOTHING, final=True),

    # Shared by every job, or the selection itself: everything runs.
    Rule((
        "VERSION",                       # a release is tested whole
        "package.json", "package-lock.json", "requirements-dev.txt",
        ".github/workflows/test.yml", ".github/actions/**",
        "scripts/github-workflows/select_checks.py", "scripts/github-workflows/tested_tree.py",
        "scripts/github-workflows/ci_gate.py",
        "scripts/test/common.sh", "scripts/test/unittest_files.py",
        "tests/python/support/**",
        "packages/core/**",              # bundled into the server's runtime and every app
        "scripts/build/**",              # core's and ui's library build
    ), EVERYTHING),

    # The components.
    Rule(PACKAGES, PACKAGE_CONSUMERS),
    # The snapshot runtime is built from core alone, so the UI reaches the two hosts and the
    # wheel, not the packages' suites.
    Rule(("packages/ui/**",), select(flags=["web_ui", "web_client", "web_viewer", "mcp", "packaging"])),
    Rule(("apps/web/**",), select(flags=["web_client", "web_viewer", "packaging"])),
    Rule(("apps/mcp/**",), select(flags=["mcp", "packaging"])),
    Rule(("apps/api/**",), NOTHING),  # its tests need no install: static runs them on every change
    # js-core, beside docs: check-dependencies.mjs walks every app's source, and the web and mcp
    # jobs run it for theirs.
    Rule(("apps/docs/**",), select(flags=["docs", "core_js"])),
    Rule(("skills/**",), NOTHING),  # prose and scripts the light contracts and light suites read
    Rule(("skills/fea/**",), select(skills=[f"{SKILL_SUITES}/fea"])),
    # The work-instructions template is run by the library's own test of the module it drives.
    Rule(("skills/work-instructions/**",), select(packages=[f"{PACKAGES_SUITE}/cad/test_work_instruction.py"])),
    # The installer rehearsals (install-linux.yml, install-windows.yml, which test.yml calls): the
    # workflows and the installers. The server's commands they run are rehearsed with every
    # release, a full run.
    Rule((".github/workflows/install-linux.yml", ".github/workflows/install-windows.yml", "scripts/install/**"),
         select(flags=["installer"])),
    # The one-line installers: the docs site serves copies of them, and the setup suite reads both.
    Rule(("scripts/install/install.sh", "scripts/install/install.ps1"),
         select(flags=["docs"], packages=[f"{PACKAGES_SUITE}/cad_server/test_setup.py"])),

    # A fixture one language writes and another asserts is current: the robot renderer's browser
    # fixtures are the payloads the server resolves, the board renderer's the test board's plot.
    Rule(("packages/ui/src/renderers/robot/__fixtures__/**",),
         select(packages=[f"{PACKAGES_SUITE}/cad_server/test_robot_payload.py"])),
    Rule(("packages/ui/src/renderers/board/__fixtures__/**",),
         select(packages=[f"{PACKAGES_SUITE}/cad/test_pcb_plot.py"])),

    # Tests. A suite with a job of its own (a tool installed, the floor's Python) is that job's
    # alone; a package, policy or skill test file runs itself, and anything else in its suite
    # (a helper, a fixture) the suite.
    Rule((f"{PACKAGES_SUITE}/kicad/**", "scripts/test/test-kicad.sh"), select(flags=["kicad"]), final=True),
    Rule((f"{PACKAGES_SUITE}/fea/**", "scripts/test/test-fea.sh"), select(flags=["fea"]), final=True),
    Rule((f"{PACKAGES_SUITE}/blender/**", "scripts/test/test-blender.sh"), select(flags=["bpy"]), final=True),
    Rule(("scripts/test/test-floor.sh",), select(flags=["floor"]), final=True),
    # The router's unit files run themselves in the packages jobs (below), and all of them on macOS.
    Rule((f"{PACKAGES_SUITE}/cad/test_kicad_routing*.py", "scripts/test/test-routing.sh"), select(flags=["routing"])),
    Rule((f"{PACKAGES_SUITE}/**",), _test_file(PACKAGES_SUITE, whole=PACKAGES_SUITE)),
    Rule((f"{POLICY_SUITE}/**",), _test_file(POLICY_SUITE, whole=POLICY_SUITE)),
    Rule((f"{SKILL_SUITES}/**",), _test_file(SKILL_SUITES)),
    Rule(("tests/browser/**",), select(flags=["web_viewer"])),

    # The runners, and what each one feeds.
    Rule(("scripts/test/test-python.sh",), select(packages=[PACKAGES_SUITE], skills=[SKILL_SUITES])),
    Rule(("scripts/test/test-global.sh",), select(policy=[POLICY_SUITE])),
    Rule(("scripts/test/test-js.sh", "scripts/test/check-*.mjs"), select(flags=["core_js", "web_ui", "web_client", "mcp"])),
    Rule(("scripts/test/test-docs.sh", "scripts/brand/**"), select(flags=["docs"])),
    Rule(("scripts/test/test-viewer-launch.sh", "scripts/test/test-viewer-browser.sh"), select(flags=["web_viewer"])),
    # What builds and checks the wheel: bundle.sh stamps metadata with sync-version.mjs.
    Rule((
        "scripts/test/test-installed.sh", "scripts/release/sync-version.mjs",
        "scripts/release/check-wheel-contents.sh", "scripts/release/wheel_contents.py",
        "scripts/github-workflows/check-builds.sh",
    ), select(flags=["packaging"])),

    # Read by the light contracts alone, which every change runs -- or by nothing a test runs: the
    # runners static calls, the release scripts and workflows the contracts pin, the plugin
    # manifests, configs and root prose, the manual benchmarks, and the sample models no test
    # may read.
    Rule((
        "scripts/test/test-api.sh", "scripts/test/test.sh",
        "scripts/release/**", "scripts/github-workflows/deploy-vercel-app.sh", "scripts/look/**",
        "scripts/git-hooks/**", "scripts/bench/**", "scripts/README.md",
        ".github/workflows/release-publish.yml", ".github/workflows/release-prepare.yml",
        ".github/workflows/deploy-docs.yml", ".github/workflows/deploy-api.yml",
        ".github/dependabot.yml", ".github/release.yml", ".github/FUNDING.yml", ".githooks/**",
        ".claude-plugin/**", ".codex-plugin/**", ".cursor-plugin/**", ".grok-plugin/**", "gemini-extension.json",
        "*.mcp.json", "plugin.json", "mcp.json", "skills.sh.json",
        "README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE", "docs/**",
        ".gitignore",
        "models/**",
    ), NOTHING),
)


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


# The packages' own suites: a changed test file under one is run first, ahead of its job's suite.
_PACKAGE_TEST = re.compile(rf"{re.escape(PACKAGES_SUITE)}/(?:cad|cad_server|cad_mcp)/(?:.*/)?test[^/]*\.py\Z")


# How many test files a change may touch and still have them run before the suite: past it the
# step is no quick answer but a second run of much of the suite (a change that split six files into
# eighteen spent five minutes there on Linux and six on Windows before its suites began).
CHANGED_FIRST = 6


def _changed_tests(paths: Iterable[str], packages: list[str]) -> list[str]:
    """The package test files a change itself touches, which their jobs run before the suite: a
    break in a pull request's own new test is reported in a minute or two rather than at the
    suite's end. None when they are all the selection is (the suite step runs just them), and
    none when there are more than ``CHANGED_FIRST`` of them."""
    changed = sorted({path for path in paths if _PACKAGE_TEST.match(path) and (ROOT / path).exists()})
    selected = [path for path in changed
                if any(path == chosen or path.startswith(chosen + "/") for chosen in packages)]
    return [] if selected == packages or len(selected) > CHANGED_FIRST else selected


def _shards(count: int) -> str:
    return json.dumps([f"{index}/{count}" for index in range(1, count + 1)], separators=(",", ":"))


def outputs(chosen: Select, paths: Iterable[str] = ()) -> dict[str, str]:
    """The step outputs for a selection of the changed `paths`."""
    if chosen.full:
        chosen = Select(frozenset(FLAGS), frozenset({PACKAGES_SUITE}), frozenset({POLICY_SUITE}),
                        frozenset({SKILL_SUITES}), True)
    packages = _narrow(chosen.packages, PACKAGES_SUITE)
    whole = packages == [PACKAGES_SUITE]
    heavy_policy = _heavy(_narrow(chosen.policy, POLICY_SUITE), POLICY_SUITE)
    heavy_skills = _heavy(_narrow(chosen.skills, SKILL_SUITES), SKILL_SUITES)
    result = {flag: flag in chosen.flags for flag in FLAGS}
    result.update({
        "packages": bool(packages),
        "packages_tests": " ".join(packages),
        "linux_shards": _shards(SHARDS["linux"] if whole else 1),
        "windows_shards": _shards(SHARDS["windows"] if whole else 1),
        "changed_tests": " ".join(_changed_tests(paths, packages)),
        "skills": bool(heavy_policy or heavy_skills),
        "skills_policy": " ".join(heavy_policy),
        "skills_tests": " ".join(heavy_skills),
        "full": chosen.full,
    })
    return {key: (("true" if value else "false") if isinstance(value, bool) else value) for key, value in result.items()}


def scope(selected: dict[str, str]) -> str:
    """`full`, or a digest of what the selection runs. Not of `changed_tests`: what runs first is
    part of what runs."""
    if selected["full"] == "true":
        return "full"
    tested = {key: value for key, value in selected.items() if key != "changed_tests"}
    digest = hashlib.sha256(json.dumps(tested, sort_keys=True).encode("utf-8")).hexdigest()
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


def _tested(names: list[str]) -> bool:
    """Whether a successful run of this repository already recorded one of `names`
    (tested_tree.py, which treats any failure to look as "not tested")."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tested_tree

    return tested_tree.main(names) == 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--paths"]:
        print(json.dumps(outputs(select_paths(argv[1:]), argv[1:]), indent=2))
        return 0
    if argv[:1] == ["--light"]:
        lists = {"policy": light_policy(), "skills": list(LIGHT_SKILL_TESTS)}
        if argv[1:] not in ([name] for name in lists):
            print("usage: select_checks.py --light policy|skills", file=sys.stderr)
            return 2
        print(" ".join(lists[argv[1]]))
        return 0

    event = os.environ.get("GITHUB_EVENT_NAME", "")
    full = os.environ.get("FULL", "") == "true"
    paths = None if full else changed_paths(os.environ.get("BEFORE", ""))
    chosen = EVERYTHING if paths is None else select_paths(paths)
    selected = outputs(chosen, paths or ())
    tree = _git("rev-parse", "HEAD^{tree}").strip()
    record = f"tested-{tree}-{scope(selected)}"
    note = f"Selected from {'everything' if paths is None else f'{len(paths)} changed path(s)'}."

    # A push repeats what its pull request ran on the same tree, and the nightly run what a full
    # run (a release's, normally) already ran on main's: nothing runs again when that run succeeded.
    already = None
    if not full and paths and event == "push":
        already = [record] + ([] if selected["full"] == "true" else [f"tested-{tree}-full"])
    elif event == "schedule":
        already = [f"tested-{tree}-full"]
    if already and _tested(already):
        selected = outputs(NOTHING)
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
