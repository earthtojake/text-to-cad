"""The installation's HTTP application: document routes and the one viewer page.

One engine serves one page, at its origin. Every document is addressed by path, ``/<id>``
(``cadgen.engine.ids``): a model's id, or a file's once a launcher or the page registers it. The
home is ``/``: Recents, and the folder of the most recent launch (``launch``), which each launch
replaces. There are no page sessions and no per-launch folders: an old ``/s/...`` link, or a ``/``
naming a document by query (``?doc=``, ``?file=``), is answered with the home.
"""
from __future__ import annotations

import html
import io
import os
import secrets
import threading
from urllib.parse import urlencode

from cadgen.engine.ids import is_id

from .documents import EngineDocuments
from .scanner import to_posix_path
from .http_app import CadApp, RAW_FILE_HEADERS, host_is_allowed


# What a navigation without this engine's token is answered with (``EngineApp._refused``).
LINK_GONE_PAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1"><title>CAD</title>'
    '<style>body{font:15px/1.5 system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem}</style>'
    '</head><body><h1>This CAD Viewer link no longer works</h1>'
    '<p>Its engine was restarted or stopped. Open the viewer again, from your agent or with '
    '<code>cadgen viewer</code>, for a fresh link.</p></body></html>\n'
).encode('utf-8')

def bounce_page(location):
    """A page of this origin that navigates to ``location`` (a path of it), with no script."""
    target = html.escape(location, quote=True)
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            f'<meta http-equiv="refresh" content="0;url={target}"><title>CAD</title></head>'
            f'<body><a href="{target}">Open the CAD Viewer</a></body></html>\n').encode('utf-8')


class DocumentResponse:
    """Adapt the engine's socket-shaped writer to the application's response, in process."""
    def __init__(self, request):
        self.command = request.method
        self.path = request.path.removeprefix('/__cad')
        if request.query:
            self.path += '?' + urlencode(list(request.query))
        self.headers = request.headers
        self.rfile = io.BytesIO(request.body() if request.method == 'POST' else b'')
        self.wfile = io.BytesIO()
        self.status = 200
        self.response_headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers[name.lower()] = str(value)

    def end_headers(self):
        pass


def document_route(server, request, response):
    if request.method == 'POST' and not request.header('x-cadgen-viewer'):
        response.send_json(403, {'error': 'missing x-cadgen-viewer header'})
        return
    handler = DocumentResponse(request)
    server.route(handler, request.method)
    # Deliberately no CORS headers: all application reads are same-origin or authenticated MCP.
    response.send_bytes(handler.status, handler.wfile.getvalue(),
                        handler.response_headers.get('content-type', 'application/octet-stream'),
                        list({**dict(RAW_FILE_HEADERS), **{key: value for key, value in handler.response_headers.items()
                              if key not in ('content-type', 'content-length', 'connection', 'cache-control')
                              and not key.startswith('access-control-')}}.items()))


class ViewerApp(CadApp):
    """The viewer's routes over the engine's documents: the page's, and each MCP session's tunnel's.
    Files are known by id through the engine's server (``Server.remember``)."""

    def __init__(self, server, **kwargs):
        super().__init__(documents=EngineDocuments(server=server), **kwargs)
        self.server = server

    def remember(self, path):
        return self.server.remember(path)

    def file_of(self, ident):
        return self.server.file_of(ident)

    def handle(self, request, response):
        self.server.touch()
        if not host_is_allowed(request.header('host'), self.host):
            return response.send_json(403, {'error': 'Host is not a local name'})
        if request.path.startswith('/__cad/api/') or request.path.startswith('/api/'):
            return document_route(self.server, request, response)
        return super().handle(request, response)


