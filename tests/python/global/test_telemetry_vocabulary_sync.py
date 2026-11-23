"""The controls a CAD view counts are one vocabulary in three languages.

The page names what a person used (`@cad/ui`'s `usage/controls.js`), cadgen notes only names it
knows (`cad_server/analytics.py`: `CONTROLS`), and the receiver refuses any other (`apps/api/src/events.mjs`:
`CONTROLS`). A name one of them lacks is a count lost without a word: the page's never noted, or a whole
batch refused. The kinds a file is counted as are its document type's (the library's registry,
`cad.registry`, kernel-free), as the schemas spell them, and the receiver keeps the kinds of the types since
removed, which released clients still send; the causes a crash of no kernel process names are
cadgen's and the receiver's alike. Read from source, so this needs nothing installed.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "packages/ui/src/usage/controls.js"
CADGEN = ROOT / "packages/cad/src/cad_server/analytics.py"
RECEIVER = ROOT / "apps/api/src/events.mjs"
# The kinds of document types cad no longer has: released clients count them, so the receiver keeps reading them.
RETIRED_KINDS = {"sdf"}


def names(path: Path, start: str, end: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    body = text[text.index(start) + len(start):]
    body = body[:body.index(end)]
    body = re.sub(r"(?m)(?://|#).*$", "", body)  # comments name words that are no control
    return re.findall(r"""['"]([a-z0-9][a-z0-9_]*)['"]""", body)


class TheControlsAreOneVocabulary(unittest.TestCase):
    def test_the_page_cadgen_and_the_receiver_name_the_same_controls(self) -> None:
        page = names(PAGE, "export const CONTROLS = Object.freeze(", "]));")
        cadgen = names(CADGEN, "CONTROLS = frozenset({", "})")
        receiver = names(RECEIVER, "export const CONTROLS = new Set([", "]);")
        self.assertGreater(len(page), 100)
        self.assertEqual(len(page), len(set(page)), "each name once")
        self.assertEqual(page, receiver, "the receiver's list, in the page's order")
        self.assertEqual(sorted(page), sorted(cadgen))
        # A name says what was used, never a value: snake_case words of the page's choosing.
        for name in page:
            self.assertRegex(name, r"^[a-z]+(?:_[a-z]+)*$")


class TheKindsAreOneVocabulary(unittest.TestCase):
    def test_current_sender_kinds_match_its_receiver_schema(self) -> None:
        # File suffixes are local lookup keys; only their formats and the closed model word cross the wire:
        # each document type's wire spelling (the registry's), which the sender's FILE_KINDS is made of.
        import sys

        sys.path.insert(0, str(ROOT / "packages/cad/src"))
        from cad.registry import DOCUMENT_TYPES

        tree = ast.parse(CADGEN.read_text(encoding="utf-8"))
        assignments = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                       for target in node.targets if isinstance(target, ast.Name)}
        self.assertEqual("_file_kinds()", ast.unparse(assignments["FILE_KINDS"]))
        formats = {entry.wire for entry in DOCUMENT_TYPES.values()}
        extra = names(CADGEN, "KINDS = frozenset({", "})")
        receiver = set(names(RECEIVER, "const KINDS = new Set([", "]);")
                       + names(RECEIVER, "const KINDS_6 = new Set([", "]);")
                       + names(RECEIVER, "const KINDS_8 = new Set([", "]);"))
        self.assertEqual(formats | set(extra) | RETIRED_KINDS, receiver)
        self.assertFalse(RETIRED_KINDS & (formats | set(extra)), "a retired kind is no current sender's")
        self.assertIn("model", extra)
        self.assertIn("xbf", formats)
        schema = ast.literal_eval(assignments["SCHEMA"])
        self.assertRegex(RECEIVER.read_text(encoding="utf-8"), rf"\[{schema}, \{{[^\n]*kinds: KINDS_8")


class TheKernelCausesAreOneVocabulary(unittest.TestCase):
    def test_cadgen_and_the_receiver_name_the_same_causes(self) -> None:
        # Which failure left the engine no kernel process: a word the receiver does not read refuses the batch.
        cadgen = names(CADGEN, "KERNEL_CAUSES = frozenset({", "})")
        receiver = names(RECEIVER, "const KERNEL_CAUSES = new Set([", "]);")
        self.assertGreater(len(cadgen), 5)
        self.assertEqual(sorted(cadgen), sorted(receiver))


