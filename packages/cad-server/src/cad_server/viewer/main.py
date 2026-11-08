"""Ensure this installation's engine and open its viewer page: the home, or each file named.

The page is the engine's one page, whose explorer opens where it was last, else your home folder.
Each FILE (an on-disk CAD file, a relative one read from this folder, or a document id the engine
holds) is registered and printed as its page, ``/<id>``."""
# A FILE that is not there, or that the viewer does not open -- a model's script among them -- is the
# command line's (the ``cad`` command's failure contract, ``cad_server._internal.cli_errors``): refused
# here, before the engine is asked, as the engine refuses it (``unopened``); a document id the engine does
# not hold is the engine's to say, with its reason (``not_found``).
from __future__ import annotations

import json
import os
import sys
import webbrowser

from cad_server import assets

DEFAULT_PROG = 'cad viewer'


def resolve_dist_dir(explicit: str) -> str:
    for candidate in (explicit, str(assets.viewer_dist_dir())):
        if candidate and os.path.isfile(os.path.join(candidate, 'index.html')):
            return os.path.abspath(candidate)
    return ''


class Unopened(ValueError):
    """A FILE a launch names that the viewer does not open (``unopened``), with the ``cad`` command's failure
    reason for it, which the engine's launch answers beside its words."""

    def __init__(self, words, reason):
        super().__init__(words)
        self.reason = reason


def unopened(name, start):
    """Why a launch's FILE ``name`` -- read from ``start`` when it is relative, as the engine reads it -- is no
    file the viewer opens, as ``(reason, words)`` (``cad_server._internal.cli_errors.REASONS``), or None for one
    it opens: a model's script (``part.py``, ``part.py::fn``), whose run makes its documents and prints each
    one's page, ``wrong_type``; a path that is not there, ``not_found``; a file of no type the viewer opens,
    ``wrong_type``. A document id is not a FILE here: the engine alone knows what it holds."""
    import shlex

    from .content_types import extension_of
    from .scanner import VIEWER_EXTENSIONS

    script = name.partition('::')[0]
    if script.lower().endswith('.py'):
        return 'wrong_type', (f"{name} is a model's script, not a CAD file: `cad run {shlex.quote(script)}` builds "
                              "its models and prints each one's page")
    path = os.path.join(start, os.path.expanduser(name))
    if not os.path.exists(path):
        return 'not_found', f'no such file: {name}'
    if extension_of(path) not in VIEWER_EXTENSIONS or not os.path.isfile(path):
        return 'wrong_type', f'no CAD file at {os.path.abspath(path)}'
    return None


def _files_opened(parsed):
    """The check of a launch's FILEs before the engine is asked (``unopened``), each read from this folder."""
    from cad.engine.ids import is_id
    from cad_server._internal.cli_errors import Failure

    for name in parsed.files:
        refused = None if is_id(name) else unopened(name, os.getcwd())
        if refused is not None:
            raise Failure(refused[1], refused[0])


def parse_args(argv=None, *, prog=DEFAULT_PROG):
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description=__doc__, checks=[_files_opened])
    parser.add_argument('files', nargs='*', metavar='FILE',
                        help='a CAD file to open (or a document id the engine holds): its page is /<id>')
    parser.add_argument('--host', default=None, help='Pin the engine bind address; default loopback.')
    parser.add_argument('--port', type=int, default=None, help='Pin this installation’s engine HTTP port.')
    parser.add_argument('--json', action='store_true', help='Print launch information without opening a browser.')
    parser.add_argument('--no-open', action='store_true', help='Print the URL without opening a browser.')
    parser.add_argument('--dist', default='', help='Built viewer client directory.')
    parser.add_argument('--api-only', action='store_true', help='Announce the engine for a Vite frontend, without its client build.')
    options = vars(parser.parse_args(argv))
    if options['port'] is not None and not 0 <= options['port'] <= 65535:
        parser.error('--port must be between 0 and 65535')
    return options


def main(argv=None, *, prog=DEFAULT_PROG):
    from cad.engine import client
    from cad.engine.client import request
    options = parse_args(argv, prog=prog)
    # The engine started for this page says so, as every verb's does (``cad_server.engine.cli.answered``).
    client.on_started = lambda: print('engine started', file=sys.stderr, flush=True)
    options['start'] = os.getcwd()
    if not options['api_only']:
        options['dist'] = resolve_dist_dir(options['dist'])
        if not options['dist']:
            return _failed(options, prog, ValueError('CAD Viewer client is not built; build apps/web or install the '
                                                     'cad-server wheel'))
    from cad_server._internal.cli_errors import REASONS, Failure

    try:
        answer = request({'op': 'viewer', **options})
        if not answer or 'failed' in answer:
            # The engine's refusal, with its reason where it gave one (a document id it does not hold).
            reason = (answer or {}).get('reason')
            raise Failure(str((answer or {}).get('failed', 'engine did not answer')),
                          reason if reason in REASONS else 'failed')
        # The meshing pool starts with the first page, not with the engine (every build starts
        # that): started now, it warms while the browser opens. CAD_VIEWER_WARM=0 skips it.
        if os.environ.get('CAD_VIEWER_WARM', '').strip() != '0':
            request({'op': 'warm'})
    except (OSError, ValueError, Failure) as error:
        return _failed(options, prog, error)
    if options['json']:
        print(json.dumps(answer), flush=True)
    else:
        # The page of each file named, a line each; the home's when none is.
        for url in [document['url'] for document in answer.get('documents') or []] or [answer['url']]:
            print(url, flush=True)
    if not options['json'] and not options['no_open'] and not options['api_only']:
        from .browser_open import CannotOpen, open_page

        try:
            open_page(answer['url'], opener=webbrowser.open)  # a file of a redirect: no token in argv
        except CannotOpen as error:
            print(f'CAD Viewer: could not open a browser ({error}); open the URL above', file=sys.stderr)
    return 0


def _failed(options, prog, error):
    """A launch that failed, by the ``cad`` command's contract (``cad_server._internal.cli_errors``): its
    words on stderr, or under ``--json`` its one JSON document on stdout; the exit status of its class either
    way (2 for a document the engine does not hold, 1 for a launch that failed)."""
    from cad_server._internal.cli_errors import classify, write

    failure = classify(error)
    if options['json']:
        return write(failure, prog=prog, as_json=True)
    print(f'CAD Viewer: {failure}', file=sys.stderr)
    return failure.status
