"""The installation's HTTP application: document routes and the one viewer page.

One engine serves one page, at its origin. Every document is addressed by path, ``/<id>``
(``cad.engine.ids``): a model's id, or a file's once a launcher or the page registers it. The
home is ``/``: Recents; the explorer opens where it was last, else the person's home folder. A
launch's folder (``launch``'s ``start``) resolves only the relative files it names. There are no
page sessions and no per-launch folders.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import io
import os
import secrets
import threading
import time
from urllib.parse import urlencode

from cad.engine.ids import is_id

from .documents import EngineDocuments
from .scanner import to_posix_path
from .http_app import CadApp, RAW_FILE_HEADERS, host_is_allowed


# The page's credentials all come from the user's one token (``engines/token``, read at the start:
# ``cad_server.engine.daemon.bind``), which only the user's own clients present, as a Bearer header: the
# door hands it to them. Every URL a launch prints or opens carries a link instead,
# ``?token=<expires>.<mac>``, good for a day (``LINK_SECONDS``), and a browser that opens one is given
# the session cookie, ``<expires>.<mac>`` too, good for 30 days from its last use, which renews it
# (``SESSION_SECONDS``, ``EngineApp._admitted``). A mac is the token's HMAC of the credential's kind and expiry, so
# each is checked by recomputing it: no engine keeps a session, every engine of this user -- on any
# port, of any installation, after any restart -- admits what another issued, and ``cadgen server
# --rotate-token`` ends every link and session at once. The cookie is named for the token too
# (``EngineApp.cookie``): one name on every port of the host, while another user's engine, or one
# with a rotated token, reads a name of its own and never sees, refuses or replaces this one.
LINK_SECONDS = 24 * 60 * 60
SESSION_SECONDS = 30 * 24 * 60 * 60


def _mac(master, message):
    digest = hmac.new(master.encode('utf-8'), message.encode('utf-8', 'surrogateescape'), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def sign(master, kind, seconds, now=None):
    """A ``kind`` credential (``link``, ``session``) of token ``master``, good for ``seconds``."""
    expires = int(time.time() if now is None else now) + seconds
    return f'{expires}.{_mac(master, f"{kind} {expires}")}'


def standing(master, kind, value):
    """``'ok'`` for a ``kind`` credential ``master`` signed that is still good, ``'expired'`` for one
    past its time, None for anything else."""
    expires, _, mac = str(value).partition('.')
    if not mac or not hmac.compare_digest(mac.encode('utf-8', 'surrogateescape'),
                                          _mac(master, f'{kind} {expires}').encode('ascii')):
        return None
    return 'ok' if int(expires) > time.time() else 'expired'


# What a page load without a credential this engine admits is answered with (``EngineApp._refused``):
# a link past its day says so (``LINK_EXPIRED_PAGE``); any other -- none, or one the token never
# signed, from before ``cadgen server --rotate-token`` -- that the page needs a link
# (``TOKEN_NEEDED_PAGE``). Each names the one thing to do.
_PAGE_HEAD = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1"><title>CAD</title>'
    '<style>body{font:15px/1.5 system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem}</style>'
    '</head><body>'
)
LINK_EXPIRED_PAGE = (
    _PAGE_HEAD + '<h1>This CAD Viewer link has expired</h1>'
    '<p>A link opens the viewer for a day. Run <code>cadgen viewer</code> and open the link it '
    'prints.</p></body></html>\n'
).encode('utf-8')
TOKEN_NEEDED_PAGE = (
    _PAGE_HEAD + '<h1>This CAD Viewer page needs its link</h1>'
    '<p>This browser has not opened the viewer in the last 30 days, or its links were replaced '
    'since. Run <code>cadgen viewer</code> and open the link it prints.</p></body></html>\n'
).encode('utf-8')


# A CAD card whose host carries none of its calls back (``apps/mcp``'s direct transport) reads the
# engine from its own sandbox's origin, with the day link its launch carries as a Bearer credential.
# That one case is answered with the card's origin's CORS allowance (``EngineApp._card``): a link in
# the Authorization header -- which a browser never attaches by itself, so only a page already holding
# the link can send it -- and nothing that rides by itself or in a URL: not the cookie (no
# Access-Control-Allow-Credentials is ever sent, so a cross-origin read never carries it), not a link
# in the query, not the user's token (a native client's, which needs no CORS), and never ``/mcp``.
# The bind stays loopback, and the Host and token gates run first.
CARD_METHODS = ('GET', 'HEAD', 'POST')
CARD_HEADERS = ('authorization', 'content-type', 'range', 'if-range', 'x-cadgen-viewer')
_CARD_EXPOSED = 'content-length, content-range, etag'
_PREFLIGHT_SECONDS = 600


def _card_origin(request):
    """The origin a cross-origin card's request names, or None: a request with no ``Origin`` is not a
    page's from another origin, and ``/mcp`` is a client's alone (``cad_server.mcp.http`` refuses it)."""
    origin = request.header('origin')
    return origin if origin and request.path != '/mcp' else None


def _navigation(request):
    """A browser's page load (a document, or HTML asked for) of a page, never a route of the engine."""
    return (request.header('sec-fetch-dest') == 'document' or 'text/html' in request.header('accept')) \
        and request.method == 'GET' and not request.path.startswith('/__cad/') and request.path != '/mcp'