class TheBuildFailuresAreOneVocabulary(unittest.TestCase):
    def test_every_reason_cadgen_sends_is_one_its_schema_reads(self) -> None:
        # Why a build failed: a reason the receiver's current schema does not read refuses the batch. The receiver
        # reads more (``child_failed``, which earlier releases sent); the system's reasons are cadgen's own words.
        cadgen = set(names(CADGEN, "BUILD_FAILURES = frozenset({", "})"))
        system = set(names(CADGEN, "SYSTEM_FAILURES = frozenset({", "})"))
        receiver = set(names(RECEIVER, "const BUILD_FAILURES = new Set([", "]);")
                       + names(RECEIVER, "const BUILD_FAILURES_9 = new Set([", "]);")
                       + names(RECEIVER, "const BUILD_FAILURES_10 = new Set([", "]);"))
        self.assertGreater(len(cadgen), 10)
        self.assertLessEqual(cadgen, receiver)
        self.assertLess(system, cadgen)
        schemas = RECEIVER.read_text(encoding="utf-8").split("const SCHEMAS = new Map([", 1)[1]
        self.assertIn("buildFailures: BUILD_FAILURES_10", schemas.split("[10, {", 1)[1].split("}],", 1)[0])


class TheInstallWordsAreOneVocabulary(unittest.TestCase):
    def test_cadgen_and_the_receiver_name_the_same_words_and_bounds(self) -> None:
        # A run of the plugin's install and each app where it failed (schema 12's ``install``, ``install_failure``):
        # who began it, how it ended, what its terminal showed and why an app failed. A word the receiver does not
        # read refuses the batch; one cadgen lacks is a run never counted. What was done in an app that did not fail
        # (``INSTALL_STATUSES``) is cadgen's alone: it is never sent, so the receiver has no such words.
        for name in ("INSTALL_BY", "INSTALL_OUTCOMES", "INSTALL_LOGOS", "INSTALL_COLOURS", "INSTALL_FAILURES"):
            cadgen = names(CADGEN, f"{name} = frozenset({{", "})")
            receiver = names(RECEIVER, f"const {name} = new Set([", "]);")
            self.assertGreater(len(cadgen), 2, name)
            self.assertEqual(sorted(cadgen), sorted(receiver), name)
        sender, receiver = CADGEN.read_text(encoding="utf-8"), RECEIVER.read_text(encoding="utf-8")
        self.assertNotIn("INSTALL_STATUSES", receiver)
        for name in ("MAX_INSTALL_SECONDS", "MAX_INSTALL_APPS"):
            ours = re.search(rf"(?m)^{name} = ([0-9_]+)$", sender)
            theirs = re.search(rf"(?m)^const {name} = ([0-9_]+);$", receiver)
            self.assertIsNotNone(ours and theirs, name)
            self.assertEqual(int(ours.group(1)), int(theirs.group(1)), name)
        # An app's key is read by one shape at both ends.
        self.assertIn('_APP = re.compile(r"[a-z0-9][a-z0-9._-]{0,39}")', sender)
        self.assertIn("const APP = /^[a-z0-9][a-z0-9._-]{0,39}$/;", receiver)
        # And both name the two events by the same fields, the app's key under its wire name here.
        tree = ast.parse(sender)
        table = next(node.value for node in tree.body
                     if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "EVENTS")
        events = {key.value: ast.literal_eval(value) for key, value in zip(table.keys, table.values)
                  if key.value in ("install", "install_failure")}
        fields = {name: re.findall(r"'([a-z_]+)'", receiver.split(f"\n  {name}: [", 1)[1].split("]", 1)[0])
                  for name in ("install", "install_failure")}
        self.assertEqual([*events["install"][0], *events["install"][1]], fields["install"])
        self.assertEqual([*events["install_failure"][0], *events["install_failure"][1]],
                         ["app" if name == "plugin_app" else name for name in fields["install_failure"]])
        self.assertEqual(fields["install_failure"], ["plugin_app", "reason", "seconds", "count"], "no status")


if __name__ == "__main__":
    unittest.main()
