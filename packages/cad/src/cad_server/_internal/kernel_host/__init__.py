"""The WebAssembly kernel's host, as cad ships it: ``python.mjs``, the stand-in for CPython's command line that
Node runs; ``bootstrap.py``, what it runs first inside that Python (it is that Python's file, never imported
here); and ``lock.json``, the pinned files a kernel folder is made of, each with its URL and sha256.
``cad_server._internal.kernel_folder`` makes the folder."""
