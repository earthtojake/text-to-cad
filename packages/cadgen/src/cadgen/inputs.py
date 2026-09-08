"""Declaring a data file a model reads as a freshness input.

:mod:`cadgen.step_scene` covers the files cadgen itself knows how to read: a
STEP goes through ``read_step`` or ``load_step_scene``, and those record what
they read without being asked. Everything else a model reads is the model's own
business -- a JSON routing atlas, a CSV of tap sizes, a solved-offsets table --
and cadgen has no reader for it, so there is nothing for it to record.

That leaves the exact hole ``read_step`` was built to close, one format over.
Freshness follows a model's Python import reach and its declared inputs; a file
read as data announces neither. A model that computes its geometry from
``atlas.json`` and reads it with ``json.load`` goes on reporting itself current
after the atlas changes, and the only way to get the truth back is ``--force``
-- the flag whose whole job is to say the gate is lying.

:func:`declare_input` is the declaration. The model still does its own reading;
this only puts the file in the closure, so the next run's gate byte-hashes it
like any other non-Python input.

Deliberately ONE function rather than a family of readers. ``read_json`` would
be the first of an open-ended set (``read_csv``, ``read_yaml``, ``read_toml``,
...), each one a format cadgen would then own the parsing of, and none of them
adding anything to the freshness story that the declaration does not already
carry. cadgen reads the formats it has geometry semantics for; for the rest it
takes the model's word for what it read.
"""

from pathlib import Path

__all__ = ["declare_input"]


def declare_input(path: Path | str) -> Path:
    """Declare ``path`` a freshness input of the model being built, and return it.

    Use it wherever a model reads a non-CAD data file, by wrapping the path
    rather than the read::

        atlas = json.loads(declare_input(HERE / "atlas.json").read_text(encoding="utf-8"))

    The returned value is the resolved absolute :class:`~pathlib.Path`, so the
    call sits inline in the expression that opens the file and there is no way
    to declare one path and read another.

    The file's content hash joins the model's closure: replace the file and the
    model is stale on its own, rewrite it with identical bytes (a checkout, an
    rsync) and it stays current, because the input is the CONTENT and not the
    mtime. What the model does with the file is never inspected -- a build
    depends on the bytes it read, whatever it read them as.

    Recording is scoped to a build. Called from a REPL, a test or a tool it
    still resolves and checks the path, but there is no run to record into.

    A missing file raises here rather than inside the model's own parser,
    because "the data file is not where the model thinks it is" is the whole
    message. Paths resolve against the PROCESS's working directory, so anchor a
    model's inputs on its own file (``Path(__file__).parent / "atlas.json"``).

    Never declare a file the model itself writes. Like ``read_step`` on a
    model's own output, that is not a loop but an input that changes on every
    run: the gate can never say "current", and the geometry depends on what the
    last run happened to leave on disk.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"declare_input: no file at {resolved}. Check the path — it resolves "
            "relative to the process's working directory, so anchor a model's own "
            "inputs on its file: Path(__file__).parent / 'atlas.json'."
        )
    from cadgen._internal.source_hash import note_discovered_input

    note_discovered_input(resolved)
    return resolved
