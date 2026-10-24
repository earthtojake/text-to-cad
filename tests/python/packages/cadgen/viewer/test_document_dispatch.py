"""Exact document routes and response headers survive the in-process HTTP adapter."""
import io
import json
import unittest
from unittest.mock import Mock

from cadgen.engine.serve import Server
from cadgen.viewer.engine_app import DocumentResponse, document_route
from cadgen.viewer.response import Request


def request(path, method='GET'):
    return Request(raw_method=method, path=path, query=[], headers={'x-cadgen-viewer': '1'}, read_body=lambda: b'')


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
                handler = DocumentResponse(request(path, method))
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
        response = Mock()
        document_route(Mock(route=route), request('/api/docs', 'HEAD'), response)
        status, body, kind, headers = response.send_bytes.call_args.args
        self.assertEqual(status, 405)
        self.assertTrue(body, 'Response suppresses the HEAD body after computing its GET length')
        self.assertEqual(dict(headers)['allow'], 'POST')
        self.assertEqual(dict(headers)['etag'], 'revision-1')
        self.assertIn('content-disposition', dict(headers))
        self.assertNotIn('access-control-allow-origin', dict(headers))
        self.assertEqual(dict(headers)['x-content-type-options'], 'nosniff')
