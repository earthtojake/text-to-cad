"""The host's stdio transport: forward JSON-RPC to this installation's engine.

Only connection metadata lives here. Tools, views, pages and document state belong
in the engine. Host capability corrections are made at this boundary.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import sys
import threading

from cadgen.viewer.engine_client import EngineClient
from .protocol import Connection, RequestContext, RpcError, claim_stdin, claim_stdout

LOG = logging.getLogger('cadgen.mcp')


def initialize_params(params):
    params = copy.deepcopy(params)
    client = params.get('clientInfo') or {}
    offered = params.setdefault('capabilities', {})
    extensions = offered.setdefault('extensions', {})
    if client.get('name') == 'codex-mcp-client':
        extensions['dev.texttocad/tabs'] = {'entrypoints': ['global', 'thread', 'file']}
    elif os.environ.get('CADGEN_MCP_PRESENTATION') in ('inline', 'text'):
        if os.environ['CADGEN_MCP_PRESENTATION'] == 'inline':
            extensions['io.modelcontextprotocol/ui'] = {'mimeTypes': ['text/html;profile=mcp-app']}
        else:
            extensions.pop('io.modelcontextprotocol/ui', None)
            extensions.pop('dev.texttocad/tabs', None)
    params.setdefault('_meta', {})['dev.texttocad/transport'] = {
        'appDir': os.environ.get('CADGEN_MCP_APP_DIR', ''), 'cwd': os.getcwd(),
    }
    return params


class Proxy:
    """One host connection's engine session. The host initializes once, but the engine's session
    can end under it (the engine restarted, or the session's idle hour passed): the shim then opens
    a new one with the host's own initialize and sends the request again, so the host never has to
    reconnect. Only a request the engine never took is sent again: one it refused for an unknown
    session, or one whose connection was refused."""

    def __init__(self, client=None):
        self.client = client or EngineClient()
        self.session = None
        self.protocol = None
        self.initialize = None  # the host's initialize, as the engine was sent it
        self.initialized = False  # whether the host said notifications/initialized
        self.lock = threading.Lock()

    def _send(self, message, session, *, fresh=False):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if session:
            headers['Mcp-Session-Id'], headers['MCP-Protocol-Version'] = session
        return self.client.call('POST', '/mcp', json.dumps(message).encode('utf-8'), headers, fresh=fresh)

    def _open(self, request_id, params):
        # The host's initialize goes only to the endpoint the engine's socket names now, never to
        # one held from an earlier call, which another process may have taken since.
        status, reply_headers, data = self._send({'jsonrpc': '2.0', 'id': request_id, 'method': 'initialize',
                                                  'params': params}, None, fresh=True)
        answer = self._answer(status, data)
        headers = {name.lower(): value for name, value in reply_headers.items()}
        session = (headers['mcp-session-id'], answer['result']['protocolVersion'])
        with self.lock:
            self.session, self.protocol = session
        return answer['result'], session

    def _reopen(self, stale):
        """A new engine session for the host's, once per ended one however many requests find it ended."""
        with self.lock:
            if self.initialize is None:
                raise RpcError(-32000, 'The engine session ended before this server was initialized.')
            current = (self.session, self.protocol) if self.session else None
            if current is not None and current != stale:
                return current  # another request opened it already
            params, initialized = self.initialize, self.initialized
        LOG.info('the engine session ended; opening a new one')
        _result, session = self._open('cadgen-reopen', params)
        if initialized:
            self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}}, session)
        return session

    @staticmethod
    def _answer(status, data):
        if status not in (200, 202):
            raise RpcError(-32000, f'Engine MCP endpoint returned HTTP {status}.')
        if status == 202:
            return {}
        answer = json.loads(data)
        if 'error' in answer:
            error = answer['error']
            raise RpcError(error['code'], error['message'], error.get('data'))
        return answer

    def _post(self, message):
        with self.lock:
            session = (self.session, self.protocol) if self.session else None
        for attempt in (1, 2):
            try:
                status, _headers, data = self._send(message, session)
            except ConnectionRefusedError:
                # No engine listens where the last one did: the request reached nothing.
                if attempt == 2 or session is None:
                    raise
                status = 404
            if status == 403 and session is not None and attempt == 1:
                # Another engine took the port: its token is not the one this shim holds.
                self.client.forget()
                status = 404
            if status != 404 or session is None or attempt == 2:
                break
            session = self._reopen(session)
        if status == 404:
            raise RpcError(-32000, 'The engine session ended and a new one could not be opened.')
        answer = self._answer(status, data)
        return answer.get('result', {}) if answer else {}

    def handle(self, method, params, context: RequestContext):
        if method == 'initialize':
            params = initialize_params(params)
            result, _session = self._open(context.request_id, params)
            with self.lock:
                self.initialize = params
            return result
        return self._post({'jsonrpc': '2.0', 'id': context.request_id, 'method': method, 'params': params})

    def notify(self, method, params):
        if method == 'notifications/initialized':
            with self.lock:
                self.initialized = True
        self._post({'jsonrpc': '2.0', 'method': method, 'params': params})

    def close(self):
        with self.lock:
            ident = self.session
        if ident:
            try:
                self.client.call('DELETE', '/mcp', headers={'Mcp-Session-Id': ident})
            except OSError:
                pass


def serve(argv=None):
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='cadgen mcp: %(message)s')
    output = claim_stdout()
    requests = claim_stdin()
    from cadgen._internal.channel import remember
    remembering = threading.Thread(target=remember, daemon=True)
    remembering.start()
    proxy = Proxy()
    connection = Connection(requests, output, proxy.handle, workers=64, notification=proxy.notify)
    try:
        connection.serve()
    finally:
        proxy.close()
        remembering.join(1)
    return 0
