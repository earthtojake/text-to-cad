from __future__ import annotations

import ast
import json
import os
import re
import shlex
import tomllib
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / "skills"
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
PYTHON_SUFFIXES = {".py"}
JAVASCRIPT_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}
PACKAGE_DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
FORBIDDEN_REPO_IMPORT_ROOTS = {"packages", "skills", "viewer"}
LOOKUP_PATH_ENV_VARS = {"NODE_PATH", "PYTHONPATH"}

JS_IMPORT_RE = re.compile(
    r"(?:import|export)\s+(?:[^'\"\n]+?\s+from\s+)?['\"](?P<from>[^'\"]+)['\"]"
    r"|(?:import|require)\(\s*['\"](?P<call>[^'\"]+)['\"]\s*\)"
)
PEP508_FILE_REF_RE = re.compile(r"@\s*(file:[^\s;]+)")


def _logical_abs(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_inside(child: Path, parent: Path) -> bool:
    child_text = os.fspath(_logical_abs(child))
    parent_text = os.fspath(_logical_abs(parent))
    try:
        return os.path.commonpath([child_text, parent_text]) == parent_text
    except ValueError:
        return False


def _iter_skill_roots() -> list[Path]:
    return sorted(
        path
        for path in SKILLS_ROOT.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def _walk_files(skill_root: Path, names: set[str] | None = None) -> list[Path]:
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(skill_root, followlinks=True):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            if names is None or filename in names:
                result.append(Path(dirpath) / filename)
    return result


def _strip_requirement_line(line: str) -> str:
    try:
        parts = shlex.split(line, comments=True, posix=True)
    except ValueError:
        return line.split("#", 1)[0].strip()
    return " ".join(parts).strip()


def _path_from_file_url(spec: str) -> str:
    raw = spec[len("file:") :]
    if raw.startswith("//"):
        parsed = urlparse(spec)
        return unquote(parsed.path)
    return unquote(raw)


def _local_path_from_spec(spec: str, *, allow_bare_relative: bool = False) -> str | None:
    stripped = spec.strip().strip("'\"")
    if not stripped:
        return None

    file_ref = PEP508_FILE_REF_RE.search(stripped)
    if file_ref:
        return _path_from_file_url(file_ref.group(1))

    parsed = urlparse(stripped)
    if parsed.scheme and parsed.scheme != "file":
        return None
    if stripped.startswith("file:"):
        return _path_from_file_url(stripped)
    if stripped.startswith(("./", "../", "/", "~")) or stripped in {".", ".."}:
        return stripped
    if allow_bare_relative and "/" in stripped and not stripped.startswith("@"):
        return stripped
    return None


def _check_local_path(
    errors: list[str],
    *,
    skill_root: Path,
    manifest: Path,
    local_path: str,
    context: str,
) -> None:
    expanded = os.path.expanduser(local_path)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = manifest.parent / candidate
    if not _is_inside(candidate, skill_root):
        errors.append(
            f"{manifest.relative_to(REPO_ROOT)}: {context} points outside "
            f"{skill_root.relative_to(REPO_ROOT)}: {local_path}"
        )


def _requirement_path_specs(line: str) -> list[tuple[str, str]]:
    stripped = _strip_requirement_line(line)
    if not stripped:
        return []

    try:
        tokens = shlex.split(stripped, comments=True, posix=True)
    except ValueError:
        tokens = stripped.split()

    specs: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"-e", "--editable", "-r", "--requirement", "-c", "--constraint"}:
            if index + 1 < len(tokens):
                specs.append((token, tokens[index + 1]))
                index += 2
                continue
        for option in ("--editable=", "--requirement=", "--constraint="):
            if token.startswith(option):
                specs.append((option.rstrip("="), token[len(option) :]))
                break
        else:
            local_path = _local_path_from_spec(token)
            if local_path is not None:
                specs.append(("requirement", token))
        index += 1

    pep508_ref = PEP508_FILE_REF_RE.search(stripped)
    if pep508_ref:
        specs.append(("requirement", pep508_ref.group(1)))
    return specs


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


def _literal_int(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal_int(node.operand)
        if value is not None:
            return -value
    return None


def _literal_env_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_os_environ_target(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    if _qualified_name(node.value) != "os.environ":
        return None
    key = _literal_env_key(node.slice)
    if key in LOOKUP_PATH_ENV_VARS:
        return key
    return None


def _collect_python_path_bindings(tree: ast.AST, source: Path) -> dict[str, set[str]]:
    bindings: dict[str, set[str]] = {}
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
    ]

    for _ in range(8):
        changed = False
        for node in assignments:
            value_node = node.value
            if value_node is None:
                continue
            values = _eval_path_expr(value_node, source, bindings)
            if not values:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and bindings.get(target.id) != values:
                    bindings[target.id] = values
                    changed = True
        if not changed:
            break
    return bindings


def _eval_path_expr(
    node: ast.AST,
    source: Path,
    bindings: dict[str, set[str]],
) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return {os.fspath(source)}
        return set(bindings.get(node.id, set()))
    if isinstance(node, ast.Call):
        name = _qualified_name(node.func)
        if name in {"Path", "pathlib.Path"} and node.args:
            return _eval_path_expr(node.args[0], source, bindings)
        if name in {"str", "os.fspath"} and node.args:
            return _eval_path_expr(node.args[0], source, bindings)
        if name in {"os.path.abspath", "os.path.realpath"} and node.args:
            return {
                os.fspath(_logical_abs(Path(value)))
                for value in _eval_path_expr(node.args[0], source, bindings)
            }
        if name == "os.path.join" and node.args:
            values = [""]
            for arg in node.args:
                parts = _eval_path_expr(arg, source, bindings)
                if not parts:
                    return set()
                values = [os.path.join(prefix, part) for prefix in values for part in parts]
            return set(values)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "absolute",
            "expanduser",
            "resolve",
        }:
            values = _eval_path_expr(node.func.value, source, bindings)
            if node.func.attr == "expanduser":
                return {os.path.expanduser(value) for value in values}
            return {os.fspath(_logical_abs(Path(value))) for value in values}
        return set()
    if isinstance(node, ast.Attribute):
        values = _eval_path_expr(node.value, source, bindings)
        if node.attr == "parent":
            return {os.fspath(Path(value).parent) for value in values}
        return set()
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
    ):
        index = _literal_int(node.slice)
        if index is None:
            return set()
        result: set[str] = set()
        for value in _eval_path_expr(node.value.value, source, bindings):
            parents = Path(value).parents
            if -len(parents) <= index < len(parents):
                result.add(os.fspath(parents[index]))
        return result
    if isinstance(node, ast.BinOp):
        left_values = _eval_path_expr(node.left, source, bindings)
        right_values = _eval_path_expr(node.right, source, bindings)
        if not left_values or not right_values:
            return set()
        if isinstance(node.op, ast.Div):
            return {
                os.fspath(Path(left) / right)
                for left in left_values
                for right in right_values
            }
        if isinstance(node.op, ast.Add):
            return {left + right for left in left_values for right in right_values}
    if isinstance(node, ast.JoinedStr):
        values = [""]
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                part_values = {part.value}
            elif isinstance(part, ast.FormattedValue):
                part_values = _eval_path_expr(part.value, source, bindings)
            else:
                return set()
            if not part_values:
                return set()
            values = [prefix + suffix for prefix in values for suffix in part_values]
        return set(values)
    return set()


