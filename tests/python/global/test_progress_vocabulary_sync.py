"""The engine's progress vocabulary is said in every language the viewer speaks.

Every job the engine runs says where it is in one progress event, whose `kind` and `stage` are a
closed vocabulary (`packages/cad/src/cad/engine/progress.py`: `STAGES`); the page says each
stage in the view's language by the key `progress.<kind>.<stage>` (`packages/ui/src/i18n/locales`).
A stage no locale names would read on screen as its key, and a key no stage has is dead. Read as
text, so this needs nothing installed.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "packages/cad/src/cad/engine/progress.py"
LOCALES = ROOT / "packages/ui/src/i18n/locales"
KEY = re.compile(r'^\s*"(progress\.[^"]+)":\s*"([^"]*)"', re.M)


def stages() -> dict[str, dict[str, str]]:
    """`STAGES` as the engine declares it, read from the source without importing cadgen."""
    module = ast.parse(ENGINE.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "STAGES":
            return ast.literal_eval(node.value)
    raise AssertionError("progress.py declares STAGES")


class TheVocabularyIsOneInEveryLanguage(unittest.TestCase):
    def test_every_stage_of_every_kind_has_its_key_in_every_locale_and_no_key_is_dead(self) -> None:
        vocabulary = stages()
        self.assertEqual(list(vocabulary), ["build", "import", "export", "snapshot", "inspect-measure", "update"])
        wanted = {f"progress.{kind}.{stage}" for kind, found in vocabulary.items() for stage in found}
        locales = sorted(LOCALES.glob("*.js"))
        self.assertEqual([path.name for path in locales], ["en.js", "ja.js", "ko.js", "zh-CN.js", "zh-TW.js"])
        for path in locales:
            found = dict(KEY.findall(path.read_text(encoding="utf-8")))
            self.assertEqual(set(found), wanted, f"{path.name}'s progress keys are the engine's stages, no more and no less")
            self.assertTrue(all(found.values()), f"{path.name} says every stage")
        # A kind's and a stage's names are what the keys can carry: lower-case words, a hyphen between them;
        # a stage named for a technology keeps its name's digits (the update's `build123d`).
        for kind, found in vocabulary.items():
            self.assertRegex(kind, r"^[a-z]+(?:-[a-z]+)*$")
            for stage, words in found.items():
                self.assertRegex(stage, r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
                self.assertTrue(words and words[0].isupper(), f"{kind}.{stage}'s words read as a line: {words!r}")
        # English says each stage as the engine does, so a terminal and a page agree on the words.
        english = dict(KEY.findall((LOCALES / "en.js").read_text(encoding="utf-8")))
        self.assertEqual({f"progress.{kind}.{stage}": words for kind, found in vocabulary.items() for stage, words in found.items()},
                         english)


if __name__ == "__main__":
    unittest.main()
