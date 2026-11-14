"""A store's copy of the plugin: its store's name stamped into every pin, and no update paragraph.

Every command a skill runs pins the skill's release, `cad +<VERSION> <verb>` (the release stamps the version:
sync-version.mjs), and the skills' prose names the pin as `+<VERSION>`. A copy a store delivers names that
store in every pin, `cad +<VERSION>@<store> <verb>`: the label says the store updates this copy, so `cad`
prints no update notice for its commands. Our own text, `main` and the `latest` branch, names no store.

Our own text tells the agent to keep the install up to date, in one paragraph of each skill's setup block
between two HTML comments, `UPDATE_START` and `UPDATE_END` (a reader of the rendered skill sees neither). A
store updates its own copy, so a store's copy leaves that paragraph out, comments and all.

Three builders make a store's copy, each through `stamp`: plugin_branch.py, the `claude-plugin` branch
claude.ai's directory reads (`@claude`), and plugin_zip.py, the ZIP OpenAI's Codex directory takes and the
`codex-plugin` branch that holds the same files (`@codex`). One routine, strict: a pin left unstamped, a pin
of another version, an update paragraph not marked exactly once in a skill's setup block, a marker left over,
or a file of the copy that is neither an image nor UTF-8 text fails the build. The store's name is checked by
the library's own rule (`cad.engine.places.CHANNEL`), read from this checkout's source, which needs nothing of
the library's installed.

The install line in the setup block names the version as a requirement (`--from cad-server==X`), not a pin,
and is left as it is.
"""

from __future__ import annotations

import functools
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACES = REPO_ROOT / "packages/cad/src/cad/engine/places.py"
# Files a copy carries that are not text, and hold no pin: images (each checked as one by its builder).
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico")
# The update paragraph of our own text, between these two lines; a store's copy has neither.
UPDATE_START = "<!-- manual-copy-update: start -->"
UPDATE_END = "<!-- manual-copy-update: end -->"
_UPDATE = re.compile(re.escape(UPDATE_START) + r"\n.*?^" + re.escape(UPDATE_END) + r"\n\n?", re.S | re.M)
# A skill's setup block opens with this sentence: each such SKILL.md carries the update paragraph once.
SETUP_OPENS = "Every command in this skill starts `cad +"
_SKILL_DOC = re.compile(r"skills/[^/]+/SKILL\.md")
# A command that runs `cad` with a pin: `cad +<word>`, the Windows `cad.exe` too; or written as a list, a
# `+<digit>` word beside `cad` (`["cad", "+0.11.9", ...]`).
_COMMAND_PIN = re.compile(r"(?<![\w.$/+-])cad(?:\.exe)?(?: \+|[\"']?[ \t]*,[ \t]*[\"']\+(?=[0-9]))"
                          r"(?P<pin>[^\s`'\")\],]+)")


@functools.cache
def channel_rule() -> re.Pattern[str]:
    """The library's rule for a channel's name (``places.CHANNEL``), from this checkout's source: its module
    imports the standard library alone."""
    name = "_cad_places_for_release"
    spec = importlib.util.spec_from_file_location(name, PLACES)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass reads its module as it is made
    spec.loader.exec_module(module)
    return module.CHANNEL


def _version_pin(version: str, *, bare: bool = False) -> re.Pattern[str]:
    """`+<version>` standing as a pin: not inside a longer word or version (`+0.11.100`, `+0.11.10.1`); with
    `bare`, only one that names no channel yet."""
    after = "[0-9A-Za-z+_@-]" if bare else "[0-9A-Za-z+_-]"
    return re.compile(r"(?<![\w.+@-])\+" + re.escape(version) + rf"(?!{after}|\.[0-9A-Za-z])")


def stamp_text(text: str, version: str, channel: str) -> str:
    """`text` with every pin of `version` that names no channel given `@channel`."""
    return _version_pin(version, bare=True).sub(lambda match: match[0] + "@" + channel, text)


def unstamped(text: str, version: str, channel: str) -> list[str]:
    """Each pin in `text` that does not carry `@channel`: a pin of `version` left bare, or a command pinned to
    anything but `version@channel`."""
    found = []
    stamped = f"{version}@{channel}"
    for match in _version_pin(version).finditer(text):
        if not text.startswith("@" + channel, match.end()):
            found.append(match[0])
    for match in _COMMAND_PIN.finditer(text):
        if match["pin"].rstrip(".,;:") != stamped:
            found.append(match[0])
    return found


def without_update(path: str, text: str) -> tuple[str, list[str]]:
    """`text` without its update paragraph, and what fails the build: a skill's setup block whose paragraph is not
    marked exactly once, or a marker left without its pair."""
    out, found = _UPDATE.subn("", text)
    errors = []
    if _SKILL_DOC.fullmatch(path) and SETUP_OPENS in text and found != 1:
        errors.append(f"{path}: its setup block's update paragraph is marked {found} times, not once")
    if UPDATE_START in out or UPDATE_END in out:
        errors.append(f"{path}: an update paragraph marker without its pair ({UPDATE_START} ... {UPDATE_END})")
    return out, errors


def stamp(files: dict[str, bytes], version: str, channel: str) -> tuple[dict[str, bytes], list[str]]:
    """Every file of a store's copy (path -> bytes) without the update paragraph and with its pins stamped
    `@channel`, and what fails the build: a channel the library would not take, a file that is neither an image
    nor UTF-8 text, an update paragraph that cannot be taken out (`without_update`), a pin left without the channel
    or naming another version. Images pass as they are."""
    if not channel_rule().fullmatch(channel):
        return files, [f"{channel!r} is not a channel's name (cad.engine.places.CHANNEL)"]
    errors: list[str] = []
    out: dict[str, bytes] = {}
    for path, data in files.items():
        if path.lower().endswith(IMAGE_SUFFIXES):
            out[path] = data
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{path}: not UTF-8 text, so its pins cannot be stamped @{channel}")
            out[path] = data
            continue
        text, stripping = without_update(path, text)
        errors += stripping
        stamped = stamp_text(text, version, channel)
        errors += [f"{path}: {pin} is not stamped @{channel} for {version}" for pin in unstamped(stamped, version, channel)]
        out[path] = stamped.encode("utf-8")
    return out, errors
