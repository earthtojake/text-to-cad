"""The ``cad`` command's reference is read off its parsers, and the documentation site's copy is it.

``cad_server._internal.cli_reference`` walks every command the dispatcher answers and writes each one's usage,
description, arguments and options; the site renders its copy, so a command or an option that changes
fails here until the copy is regenerated, rather than leaving the page wrong.
"""

from __future__ import annotations

import unittest

from cad_server import cli
from cad_server._internal.cli_parser import parser as command_parser
from cad_server._internal import cli_reference as reference
from tests.python.support.paths import repo_path

COPY = repo_path("apps", "docs", "src", "lib", "docs", "cli-reference.generated.json")


class TheCopyIsTheCommand(unittest.TestCase):
    def test_the_docs_site_reads_the_commands_parsers(self) -> None:
        self.assertEqual(reference.as_docs_json(), COPY.read_text(encoding="utf-8"),
                         "regenerate: python -m cad_server._internal.cli_reference --docs "
                         "> apps/docs/src/lib/docs/cli-reference.generated.json")

    def test_every_command_the_dispatcher_answers_is_in_it(self) -> None:
        from cad_server.cli.document_types import OPERATIONS
        from cad_server.cli.integrations import OPERATIONS as INTEGRATION_OPERATIONS

        docs = reference.as_docs()
        listed = {command["command"] for group in (*docs["documentTypes"], *docs["integrations"])
                  for command in group["operations"]} | {command["command"] for command in docs["commands"]}
        answered = {f"cad {name}" for name in cli._COMMANDS} | {
            f"cad {owner} {operation}" for owner, operation in (*OPERATIONS, *INTEGRATION_OPERATIONS)}
        self.assertEqual(listed, answered)


class OneCommandsEntry(unittest.TestCase):
    def test_a_parser_becomes_its_entry(self) -> None:
        import argparse

        parser = command_parser("cad sample", description="Do the sample  thing.")
        parser.add_argument("source", metavar="SRC", help="the file")
        parser.add_argument("more", nargs="*", help="others")
        parser.add_argument("--mode", choices=["a", "b"], default="a", help="how (default: %(default)s)")
        parser.add_argument("--tag", action="append", metavar="TAG", help="a tag")
        parser.add_argument("--secret", help=argparse.SUPPRESS)
        either = parser.add_mutually_exclusive_group()
        either.add_argument("--json", action="store_true", help="JSON")
        either.add_argument("--quiet", action="store_true", help="nothing")
        self.assertEqual(reference.command_reference(parser, "cad sample", "a sample"), {
            "command": "cad sample", "summary": "a sample",
            "usage": "cad sample [--mode {a,b}] [--tag TAG] [--json | --quiet] SRC [more ...]",
            "description": "Do the sample thing.", "epilog": None,
            "arguments": [
                {"name": "SRC", "help": "the file", "choices": None, "optional": False, "repeatable": False},
                {"name": "more", "help": "others", "choices": None, "optional": True, "repeatable": True},
            ],
            "options": [
                {"flags": ["--mode"], "metavar": "{a,b}", "help": "how (default: a)", "choices": ["a", "b"],
                 "default": "a", "required": False, "repeatable": False},
                {"flags": ["--tag"], "metavar": "TAG", "help": "a tag", "choices": None, "default": None,
                 "required": False, "repeatable": True},
                {"flags": ["--json"], "metavar": None, "help": "JSON", "choices": None, "default": None,
                 "required": False, "repeatable": False},
                {"flags": ["--quiet"], "metavar": None, "help": "nothing", "choices": None, "default": None,
                 "required": False, "repeatable": False},
            ],
        })

    def test_shared_words_are_written_once(self) -> None:
        shared = reference._shared({"commands": [
            {"command": "cad a", "summary": "s", "description": "s", "options": [{"flags": ["--x"], "help": "h"}]},
            {"command": "cad b", "summary": "t", "description": "d", "options": [{"flags": ["--x"], "help": "h"}],
             "arguments": []},
        ]})
        self.assertEqual(shared, {"commands": [
            {"command": "cad a", "summary": "s", "options": [{"flags": ["--x"], "help": 0}]},
            {"command": "cad b", "summary": "t", "description": 1, "options": [{"flags": ["--x"], "help": 0}]},
        ], "texts": ["h", "d"]})


if __name__ == "__main__":
    unittest.main()