def _eval_path_sequence(
    node: ast.AST,
    source: Path,
    bindings: dict[str, set[str]],
) -> set[str]:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        result: set[str] = set()
        for element in node.elts:
            result.update(_eval_path_expr(element, source, bindings))
        return result
    return _eval_path_expr(node, source, bindings)


def _lookup_path_specs(values: set[str]) -> list[str]:
    specs: list[str] = []
    for value in values:
        pieces = value.split(os.pathsep)
        specs.extend(piece for piece in pieces if piece)
    return specs


def _check_lookup_path(
    errors: list[str],
    *,
    skill_root: Path,
    source: Path,
    lookup_path: str,
    context: str,
) -> None:
    expanded = os.path.expanduser(lookup_path)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        if candidate.parts and candidate.parts[0] == "skills":
            errors.append(
                f"{source.relative_to(REPO_ROOT)}: {context} adds relative root "
                f"skills lookup path: {lookup_path}"
            )
            return
        candidate = source.parent / candidate

    if _logical_abs(candidate) == _logical_abs(SKILLS_ROOT):
        errors.append(
            f"{source.relative_to(REPO_ROOT)}: {context} adds repository skills "
            f"lookup path: {lookup_path}"
        )
    elif _is_inside(candidate, SKILLS_ROOT) and not _is_inside(candidate, skill_root):
        errors.append(
            f"{source.relative_to(REPO_ROOT)}: {context} adds sibling skill lookup "
            f"path: {lookup_path}"
        )
    elif not _is_inside(candidate, skill_root):
        errors.append(
            f"{source.relative_to(REPO_ROOT)}: {context} adds lookup path outside "
            f"{skill_root.relative_to(REPO_ROOT)}: {lookup_path}"
        )


