"""A store's delivery channel, stamped into every pin of its copy of the plugin.

Every command a skill runs pins the skill's release, `cad +<VERSION> <verb>` (the release stamps the version:
sync-version.mjs), and the skills' prose names the pin as `+<VERSION>`. A copy a store delivers runs that
release on the store's own channel, `cad +<VERSION>@<channel> <verb>`, so the device keeps a pointer for that
store's copies apart from the default channel's (the server's `pointers`): a store's update moves its own
channel, and the install command's update moves only the default. Our own text, the server's plugin folder
and the `latest` branch, carries no channel: the default.

Two builders stamp: plugin_branch.py, the `claude-plugin` branch claude.ai's directory reads (`@claude`), and
plugin_zip.py, the ZIP OpenAI's Codex directory takes (`@codex`). One routine, strict: a pin left unstamped,
a pin of another version, or a file of the copy that is neither an image nor UTF-8 text fails the build.
The channel's name is checked by the library's own rule (`cad.engine.places.CHANNEL`), read from this
checkout's source, which needs nothing of the library's installed.

What `--add X` names in the skills' setup block (`install.sh ... --add X`) is a version, not a pin: it
installs version X alone and moves no channel, and the first pinned command afterwards moves the store's
channel to it. It is left as it is.
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
# A command that runs `cad` with a pin: `cad +<word>`, the Windows `cad.exe` too.
_COMMAND_PIN = re.compile(r"(?<![\w.$/+-])cad(?:\.exe)? \+(?P<pin>[^\s`'\")\]]+)")


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


def stamp(files: dict[str, bytes], version: str, channel: str) -> tuple[dict[str, bytes], list[str]]:
    """Every file of a copy (path -> bytes) with its pins stamped `@channel`, and what fails the build: a
    channel the library would not take, a file that is neither an image nor UTF-8 text, a pin left without the
    channel or naming another version. Images pass as they are."""
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
        stamped = stamp_text(text, version, channel)
        errors += [f"{path}: {pin} is not stamped @{channel} for {version}" for pin in unstamped(stamped, version, channel)]
        out[path] = stamped.encode("utf-8")
    return out, errors
