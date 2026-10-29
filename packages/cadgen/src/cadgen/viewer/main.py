"""Attach to the selected engine and open its viewer page: the home, or each file named.

The page is the engine's one page, whose explorer opens where it was last, else your home folder.
Each FILE (an on-disk CAD file, a relative one read from this folder, or a document id the engine
holds) is registered and printed as its page, ``/<id>``."""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser

from cadgen import assets

DEFAULT_PROG = 'cadgen viewer'


def resolve_dist_dir(explicit: str) -> str:
    for candidate in (explicit, str(assets.viewer_dist_dir())):
        if candidate and os.path.isfile(os.path.join(candidate, 'index.html')):
            return os.path.abspath(candidate)
    return ''


def parse_args(argv=None, *, prog=DEFAULT_PROG):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument('files', nargs='*', metavar='FILE',
                        help='a CAD file to open (or a document id the engine holds): its page is /<id>')
    parser.add_argument('--host', default=None, choices=['127.0.0.1'], help='The engine loopback address.')
    parser.add_argument('--port', type=int, default=None, help='Select a running engine (else CADGEN_PORT, else 3245).')
    parser.add_argument('--json', action='store_true', help='Print launch information without opening a browser.')
    parser.add_argument('--no-open', action='store_true', help='Print the URL without opening a browser.')
    parser.add_argument('--dist', default='', help='Built viewer client directory.')
    parser.add_argument('--api-only', action='store_true', help='Announce the engine for a Vite frontend, without its client build.')
    options = vars(parser.parse_args(argv))
    if options['port'] is not None and not 1 <= options['port'] <= 65535:
        parser.error('--port must be between 1 and 65535')
    return options


def main(argv=None, *, prog=DEFAULT_PROG):
    from cadgen.engine.client import request
    options = parse_args(argv, prog=prog)
    if options['port'] is not None:
        os.environ['CADGEN_PORT'] = str(options['port'])
    options['start'] = os.getcwd()
    if not options['api_only']:
        options['dist'] = resolve_dist_dir(options['dist'])
        if not options['dist']:
            print('CAD Viewer client is not built; build apps/web or install the cadgen wheel', file=sys.stderr)
            return 1
    try:
        answer = request({'op': 'viewer', **options})
        if not answer or 'failed' in answer:
            raise ValueError((answer or {}).get('failed', 'engine did not answer'))
        # The meshing pool starts with the first page, not with the engine (every build starts
        # that): started now, it warms while the browser opens. CADGEN_VIEWER_WARM=0 skips it.
        if os.environ.get('CADGEN_VIEWER_WARM', '').strip() != '0':
            request({'op': 'warm'})
    except (OSError, ValueError) as error:
        print(f'CAD Viewer: {error}', file=sys.stderr)
        return 1
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
