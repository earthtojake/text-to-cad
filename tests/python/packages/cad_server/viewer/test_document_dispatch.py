"""Exact document reads and response headers survive the in-process adapter: the engine's own
vocabulary (``/api/doc/<id>...``, ``cad/engine/serve.py``'s), which ``/api/v1``'s routes read."""
import io
import json
import unittest
from unittest.mock import Mock

from cad.engine.serve import Server
from cad_server.viewer.engine_app import DocumentResponse, document_read
from cad_server.viewer.response import Request


def request(path, method='GET', query=()):
    return Request(raw_method=method, path=path, query=list(query), headers={'x-cadgen-viewer': '1'}, read_body=lambda: b'')


class DocumentDispatchTest(unittest.TestCase):
    def test_exact_read_routes_and_methods(self):
        server = Server.__new__(Server)
        server.three = None
        server.poses, server.served, server.model_loaders = {}, {}, {}
        server.listing = lambda: []
        for path, method, expected in (('/api/docs', 'POST', 405), ('/api/docs/extra', 'GET', 404),
                                        ('/api/docs/', 'GET', 404), ('/api//docs', 'GET', 404),
                                        ('/api/docs', 'GET', 200), ('/api/doc/absent/mesh', 'GET', 405)):
            with self.subTest(path=path, method=method):
                handler = DocumentResponse(request(path, method), path)
                server.route(handler, method)
                self.assertEqual(handler.status, expected)
                if expected == 405:
                    self.assertIn('allow', handler.response_headers)
                json.loads(handler.wfile.getvalue())

    def test_adapter_preserves_headers_and_head_representation_length(self):
        def route(handler, method):
            handler.send_response(405)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Allow', 'POST')
            handler.send_header('ETag', 'revision-1')
            handler.send_header('Content-Disposition', 'attachment; filename="model.json"')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.wfile.write(b'{"error":"Method not allowed"}')
        status, kind, headers, body = document_read(Mock(route=route), request('/api/v1/look', 'HEAD'), '/api/docs')
        self.assertEqual((status, kind), (405, 'application/json'))
        self.assertTrue(body, 'Response suppresses the HEAD body after computing its GET length')
        headers = list(headers.items())
        self.assertEqual(dict(headers)['allow'], 'POST')
        self.assertEqual(dict(headers)['etag'], 'revision-1')
        self.assertIn('content-disposition', dict(headers))
        self.assertNotIn('access-control-allow-origin', dict(headers))
        self.assertEqual(dict(headers)['x-content-type-options'], 'nosniff')


class BrowserPageTest(unittest.TestCase):
    """A host with no app opens a document's page once (``cad_server.mcp``): the engine knows a browser
    page shows a document by that page's version reads, which an MCP view's tunnel does not make."""

    def test_only_the_browser_pages_version_read_says_a_page_shows_the_document(self):
        import shutil
        import tempfile
        from pathlib import Path

        folder = Path(tempfile.mkdtemp(prefix='browser-page-'))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        server = Server(mesh_mode='inline')
        self.addCleanup(server.stop)
        path = folder / 'part.xbf'
        ident = server.put(path, {'version': 'one', 'prototypes': [], 'name': 'part'}, {})
        version = request(f'/api/v1/documents/{ident}/version')
        route, query = f'/api/doc/{ident}/version', [('after', ''), ('wait', '0')]
        document_read(server, version, route, query, page=False)  # an MCP view's, through its tunnel
        server.sync(ident)  # and its heartbeat
        self.assertFalse(server.in_page(str(path)))
        document_read(server, version, route, query, page=True)
        self.assertTrue(server.in_page(str(path)))
        self.assertTrue(server.in_page(ident))
        other = server.put(folder / 'other.xbf', {'version': 'one', 'prototypes': [], 'name': 'other'}, {})
        server.page_opening(other)  # a browser opened on it, its page still loading
        self.assertTrue(server.in_page(other))
