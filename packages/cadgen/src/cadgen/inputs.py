"""Declaring a data file a native reader opens as a freshness input.

:mod:`cadgen.step_scene` covers the files cadgen itself knows how to read: a
STEP goes through ``read_step`` or ``read_scene``, and those record what
they read without being asked. A file the model's own Python code opens -- a
JSON routing atlas through ``json.load``, a CSV of tap sizes, an ``np.load``
table -- is recorded too: Python's ``open`` audit event reports it, and the
build puts it in the closure (``cadgen._internal.source_hash``).

What no audit event sees is a file opened in native code: ``build123d``'s
``import_step`` or ``import_brep``, a font a text shape loads. A model that
computes its geometry from one of those would go on reporting itself current
after the file changes, and the only way to get the truth back would be
``--force`` -- the flag whose whole job is to say the gate is lying.

:func:`declare_input` is the declaration. The model still does its own reading;
this only puts the file in the closure, so the next run's gate byte-hashes it
like any other non-Python input. Declaring a file Python also opens is harmless.

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
    records the bytes present at declaration. Declare immediately before the
    read and keep the file stable through that read; returning a Path cannot
    make the caller's separate read atomic. An edit later in the build makes
    its result stale instead of binding the new bytes to the old geometry.

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
    from cadgen._internal.self_input import refuse_own_output
    from cadgen._internal.source_hash import note_discovered_input
    from cadgen.store.closure import note_declared_file_hash

    refuse_own_output(resolved, reader="declare_input")
    note_declared_file_hash(resolved)
    note_discovered_input(resolved)
    return resolved