def bounce_page(location):
    """A page of this origin that navigates to ``location`` (a path of it), with no script."""
    target = html.escape(location, quote=True)
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            f'<meta http-equiv="refresh" content="0;url={target}"><title>CAD</title></head>'
            f'<body><a href="{target}">Open the CAD Viewer</a></body></html>\n').encode('utf-8')


class DocumentResponse:
    """Adapt the engine's socket-shaped writer to the application's response, in process. ``page``:
    the request is the browser page's (the engine's own app), not an MCP view's tunnel."""
    def __init__(self, request, page=False):
        self.page = page
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


def document_route(server, request, response, page=False):
    if request.method == 'POST' and not request.header('x-cadgen-viewer'):
        response.send_json(403, {'error': 'missing x-cadgen-viewer header'})
        return
    handler = DocumentResponse(request, page)
    server.route(handler, request.method)
    # No CORS headers of the route's own: application reads are same-origin, authenticated MCP, or a
    # card's link-bearing read, which the engine's gate alone allows (``EngineApp._card``).
    response.send_bytes(handler.status, handler.wfile.getvalue(),
                        handler.response_headers.get('content-type', 'application/octet-stream'),
                        list({**dict(RAW_FILE_HEADERS), **{key: value for key, value in handler.response_headers.items()
                              if key not in ('content-type', 'content-length', 'connection', 'cache-control')
                              and not key.startswith('access-control-')}}.items()))


class ViewerApp(CadApp):
    """The viewer's routes over the engine's documents: the page's, and each MCP session's tunnel's.
    Files are known by id through the engine's server (``Server.remember``)."""

    # The browser page's app (``EngineApp.default_app``), whose version reads say a page shows a
    # document (``Server.in_page``); an MCP session's tunnel's is not.
    page = False

    def __init__(self, server, **kwargs):
        super().__init__(documents=EngineDocuments(server=server), **kwargs)
        self.server = server

    def remember(self, path):
        return self.server.remember(path)

    def file_of(self, ident):
        return self.server.file_of(ident)

    def delete_document(self, ident):
        # The engine's own deletion (``Server.delete``, the daemon's ``Models.delete``): what it holds
        # of the document, then its record and its cached document.
        if self.server.delete is None:
            return super().delete_document(ident)
        return self.server.delete(ident)

    def handle(self, request, response):
        self.server.touch()
        if not host_is_allowed(request.header('host'), self.host):
            return response.send_json(403, {'error': 'Host is not a local name'})
        if request.path.startswith('/__cad/api/') or request.path.startswith('/api/'):
            return document_route(self.server, request, response, self.page)
        return super().handle(request, response)