class EngineApp:
    def __init__(self, server, host, *, session_factory=None):
        self.server, self.host = server, host
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.active_requests = 0
        self._default = None
        self._mcp = None
        self.session_factory = session_factory
        from cadgen.analytics import Recorder
        self.analytics = Recorder()
        self.analytics.start()

    def active(self):
        with self.lock:
            apps = [self._default] if self._default else []
            active = self.active_requests > 0 or any(app._exports and app._exports.keeps_alive() for app in apps)
        return active or bool(self._mcp and self._mcp.active())

    def close(self):
        with self.lock:
            apps = [self._default] if self._default else []
        for app in apps:
            if app._exports is not None:
                app._exports.close()
        if self._mcp is not None:
            self._mcp.close()
        self.analytics.close()

    def endpoint(self):
        return {'ok': True, 'url': self.server.url, 'port': self.server.port, 'token': self.token}

    def launch(self, options):
        """A launch of the one page (``cadgen viewer``, a text-only host's link, the dev client's
        ``--api-only``): its folder (``start``) becomes the folder the home shows, and each file it
        names (``files``: on-disk CAD files, or ids the engine holds) is registered and given its
        page, ``/<id>``. ``url`` is the first file's page, else the home's."""
        from .main import resolve_dist_dir
        start = os.path.abspath(options.get('start') or os.path.expanduser('~'))
        dist = '' if options.get('api_only') else resolve_dist_dir(options.get('dist') or '')
        if not options.get('api_only') and not dist:
            return {'failed': 'CAD Viewer client is not built; build apps/web or install the cadgen wheel'}
        try:
            documents = [self.document(name, start) for name in options.get('files') or []]
        except ValueError as error:
            return {'failed': str(error)}
        with self.lock:
            reused = self._default is not None
            app = self.default_app(dist or None)
            app.start = to_posix_path(start)
        token = f'?token={self.token}'
        for document in documents:
            document['url'] = f'{self.server.url}/{document["id"]}{token}'
        return {'ok': True, 'url': documents[0]['url'] if documents else f'{self.server.url}/{token}',
                'apiUrl': self.server.url, 'token': self.token, 'port': self.server.port, 'pid': os.getpid(),
                'start': app.start, 'documents': documents, 'action': 'reused' if reused else 'started'}

    def document(self, name, start):
        """A file or an id a launch names, as ``{id, file}``: a file registered by its canonical path
        (its id derived from it), an id taken as the engine holds it. ``ValueError`` for another."""
        from cadgen.engine.ids import is_id

        from .scanner import VIEWER_EXTENSIONS, extension_of

        if is_id(name):
            if not self.server.holds(name):
                self.server.revive(name)  # a document the engine's cache holds, after a restart
            if not (self.server.holds(name) or self.server.file_of(name)):
                raise ValueError(f'no document {name} is held')
            return {'id': name, 'file': self.server.file_of(name)}
        path = os.path.join(start, os.path.expanduser(name))
        if extension_of(path) not in VIEWER_EXTENSIONS or not os.path.isfile(path):
            raise ValueError(f'no CAD file at {os.path.abspath(path)}')
        ident = self.server.remember(path)
        return {'id': ident, 'file': to_posix_path(self.server.file_of(ident))}

    def sessions(self):
        page = [] if self._default is None else [{'kind': 'viewer', 'start': self._default.start}]
        return page + ([] if self._mcp is None else self._mcp.listing())

    def default_app(self, dist=None):
        """The one page's app, made on its first request or launch; a launch's client build replaces
        the one it serves."""
        with self.lock:
            if self._default is None:
                from .main import resolve_dist_dir
                self._default = ViewerApp(self.server, host=self.host, port=self.server.port,
                                          dist_dir=dist or resolve_dist_dir(''))
                self._default.analytics = self.analytics
            elif dist:
                self._default.dist_dir = os.path.abspath(dist)
            return self._default

    def handle(self, request, response):
        return self._handle(request, response)

    def _handle(self, request, response):
        # Nothing before the gates counts as use: a request refused for its Host or its token
        # neither keeps the engine from retiring nor counts as an active client.
        if not host_is_allowed(request.header('host'), self.host):
            return response.send_json(403, {'error': 'Host is not a local name'})
        bearer = request.header('authorization').removeprefix('Bearer ')
        # Read only this engine's cookie out of the header by hand. A stdlib SimpleCookie parse
        # is all-or-nothing: a sibling cookie another page on this host set (cookies are scoped by
        # host, not port) with a name or value it rejects would drop the whole jar, and the engine's
        # own valid cookie with it, turning a good request into a 403.
        cookie_name = f'cadgen-engine-{self.server.port}'
        saved = ''
        for pair in (request.header('cookie') or '').split(';'):
            name, _, value = pair.strip().partition('=')
            if name == cookie_name:
                saved = value.strip().strip('"')
        # Any one credential suffices: a cookie left by an engine that held this port before
        # must not outrank the token of the URL a launch just printed.
        expected = self.token.encode()

        def matches(value):
            return bool(value) and secrets.compare_digest(str(value).encode('utf-8', 'surrogateescape'), expected)

        named = matches(bearer) or matches(request.query.get('token', ''))
        if not named and not matches(saved):
            return self._refused(request, response)
        if not named and request.header('sec-fetch-site') not in ('', 'same-origin', 'none'):
            # The cookie is sent to every port of this host, so a request it alone admits must come
            # from this engine's own pages (or be typed or opened by the person): the browser says
            # so in Sec-Fetch-Site, which a page cannot set. One without the header is a client's
            # that is not a browser, and is admitted as before.
            return response.send_json(403, {'error': 'cross-origin request refused'})
        with self.lock:
            self.active_requests += 1
        self.server.touch()
        try:
            return self._admitted(request, response, cookie_name)
        finally:
            with self.lock:
                self.active_requests -= 1
            self.server.touch()

    def _admitted(self, request, response, cookie_name):
        """A request past the Host and token gates."""
        if request.query.get('token') == self.token and request.method == 'GET':
            query = {k: v for k, v in request.query if k != 'token'}
            location = request.path + ('?' + urlencode(query) if query else '')
            cookie = ('set-cookie', f'{cookie_name}={self.token}; Path=/; HttpOnly; SameSite=Strict')
            if request.header('sec-fetch-site') in ('', 'none', 'same-origin'):
                return response.send_bytes(302, b'', '', [('location', location), cookie,
                                                          ('referrer-policy', 'no-referrer')])
            # Arrived from another origin (the browser opened on a redirect file, ``browser_open``): a
            # redirect would carry that origin on, and the browser would hold back the SameSite=Strict
            # cookie it was just given. The page's own navigation is this origin's, so it is sent.
            return response.send_bytes(200, bounce_page(location), 'text/html; charset=utf-8', [cookie,
                ('referrer-policy', 'no-referrer'), ('cache-control', 'no-store'),
                ('content-security-policy', "default-src 'none'; frame-ancestors 'self'")])
        if request.path == '/mcp' and self.session_factory is not None:
            return self.mcp().handle(request, response)
        if request.method == 'GET' and (request.path.startswith('/s/') or request.path == '/s'
                                         or request.path == '/' and ('doc' in request.query or 'file' in request.query)):
            # A page session's link, or a document named by query: forms that are gone. The home.
            return response.send_bytes(302, b'', '', [('location', '/'), ('referrer-policy', 'no-referrer')])
        if request.method == 'GET' and is_id(request.path[1:]) and self.server.holds(request.path[1:]):
            self.server.warm()  # a build's view link opened: its meshing pool starts as the page loads
        return self.default_app().handle(request, response)

    def _refused(self, request, response):
        """A request without this engine's token: refused, 403, whatever it asks for -- a route, a
        page or an asset. A tab left open from an engine that stopped, or reloaded under one started
        since, navigates with a token this engine never issued: it is told so in a static page of a
        few lines (``LINK_GONE_PAGE``: no script, no asset, nothing of the person's), never raw JSON.
        Every other refusal is the JSON error."""
        navigation = (request.header('sec-fetch-dest') == 'document' or 'text/html' in request.header('accept')) \
            and request.method == 'GET' and not request.path.startswith('/__cad/') and request.path != '/mcp'
        if navigation:
            return response.send_bytes(403, LINK_GONE_PAGE, 'text/html; charset=utf-8',
                                       [('referrer-policy', 'no-referrer'),
                                        ('content-security-policy',
                                         "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'")])
        return response.send_json(403, {'error': 'engine token required'})

    def mcp(self):
        with self.lock:
            if self._mcp is None:
                self._mcp = self.session_factory(self)
            return self._mcp
