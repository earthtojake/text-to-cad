"""Streamable HTTP MCP, with one tool/view session per negotiated session id.

JSON responses implement the 2025-11-25 transport without an optional SSE stream.
A session's removal releases only its state, never the installation's engine.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from cadgen.viewer.engine_app import ViewerApp
from .protocol import INVALID_REQUEST, INVALID_PARAMS, PARSE_ERROR, INTERNAL_ERROR, RequestContext, RpcError
from .server import Server, _PROTOCOL_VERSIONS
from .sidebar import SidebarViews
from .tunnel import ViewerTunnel
from .ui import AppPage
from .views import ViewRegistry

IDLE = 3600.0


@dataclass
class Session:
    server: Server
    protocol: str
    client: str
    touched: float = field(default_factory=time.monotonic)
    active: int = 0

    def close(self):
        self.server.sidebar_views.close()


class Sessions:
    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.sidebar = ViewRegistry()

    def close(self):
        with self.lock:
            for session in self.sessions.values():
                session.close()
            self.sessions.clear()

    def _expire(self):
        for ident, session in list(self.sessions.items()):
            if (not session.active and not session.server.operations.keeps_alive()
                    and time.monotonic() - session.touched > IDLE and session.server.operations.idle_seconds() > IDLE):
                del self.sessions[ident]
                session.close()

    def active(self):
        with self.lock:
            return any(s.server.operations.keeps_alive() for s in self.sessions.values())

    def listing(self):
        with self.lock:
            self._expire()
            return [{'id': ident, 'kind': 'mcp', 'client': session.client,
                     'idle': round(time.monotonic()-session.touched, 1)}
                    for ident, session in self.sessions.items()]

    def _new(self, params):
        # The stdio peer may select its immutable development app copy. It has the
        # installation token and the same local-file authority as every other client.
        meta = params.get('_meta') or {}
        options = meta.get('dev.texttocad/transport', {}) if isinstance(meta, dict) else {}
        options = options if isinstance(options, dict) else {}
        directory = options.get('appDir')
        page = AppPage(Path(directory)) if isinstance(directory, str) and directory else AppPage()
        app = ViewerApp(self.engine.server, host=self.engine.host, port=self.engine.server.port,
                         start=options.get('cwd') if isinstance(options.get('cwd'), str) else None)
        app.analytics = self.engine.analytics
        app.consent_by = "app"
        def viewer_url(model=None):
            from .browser import ViewerUnavailable
            answer = self.engine.launch({'start': app.start, 'files': [model] if model else []})
            if 'failed' in answer:
                raise ViewerUnavailable(answer['failed'])
            return answer['url']
        server = Server(page=page, tunnel=ViewerTunnel(app=app), analytics=self.engine.analytics,
                        sidebar_views=SidebarViews(self.sidebar), viewer_url=viewer_url,
                        sync_document=self.engine.server.sync, warm=self.engine.server.warm)
        result = server.handle('initialize', params, RequestContext(None, {}))
        client = params.get('clientInfo')
        client = client if isinstance(client, dict) else {}
        return Session(server, result['protocolVersion'], str(client.get('name', 'unknown'))), result

    def handle(self, request, response):
        origin = request.header('origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.netloc != request.header('host'):
                return response.send_json(403, {'error': 'cross-origin MCP request refused'})
        if request.raw_method in ('GET', 'HEAD'):
            return response.send_empty(405, [('allow', 'POST, DELETE')])
        ident = request.header('mcp-session-id')
        with self.lock:
            self._expire()
            session = self.sessions.get(ident)
            if ident and session is None:
                return response.send_json(404, {'error': 'MCP session expired; initialize again'})
            if session:
                session.active += 1
                session.touched = time.monotonic()
        try:
            if request.raw_method == 'DELETE':
                if not session:
                    return response.send_json(400, {'error': 'Mcp-Session-Id required'})
                if session.server.operations.keeps_alive():
                    return response.send_json(409, {'error': 'Wait for running operations or cancel queued work before closing this session'})
                with self.lock:
                    self.sessions.pop(ident, None)
                session.close()
                return response.send_empty(200)
            if request.raw_method != 'POST':
                return response.send_empty(405, [('allow', 'POST, DELETE')])
            if request.header('content-type').split(';')[0].strip() != 'application/json':
                return response.send_json(415, {'error': 'application/json required'})
            accept = request.header('accept')
            if 'application/json' not in accept or 'text/event-stream' not in accept:
                return response.send_json(406, {'error': 'accept application/json and text/event-stream'})
            version = request.header('mcp-protocol-version')
            if version and version not in _PROTOCOL_VERSIONS:
                return response.send_json(400, {'error': 'unsupported MCP protocol version'})
            try:
                message = json.loads(request.body())
            except (ValueError, UnicodeError):
                return self._error(response, None, PARSE_ERROR, 'invalid JSON', status=400)
            if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
                return self._error(response, None, INVALID_REQUEST, 'expected one JSON-RPC 2.0 object', status=400)
            method, request_id = message.get('method'), message.get('id')
            params = message.get('params', {})
            if not isinstance(method, str) or not isinstance(params, dict):
                return self._error(response, request_id, INVALID_PARAMS, 'method and object params required', status=400)
            if method == 'initialize':
                if session or 'id' not in message:
                    return self._error(response, request_id, INVALID_REQUEST, 'initialize requires a new session', status=400)
                try:
                    created, result = self._new(params)
                except RpcError as error:
                    return self._error(response, request_id, error.code, error.message)
                ident = secrets.token_urlsafe(32)
                with self.lock:
                    self.sessions[ident] = created
                return self._result(response, request_id, result, [('Mcp-Session-Id', ident)])
            if not session:
                return response.send_json(400, {'error': 'Mcp-Session-Id required'})
            if 'id' not in message:
                return response.send_empty(202)
            try:
                meta = params.get('_meta') if isinstance(params.get('_meta'), dict) else {}
                result = session.server.handle(method, params, RequestContext(request_id, meta))
            except RpcError as error:
                return self._error(response, request_id, error.code, error.message, data=error.data)
            except Exception:
                return self._error(response, request_id, INTERNAL_ERROR, 'internal MCP request failure')
            return self._result(response, request_id, result)
        finally:
            if session:
                with self.lock:
                    session.active -= 1
                    session.touched = time.monotonic()

    @staticmethod
    def _result(response, ident, result, headers=()):
        response.send_bytes(200, json.dumps({'jsonrpc': '2.0', 'id': ident, 'result': result}).encode('utf-8'),
                            'application/json', headers)

    @staticmethod
    def _error(response, ident, code, message, *, status=200, data=None):
        error = {'code': code, 'message': message}
        if data is not None:
            error['data'] = data
        response.send_json(status, {'jsonrpc': '2.0', 'id': ident, 'error': error})