class SkillSelfContainmentTest(unittest.TestCase):
    def test_dependency_manifests_use_only_skill_local_path_dependencies(self) -> None:
        errors: list[str] = []
        manifest_names = {
            "package-lock.json",
            "package.json",
            "pyproject.toml",
            "requirements.txt",
        }

        for skill_root in _iter_skill_roots():
            for manifest in _walk_files(skill_root, manifest_names):
                if manifest.name == "requirements.txt":
                    self._check_requirements(errors, skill_root, manifest)
                elif manifest.name == "package.json":
                    self._check_package_json(errors, skill_root, manifest)
                elif manifest.name == "package-lock.json":
                    self._check_package_lock(errors, skill_root, manifest)
                elif manifest.name == "pyproject.toml":
                    self._check_pyproject(errors, skill_root, manifest)

        if errors:
            self.fail("Skill manifests reference external local paths:\n" + "\n".join(errors))

    def test_source_imports_and_lookup_paths_do_not_target_repo_roots_or_escape_skill(self) -> None:
        errors: list[str] = []
        source_suffixes = PYTHON_SUFFIXES | JAVASCRIPT_SUFFIXES

        for skill_root in _iter_skill_roots():
            for source in _walk_files(skill_root):
                if source.suffix not in source_suffixes:
                    continue
                if source.suffix in PYTHON_SUFFIXES:
                    self._check_python_imports(errors, skill_root, source)
                    self._check_python_lookup_paths(errors, skill_root, source)
                else:
                    self._check_javascript_imports(errors, skill_root, source)

        if errors:
            self.fail("Skill source files reference repo-root or sibling paths:\n" + "\n".join(errors))

    def _check_requirements(self, errors: list[str], skill_root: Path, manifest: Path) -> None:
        for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
            for context, spec in _requirement_path_specs(line):
                local_path = _local_path_from_spec(spec)
                if local_path is not None:
                    _check_local_path(
                        errors,
                        skill_root=skill_root,
                        manifest=manifest,
                        local_path=local_path,
                        context=f"{context} on line {line_number}",
                    )

    def _check_package_json(self, errors: list[str], skill_root: Path, manifest: Path) -> None:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for field in PACKAGE_DEPENDENCY_FIELDS:
            dependencies = data.get(field, {})
            if not isinstance(dependencies, dict):
                continue
            for name, spec in sorted(dependencies.items()):
                if not isinstance(spec, str):
                    continue
                local_path = _local_path_from_spec(spec)
                if local_path is not None:
                    _check_local_path(
                        errors,
                        skill_root=skill_root,
                        manifest=manifest,
                        local_path=local_path,
                        context=f"{field}.{name}",
                    )

        workspaces = data.get("workspaces")
        workspace_specs: list[str] = []
        if isinstance(workspaces, list):
            workspace_specs.extend(spec for spec in workspaces if isinstance(spec, str))
        elif isinstance(workspaces, dict):
            packages = workspaces.get("packages", [])
            if isinstance(packages, list):
                workspace_specs.extend(spec for spec in packages if isinstance(spec, str))
        for spec in workspace_specs:
            local_path = _local_path_from_spec(spec, allow_bare_relative=True)
            if local_path is not None:
                _check_local_path(
                    errors,
                    skill_root=skill_root,
                    manifest=manifest,
                    local_path=local_path,
                    context="workspaces",
                )

    def _check_package_lock(self, errors: list[str], skill_root: Path, manifest: Path) -> None:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        packages = data.get("packages", {})
        if isinstance(packages, dict):
            for package_path, package_data in sorted(packages.items()):
                if package_path and not package_path.startswith("node_modules/"):
                    _check_local_path(
                        errors,
                        skill_root=skill_root,
                        manifest=manifest,
                        local_path=package_path,
                        context=f"lock package {package_path}",
                    )
                if not isinstance(package_data, dict):
                    continue
                for field in PACKAGE_DEPENDENCY_FIELDS:
                    dependencies = package_data.get(field, {})
                    if not isinstance(dependencies, dict):
                        continue
                    for name, spec in sorted(dependencies.items()):
                        if not isinstance(spec, str):
                            continue
                        local_path = _local_path_from_spec(spec)
                        if local_path is not None:
                            _check_local_path(
                                errors,
                                skill_root=skill_root,
                                manifest=manifest,
                                local_path=local_path,
                                context=f"lock {field}.{name}",
                            )
                resolved = package_data.get("resolved")
                if isinstance(resolved, str):
                    local_path = _local_path_from_spec(resolved, allow_bare_relative=True)
                    if local_path is not None:
                        _check_local_path(
                            errors,
                            skill_root=skill_root,
                            manifest=manifest,
                            local_path=local_path,
                            context=f"lock resolved {package_path or '<root>'}",
                        )

    def _check_pyproject(self, errors: list[str], skill_root: Path, manifest: Path) -> None:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        project = data.get("project", {})
        if isinstance(project, dict):
            self._check_python_dependency_list(
                errors,
                skill_root,
                manifest,
                project.get("dependencies", []),
                "project.dependencies",
            )
            optional = project.get("optional-dependencies", {})
            if isinstance(optional, dict):
                for group, dependencies in sorted(optional.items()):
                    self._check_python_dependency_list(
                        errors,
                        skill_root,
                        manifest,
                        dependencies,
                        f"project.optional-dependencies.{group}",
                    )

        tool = data.get("tool", {})
        uv_sources = tool.get("uv", {}).get("sources", {}) if isinstance(tool, dict) else {}
        if isinstance(uv_sources, dict):
            for name, source in sorted(uv_sources.items()):
                if isinstance(source, dict) and isinstance(source.get("path"), str):
                    _check_local_path(
                        errors,
                        skill_root=skill_root,
                        manifest=manifest,
                        local_path=source["path"],
                        context=f"tool.uv.sources.{name}.path",
                    )

    def _check_python_dependency_list(
        self,
        errors: list[str],
        skill_root: Path,
        manifest: Path,
        dependencies: object,
        context: str,
    ) -> None:
        if not isinstance(dependencies, list):
            return
        for dependency in dependencies:
            if not isinstance(dependency, str):
                continue
            local_path = _local_path_from_spec(dependency)
            if local_path is not None:
                _check_local_path(
                    errors,
                    skill_root=skill_root,
                    manifest=manifest,
                    local_path=local_path,
                    context=context,
                )

    def _check_python_imports(self, errors: list[str], skill_root: Path, source: Path) -> None:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (SyntaxError, UnicodeDecodeError):
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = str(alias.name).split(".", 1)[0]
                    if root_name in FORBIDDEN_REPO_IMPORT_ROOTS:
                        errors.append(
                            f"{source.relative_to(REPO_ROOT)}:{node.lineno}: imports repo root "
                            f"module {root_name!r}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = source.parent
                    for _ in range(max(0, int(node.level) - 1)):
                        base = base.parent
                    if not _is_inside(base, skill_root):
                        errors.append(
                            f"{source.relative_to(REPO_ROOT)}:{node.lineno}: relative import escapes "
                            f"{skill_root.relative_to(REPO_ROOT)}"
                        )
                elif node.module:
                    root_name = str(node.module).split(".", 1)[0]
                    if root_name in FORBIDDEN_REPO_IMPORT_ROOTS:
                        errors.append(
                            f"{source.relative_to(REPO_ROOT)}:{node.lineno}: imports repo root "
                            f"module {root_name!r}"
                        )

    def _check_python_lookup_paths(self, errors: list[str], skill_root: Path, source: Path) -> None:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (SyntaxError, UnicodeDecodeError):
            return

        bindings = _collect_python_path_bindings(tree, source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _qualified_name(node.func)
                path_values: set[str] = set()
                context = name or "lookup path mutation"
                if name == "sys.path.insert" and len(node.args) >= 2:
                    path_values = _eval_path_expr(node.args[1], source, bindings)
                elif name in {"sys.path.append", "site.addsitedir"} and node.args:
                    path_values = _eval_path_expr(node.args[0], source, bindings)
                elif name == "sys.path.extend" and node.args:
                    path_values = _eval_path_sequence(node.args[0], source, bindings)

                for lookup_path in _lookup_path_specs(path_values):
                    _check_lookup_path(
                        errors,
                        skill_root=skill_root,
                        source=source,
                        lookup_path=lookup_path,
                        context=f"{context} on line {node.lineno}",
                    )
            elif isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                if value is None:
                    continue
                for target in targets:
                    env_key = _is_os_environ_target(target)
                    if env_key is None:
                        continue
                    for lookup_path in _lookup_path_specs(_eval_path_expr(value, source, bindings)):
                        _check_lookup_path(
                            errors,
                            skill_root=skill_root,
                            source=source,
                            lookup_path=lookup_path,
                            context=f"os.environ[{env_key!r}] on line {node.lineno}",
                        )

    def _check_javascript_imports(self, errors: list[str], skill_root: Path, source: Path) -> None:
        try:
            content = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return

        for match in JS_IMPORT_RE.finditer(content):
            spec = match.group("from") or match.group("call") or ""
            if not spec:
                continue
            root_name = spec.split("/", 1)[0]
            if root_name in FORBIDDEN_REPO_IMPORT_ROOTS:
                errors.append(
                    f"{source.relative_to(REPO_ROOT)}: imports repo root module {root_name!r}"
                )
                continue
            local_path = _local_path_from_spec(spec)
            if local_path is not None:
                candidate = Path(local_path)
                if not candidate.is_absolute():
                    candidate = source.parent / candidate
                if not _is_inside(candidate, skill_root):
                    errors.append(
                        f"{source.relative_to(REPO_ROOT)}: import {spec!r} escapes "
                        f"{skill_root.relative_to(REPO_ROOT)}"
                    )


if __name__ == "__main__":
    unittest.main()
