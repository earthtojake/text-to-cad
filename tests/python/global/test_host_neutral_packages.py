"""Host neutrality, held by test: shared code never knows which app hosts it.

packages/core and packages/ui serve every app -- the web CAD Viewer and the Codex
plugin -- through injected host capabilities (packages/ui/docs/viewer-host.md).
cadgen is shared the same way: its Codex adapter lives in cadgen/mcp/ (plus the
`cadgen mcp` command shell), which may depend on the rest of cadgen; nothing else
in cadgen may name a host or import the adapter.

A host name, a host-protocol call, a host-identity flag or host sniffing in shared
code means an abstraction is missing. Fix the interface -- a capability, a
destination state or a named slot -- never this rule.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

SHARED_JS_ROOTS = (
    repo_path("packages/core/src"),
    repo_path("packages/core/bin"),
    repo_path("packages/ui/src"),
    repo_path("packages/ui/scripts"),
)
SHARED_JS_SUFFIXES = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".css"}
SHARED_PACKAGE_MANIFESTS = (
    repo_path("packages/core/package.json"),
    repo_path("packages/ui/package.json"),
)

CADGEN_PACKAGE = repo_path("packages/cadgen/src/cadgen")
# The adapter and its command shell: the only cadgen code allowed to know the host.
CADGEN_ADAPTER = ("mcp/", "cli/mcp.py")

# Each entry: (compiled pattern, what the match means).
HOST_NAMES = (re.compile(r"\b(?:codex|chatgpt|openai|skybridge)\b", re.IGNORECASE), "names a host")
SHARED_JS_RULES = (
    HOST_NAMES,
    (re.compile(r"\bmcp\b|modelcontextprotocol", re.IGNORECASE), "names the host protocol"),
    (
        re.compile(r"\bis(?:Web|Desktop|Codex|ChatGPT|Plugin|Sidebar|Thread|Mobile|Browser|Electron|Tauri|Host|Embedded|Iframe)\b"),
        "is a host-identity flag",
    ),
    (re.compile(r"navigator\.userAgent|userAgentData"), "sniffs the host"),
    (re.compile(r"\bwindow\.(?:parent|top|opener)\b"), "sniffs the embedding frame"),
    (
        re.compile(r"""["'`](?:ui/(?:initialize|message|update-model-context|open-link|request-display-mode)|openai/)"""),
        "calls a host protocol",
    ),
)
CADGEN_ADAPTER_IMPORT = re.compile(
    r"^\s*(?:from\s+(?:cadgen\.mcp|\.+mcp)\b|import\s+cadgen\.mcp\b|from\s+(?:cadgen|\.+)\s+import\s+(?:[^#\n]*,\s*)?mcp\b)",
    re.MULTILINE,
)


def _shared_js_files():
    for root in SHARED_JS_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix in SHARED_JS_SUFFIXES and path.is_file() and "node_modules" not in path.parts:
                yield path


def _offenses(path: Path, rules) -> list[str]:
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        for pattern, meaning in rules:
            match = pattern.search(line)
            if match:
                found.append(f"{path.relative_to(repo_path('.'))}:{number}: `{match.group(0)}` {meaning}")
    return found


def _is_adapter(path: Path) -> bool:
    relative = path.relative_to(CADGEN_PACKAGE).as_posix()
    return any(relative == entry or relative.startswith(entry) for entry in CADGEN_ADAPTER)


class SharedPackagesAreHostNeutral(unittest.TestCase):
    def test_shared_js_sources_never_name_or_detect_a_host(self) -> None:
        files = list(_shared_js_files())
        self.assertTrue(files, "no shared JS sources found; the roots moved")
        offenders = [offense for path in files for offense in _offenses(path, SHARED_JS_RULES)]
        self.assertEqual(offenders, [], "shared packages must reach hosts through injected capabilities:\n" + "\n".join(offenders))

    def test_shared_packages_depend_on_no_host_sdk(self) -> None:
        offenders = []
        for manifest in SHARED_PACKAGE_MANIFESTS:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for section in ("dependencies", "peerDependencies", "optionalDependencies", "devDependencies"):
                for name in data.get(section, {}):
                    if "modelcontextprotocol" in name or "openai" in name:
                        offenders.append(f"{manifest.name} {section}: {name}")
        self.assertEqual(offenders, [], "shared packages must not depend on a host SDK:\n" + "\n".join(offenders))


class CadgenKeepsItsHostAdapterApart(unittest.TestCase):
    def test_only_the_adapter_names_a_host_or_imports_it(self) -> None:
        sources = sorted(CADGEN_PACKAGE.rglob("*.py"))
        self.assertTrue(sources, "no cadgen sources found; the package moved")
        offenders = []
        for path in sources:
            if "_runtime" in path.relative_to(CADGEN_PACKAGE).parts or _is_adapter(path):
                continue
            offenders.extend(_offenses(path, (HOST_NAMES,)))
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in CADGEN_ADAPTER_IMPORT.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(repo_path('.'))}:{line}: imports the host adapter")
        self.assertEqual(offenders, [], "cadgen code outside its adapter must stay host-neutral:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
