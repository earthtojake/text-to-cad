"""Map changed paths to CI contracts. No source/diff parsing or third-party deps.

Dorny supplies added, modified, deleted and renamed paths; selection deliberately
never checks whether a path still exists. Unknown infrastructure stays conservative.
"""
from __future__ import annotations

import json
import os
from pathlib import PurePosixPath

FLAGS = ("cadgen", "core", "ui", "web", "skills", "docs", "infra",
         "policy", "skill_prose", "skill_examples", "packaging")

# Exact exceptions to the shared-infrastructure fallback. A workflow is mapped
# to its contract, not every suite it happens to invoke during a release.
SCOPED = {
    ".github/workflows/release-publish.yml": {"packaging", "policy"},
    ".github/workflows/release-prepare.yml": {"policy"},
    ".github/workflows/deploy-docs.yml": {"docs"},
    "scripts/github-workflows/deploy-vercel-app.sh": {"docs"},
    "scripts/github-workflows/check-builds.sh": {"packaging", "policy"},
    "scripts/test/test-viewer-launch.sh": {"web"},
    "scripts/test/test-viewer-browser.sh": {"web"},
    "scripts/test/test-installed.sh": {"packaging"},
    "scripts/test/test-docs.sh": {"docs"},
    "scripts/test/test-global.sh": {"policy"},
    "scripts/test/test-skill-docs.sh": {"policy", "skill_prose", "skill_examples"},
    "scripts/test/skill_doc_contracts.py": {"policy", "skill_prose", "skill_examples"},
    "scripts/test/test-python.sh": {"cadgen", "skills"},
    "scripts/utils/list-skills.sh": {"skills", "policy"},
    "scripts/test/unittest_files.py": {"cadgen", "skills"},
    "scripts/test/check-dependencies.mjs": {"core", "ui", "web"},
    "scripts/test/check-dependencies.test.mjs": {"core", "ui", "web"},
    "scripts/test/check-kit-boundaries.mjs": {"core", "ui", "web"},
    "scripts/test/check-kit-boundaries.test.mjs": {"core", "ui", "web"},
    "scripts/release/check-wheel-contents.sh": {"packaging", "policy"},
    "scripts/release/check-pr-version.sh": {"policy"},
    "scripts/release/check-version.sh": {"policy"},
    "scripts/release/bump-version.sh": {"policy"},
    "scripts/release/pin-cadgen-requirements.sh": {"policy"},
    "scripts/release/publish-github-release.sh": {"policy"},
    "scripts/release/release-tags.sh": {"policy"},
    "scripts/install/install-skills.sh": {"policy"},
    "scripts/install/uninstall-skills.sh": {"policy"},
    # sync-version is also a bundle input, so it keeps the broad fallback.
    "scripts/release/sync-version.mjs": {"infra"},
}


def select(paths: list[str], *, manual: bool = False) -> dict[str, object]:
    flags = set(FLAGS) if manual else set()
    names = set()
    all_docs = manual
    for path in paths:
        parts = PurePosixPath(path).parts
        if path in SCOPED:
            flags.update(SCOPED[path])
            all_docs = all_docs or "skill_examples" in SCOPED[path]
        elif path.startswith("skills/"):
            # Only Markdown and agent display metadata are prose. Requirements,
            # scripts, templates, assets and unknown file types remain executable.
            if path.endswith(".md") or (len(parts) > 2 and parts[2] == "agents" and path.endswith((".yaml", ".yml"))):
                flags.add("skill_prose")
                if len(parts) > 2:
                    names.add(parts[1])
                    if parts[1] in {"cad", "dxf"}:
                        flags.add("skill_examples")
            else:
                flags.add("skills")
        elif path.startswith("tests/python/skills/"):
            flags.add("skills")
        elif path.startswith("tests/python/global/"):
            flags.add("policy")
        elif path.startswith(("packages/cadgen/", "tests/python/packages/", "tests/python/support/")) or (path.startswith("requirements") and path.endswith(".txt")):
            flags.add("cadgen")
        elif path.startswith("packages/core/"):
            flags.add("core")
        elif path.startswith("packages/ui/"):
            flags.add("ui")
        elif path.startswith(("apps/web/", "tests/browser/")):
            flags.add("web")
        elif path.startswith("apps/docs/"):
            flags.add("docs")
        elif path.startswith((".claude-plugin/", ".codex-plugin/")):
            flags.add("policy")
        elif path.startswith(("scripts/", ".github/")) or path in {"VERSION", "package.json", "package-lock.json", ".gitattributes", ".gitignore"}:
            flags.add("infra")
    result = {name: name in flags for name in FLAGS}
    # Empty means all document contracts (manual run or runner changes).
    result["skill_names"] = [] if all_docs else sorted(names)
    return result


def main() -> None:
    paths = json.loads(os.environ["CHANGED_PATHS"])
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError("CHANGED_PATHS must be a JSON array of paths")
    result = select(paths, manual=os.environ.get("EVENT_NAME") == "workflow_dispatch")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name, value in result.items():
            output.write(f"{name}={json.dumps(value)}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
