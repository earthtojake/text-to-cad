"""The library's reference is read off its declarations, and the documentation site's copy is it.

``cad._internal.reference`` writes the public API -- the root's ``__all__``, each document type's names (its
registry entry's, and its ``__all__``) and each integration's ``__all__`` -- with each name's signature and
docstring; the site renders its copy, so a signature or a docstring that changes fails here until the copy
is regenerated. An integration's names are read from source, never imported, so the reference is the same
where its extra is not installed.
"""

from __future__ import annotations

import ast
import typing
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cad/src")

from cad._internal import reference  # noqa: E402

COPY = repo_path("apps", "docs", "src", "lib", "docs", "library-reference.generated.json")


class TheCopyIsTheLibrary(unittest.TestCase):
    def test_the_docs_site_reads_the_librarys_declarations(self) -> None:
        self.assertEqual(reference.as_docs_json(), COPY.read_text(encoding="utf-8"),
                         "regenerate: python -m cad._internal.reference --docs "
                         "> apps/docs/src/lib/docs/library-reference.generated.json")

    def test_every_declared_name_is_in_it(self) -> None:
        import cad
        from cad.registry import DOCUMENT_TYPES, INTEGRATIONS

        docs = reference.as_docs()
        self.assertEqual([entry["name"] for entry in docs["documentTypes"]], list(DOCUMENT_TYPES))
        self.assertEqual([entry["name"] for entry in docs["integrations"]], list(INTEGRATIONS))
        self.assertEqual({entry["name"] for entry in docs["names"]} | set(DOCUMENT_TYPES), set(cad.__all__))
        for entry in docs["documentTypes"]:
            with self.subTest(type=entry["name"]):
                registry = DOCUMENT_TYPES[entry["name"]]
                names = {member["name"] for member in entry["members"] if member["kind"] != "decorator"}
                self.assertLessEqual(set(registry.operation_names), names)
                self.assertEqual(any(member["kind"] == "decorator" for member in entry["members"]),
                                 registry.decorator)
        for entry in docs["integrations"]:
            with self.subTest(integration=entry["name"]):
                module = __import__(entry["module"], fromlist=["__all__"])
                self.assertEqual([member["name"] for member in entry.get("members", [])],
                                 list(getattr(module, "__all__", ())))


class Signatures(unittest.TestCase):
    def test_a_function_from_source(self) -> None:
        node = ast.parse("def f(a, /, b: int = 1, *rest: str, c: 'X | None' = None, **more) -> list[str]: ...")
        self.assertEqual(reference._ast_signature(node.body[0]),
                         "(a, /, b: int = 1, *rest: str, c: 'X | None' = None, **more) -> list[str]")

    def test_a_value_read_at_run_time_says_the_same_on_every_python(self) -> None:
        import inspect
        from pathlib import Path

        def f(*args, **kwargs): ...

        # Values, not this module's strings (``from __future__ import annotations``), as a signature made at run
        # time has them (``cad.<type>.dfm``'s), beside a string annotation quoted twice.
        keyword = inspect.Parameter.KEYWORD_ONLY
        f.__signature__ = inspect.Signature([  # type: ignore[attr-defined]
            inspect.Parameter("source", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Path),
            inspect.Parameter("process", keyword, default=None,
                              annotation=typing.Optional[typing.Literal["cnc", "sheet"]]),
            inspect.Parameter("tools", keyword, default=None, annotation="'dict[str, Path] | None'"),
        ], return_annotation=typing.Any)
        self.assertEqual(reference._runtime_signature(f),
                         "(source: Path, *, process: Literal['cnc', 'sheet'] | None = None, "
                         "tools: dict[str, Path] | None = None) -> Any")

    def test_a_dataclass_is_its_fields(self) -> None:
        node = ast.parse("@dataclass\nclass C:\n    a: int\n    b: str = 'x'\n    _c: list = field(default_factory=list)\n"
                         "    @property\n    def ok(self) -> bool: ...\n    def lines(self, n: int) -> list: ...\n")
        found = reference._class(node.body[0])
        self.assertEqual(found["signature"], "(a: int, b: str = 'x')")
        self.assertEqual([(member["name"], member["kind"]) for member in found["members"]],
                         [("ok", "property"), ("lines", "method")])
        self.assertEqual(found["members"][1]["signature"], "(n: int) -> list")

    def test_every_docstring_is_written_once(self) -> None:
        shared = reference._shared({"names": [{"name": "a", "doc": "same", "bases": None},
                                              {"name": "b", "doc": "same", "operation": False}]})
        self.assertEqual(shared, {"names": [{"name": "a", "doc": 0}, {"name": "b", "doc": 0}], "texts": ["same"]})


if __name__ == "__main__":
    unittest.main()