class EngineApp:
    def __init__(self, server, host, *, session_factory=None):
        self.server, self.host = server, host
        # The installation's page token, the same at every start (``daemon.bind``), else one of its own.
        self.token = getattr(server, 'token', None) or secrets.token_urlsafe(32)
        self.cookie = 'cadgen-' + _mac(self.token, 'cookie')[:12]
        self.lock = threading.RLock()
        self.active_requests = 0
        self._default = None
        self._mcp = None
        self.session_factory = session_factory
        from cad_server import __version__
        from cad_server.analytics import Recorder
        # Each sender's own recorder, so a batch says who sent it (``cad_server.analytics.PROCESSES``): the
        # CAD app's sessions (``mcp/http.py``) are the app's, the browser viewer's page the viewer's. The app's
        # client is the agent app a session's initialize names (``mcp/server.py``); the viewer's is the viewer
        # itself, of this version, shown in a browser -- the page's usage, told from the apps' by client.
        self.analytics = Recorder(process="app")
        self.viewer_analytics = Recorder(process="viewer")
        self.viewer_analytics.started(client={"name": "cadgen-viewer", "version": __version__}, presentation="browser")
        self.analytics.start()
        self.viewer_analytics.start()

    def active(self):
        with self.lock:
            apps = [self._default] if self._default else []
            active = self.active_requests > 0 or any(app._exports and app._exports.keeps_alive() for app in apps)
        return active or bool(self._mcp and self._mcp.active())

    def working(self):
        """What an update's drain waits for here (``serve.Server.clients_working``): an export the page
        asked for, and an agent's MCP call or operation (``Sessions.working``). A page's own requests
        are not: a page reconnects to the engine that follows."""
        with self.lock:
            apps = [self._default] if self._default else []
            exporting = any(app._exports and app._exports.keeps_alive() for app in apps)
        return exporting or bool(self._mcp and self._mcp.working())

    def close(self):
        with self.lock:
            apps = [self._default] if self._default else []
        for app in apps:
            if app._exports is not None:
                app._exports.close()
        if self._mcp is not None:
            self._mcp.close()
        self.analytics.close()
        self.viewer_analytics.close()

    def hold_ended(self, holder):
        """An MCP server's hold on the engine gone (``Daemon.hold``): the sessions it opened end."""
        with self.lock:
            mcp = self._mcp
        if mcp is not None:
            mcp.release(holder)

    def endpoint(self):
        return {'ok': True, 'url': self.server.url, 'port': self.server.port, 'token': self.token}

    def link(self):
        """A fresh link for a URL this engine prints or opens: good for ``LINK_SECONDS``."""
        return sign(self.token, 'link', LINK_SECONDS)

    def launch(self, options):
        """A launch of the one page (``cadgen viewer``, a text-only host's link, the dev client's
        ``--api-only``): each file it names (``files``: on-disk CAD files, a relative one read from its
        folder, ``start``, or ids the engine holds) is registered and given its page, ``/<id>``. ``url`` is the first file's page, else the home's, each with a fresh link,
        which ``token`` is too -- the user's token itself only for the dev client's ``--api-only``,
        whose proxy outlives a link."""
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
        link = self.link()
        for document in documents:
            document['url'] = f'{self.server.url}/{document["id"]}?token={link}'
        return {'ok': True, 'url': documents[0]['url'] if documents else f'{self.server.url}/?token={link}',
                'apiUrl': self.server.url, 'token': self.token if options.get('api_only') else link,
                'port': self.server.port, 'pid': os.getpid(),
                'start': app.start, 'documents': documents, 'action': 'reused' if reused else 'started'}

    def document(self, name, start):
        """A file or an id a launch names, as ``{id, file}``: a file registered by its canonical path
        (its id derived from it), an id taken as the engine holds it. ``ValueError`` for another."""
        from cad.engine.ids import is_id

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
                self._default.analytics = self.viewer_analytics  # the browser viewer's page
                self._default.page = True
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
        # Read only this engine's cookie out of the header by hand. A stdlib SimpleCookie parse
        # is all-or-nothing: a sibling cookie another page on this host set (cookies are scoped by
        # host, not port) with a name or value it rejects would drop the whole jar, and the engine's
        # own valid cookie with it, turning a good request into a 403.
        saved = ''
        for pair in (request.header('cookie') or '').split(';'):
            name, _, value = pair.strip().partition('=')
            if name == self.cookie:
                saved = value.strip().strip('"')

        def named(value):  # the user's token, or a link it signed
            if value and secrets.compare_digest(str(value).encode('utf-8', 'surrogateescape'), self.token.encode()):
                return 'ok'
            return standing(self.token, 'link', value) if value else None

        # Any one credential suffices: a cookie the token never signed is not one, and never outranks
        # the link of the URL a launch just printed.
        bearer = request.header('authorization').removeprefix('Bearer ')
        offered = {named(bearer), named(request.query.get('token', ''))}
        session = saved if saved and standing(self.token, 'session', saved) == 'ok' else ''
        if 'ok' not in offered and not session:
            return self._refused(request, response, 'expired' in offered)
        if 'ok' not in offered and request.header('sec-fetch-site') not in ('', 'same-origin', 'none'):
            # The cookie is sent to every port of this host, so a request it alone admits must come
            # from this engine's own pages (or be typed or opened by the person): the browser says
            # so in Sec-Fetch-Site, which a page cannot set. One without the header is a client's
            # that is not a browser, and is admitted as before. An old link followed from such a page
            # is asked again from this origin (``_refused``).
            if 'expired' in offered:
                return self._refused(request, response, True)
            return response.send_json(403, {'error': 'cross-origin request refused'})
        origin = _card_origin(request)
        if origin and bearer and standing(self.token, 'link', bearer) == 'ok':
            response.also = (*response.also, *self._card(origin))
        with self.lock:
            self.active_requests += 1
        self.server.touch()
        try:
            return self._admitted(request, response, session)
        finally:
            with self.lock:
                self.active_requests -= 1
            self.server.touch()

    @staticmethod
    def _card(origin):
        """The CORS allowance of a card's link-bearing request from ``origin``: that origin, echoed
        (an opaque sandbox's is ``null``), the headers its reader needs, and no credentials."""
        return (('access-control-allow-origin', origin), ('vary', 'Origin'),
                ('access-control-expose-headers', _CARD_EXPOSED))

    def preflight(self, request, response):
        """An ``OPTIONS`` request (``handler``): the preflight of a card's link-bearing request, which
        carries no credential itself (the browser sends none with it), answered for exactly that
        request -- one of ``CARD_METHODS``, asking for headers among ``CARD_HEADERS`` and for
        ``authorization`` among them -- from a local Host. It grants nothing: the request it clears is
        still refused without a good link. Anything else is the 405 every other method gets."""
        origin = _card_origin(request)
        asked = {name.strip().lower() for name in request.header('access-control-request-headers').split(',') if name.strip()}
        if not (host_is_allowed(request.header('host'), self.host) and origin
                and request.header('access-control-request-method').upper() in CARD_METHODS
                and 'authorization' in asked and asked <= set(CARD_HEADERS)):
            return response.send_empty(405, [('allow', 'GET, HEAD, POST')])
        headers = [('access-control-allow-origin', origin), ('vary', 'Origin'),
                   ('access-control-allow-methods', ', '.join(CARD_METHODS)),
                   ('access-control-allow-headers', ', '.join(CARD_HEADERS)),
                   ('access-control-max-age', _PREFLIGHT_SECONDS)]
        if request.header('access-control-request-private-network').lower() == 'true':
            # A page of a public origin reaching loopback (Private Network Access): this one may.
            headers.append(('access-control-allow-private-network', 'true'))
        return response.send_empty(204, headers)

    def _session_cookie(self):
        return ('set-cookie', f'{self.cookie}={sign(self.token, "session", SESSION_SECONDS)}; Path=/; '
                              f'Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Strict')

    def _admitted(self, request, response, session):
        """A request past the Host and token gates: by a credential it names, else by its ``session``
        cookie's value."""
        if 'token' in request.query and request.method == 'GET':
            # A link (or the token) is exchanged for a session and dropped from the address; one past
            # its day that the session admitted is just dropped.
            query = {k: v for k, v in request.query if k != 'token'}
            location = request.path + ('?' + urlencode(query) if query else '')
            cookie = self._session_cookie()
            if request.header('sec-fetch-site') in ('', 'none', 'same-origin'):
                return response.send_bytes(302, b'', '', [('location', location), cookie,
                                                          ('referrer-policy', 'no-referrer')])
            # Arrived from another origin (the browser opened on a redirect file, ``browser_open``): a
            # redirect would carry that origin on, and the browser would hold back the SameSite=Strict
            # cookie it was just given. The page's own navigation is this origin's, so it is sent.
            return response.send_bytes(200, bounce_page(location), 'text/html; charset=utf-8', [cookie,
                ('referrer-policy', 'no-referrer'), ('cache-control', 'no-store'),
                ('content-security-policy', "default-src 'none'; frame-ancestors 'self'")])
        if session and (_navigation(request) or int(session.partition('.')[0]) < time.time() + SESSION_SECONDS - 86400):
            # Each page load renews it, and any request once it is a day old, so a tab left open
            # keeps it too: 30 days from the last use.
            response.also = (*response.also, self._session_cookie())
        if request.path == '/mcp' and self.session_factory is not None:
            return self.mcp().handle(request, response)
        if request.method == 'GET' and is_id(request.path[1:]) and self.server.holds(request.path[1:]):
            self.server.warm()  # a build's view link opened: its meshing pool starts as the page loads
        return self.default_app().handle(request, response)

    def _refused(self, request, response, expired=False):
        """A request without a credential this engine admits: refused, 403, whatever it asks for -- a
        route, a page or an asset. A page load is told why in a static page of a few lines (no script,
        no asset, nothing of the person's), never raw JSON: a link past its day that it ``expired``
        (``LINK_EXPIRED_PAGE``), else that it needs a link (``TOKEN_NEEDED_PAGE``). An expired link
        followed from another site is first asked again from this origin, so the browser sends the
        session it holds (SameSite=Strict withholds it from the other site's navigation), which
        admits it; a request with no link is never. Every other refusal is the JSON error."""
        if _navigation(request):
            if expired and 'token' in request.query and request.header('sec-fetch-site') in ('cross-site', 'same-site'):
                return response.send_bytes(200, bounce_page(request.path + '?' + urlencode(list(request.query))),
                                           'text/html; charset=utf-8', [('referrer-policy', 'no-referrer'),
                                           ('content-security-policy', "default-src 'none'; frame-ancestors 'self'")])
            return response.send_bytes(403, LINK_EXPIRED_PAGE if expired else TOKEN_NEEDED_PAGE,
                                       'text/html; charset=utf-8',
                                       [('referrer-policy', 'no-referrer'),
                                        ('content-security-policy',
                                         "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'")])
        return response.send_json(403, {'error': 'engine token required'})

    def mcp(self):
        with self.lock:
            if self._mcp is None:
                self._mcp = self.session_factory(self)
            return self._mcp
