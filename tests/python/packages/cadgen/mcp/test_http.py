"""Real stdio and HTTP peers share an engine, with isolated MCP view state."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.engine.client import request
from cadgen.mcp.protocol import RequestContext, RpcError
from cadgen.mcp.shim import Proxy
from cadgen.viewer.engine_client import EngineClient
from tests.python.support import engine_daemon

INIT = {'protocolVersion': '2025-11-25', 'clientInfo': {'name': 'codex-mcp-client'}, 'capabilities': {}}


class HttpSessionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='mcp-http-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.env = engine_daemon.watched({**os.environ, 'CADGEN_ENGINE_DIR': str(cls.root / 'engine'),
                   'CADGEN_STATE_DIR': str(cls.root / 'state'), 'CADGEN_ENGINE_MESH': 'inline'}, cls.addClassCleanup)
        changed = patch.dict(os.environ, cls.env)
        changed.start()
        cls.addClassCleanup(changed.stop)
        from cadgen.engine.api import stop
        cls.addClassCleanup(stop)
        cls.endpoint = EngineClient().connect()
        cls.page = cls.root / 'page'
        cls.page.mkdir()
        (cls.page / 'index.html').write_text('<!doctype html><title>test app</title>', encoding='utf-8')
        cls.model = cls.root / 'part.stl'
        cls.model.write_bytes(b'solid part\nendsolid part\n')

    def proxy(self):
        proxy = Proxy()
        self.addCleanup(proxy.close)
        self.call(proxy, 'initialize', INIT)
        return proxy

    @staticmethod
    def call(proxy, method, params=None):
        return proxy.handle(method, params or {}, RequestContext(1, {}))

    def tool(self, proxy, name, arguments=None):
        return self.call(proxy, 'tools/call', {'name': name, 'arguments': arguments or {}})

    def test_two_sessions_share_engine_and_router_but_not_conversation_views(self):
        first, second = self.proxy(), self.proxy()
        self.assertNotEqual(first.session, second.session)
        # Agent access works over the real transport before any view has opened.
        status = self.tool(first, 'cad_http', {'method': 'GET', 'url': '/__cad/analytics'})
        self.assertEqual(status['structuredContent']['status'], 200)
        self.assertIn('sharing', json.loads(status['content'][0]['text']))
        refused = self.tool(first, 'cad_http', {'method': 'POST', 'url': '/__cad/analytics',
                            'body': base64.b64encode(b'{"share":true}').decode()})
        self.assertTrue(refused['isError'])
        self.assertEqual(refused['structuredContent']['status'], 403)
        info = request({'op': 'status'})
        sessions = {item['id'] for item in info['sessions'] if item['kind'] == 'mcp'}
        self.assertTrue({first.session, second.session} <= sessions)
        token = self.tool(first, 'cad_tab')['_meta']['dev.texttocad/httpToken']
        self.tool(first, 'cad_sync', {'view': 'one', 'surface': 'agent', 'model': str(self.model),
                  'state': {'selection': ['part#f1']}, 'focused': True, 'app': token})
        self.assertEqual(self.tool(first, 'cad_view')['structuredContent']['views'][0]['selection'], ['part#f1'])
        self.assertEqual(self.tool(second, 'cad_view')['structuredContent']['views'], [])
        reply = self.tool(first, 'cad_http', {'method': 'GET', 'url': '/__cad/server', 'headers': {'x-cadgen-app': token}})['structuredContent']
        self.assertEqual(reply['status'], 200)
        self.assertEqual(json.loads(base64.b64decode(reply['body']))['pid'], info['pid'])
        first.close()
        self.assertEqual(self.call(second, 'ping'), {})
        self.assertEqual(request({'op': 'status'})['pid'], info['pid'])
        self.assertFalse((self.root / 'state' / 'sidebar-views').exists())

    def test_inspect_export_tools_run_without_a_view(self):
        proxy = self.proxy()
        def finished(name, arguments):
            status = self.tool(proxy, name, arguments)['structuredContent']
            for _ in range(30):
                if status['state'] in ('succeeded', 'failed', 'cancelled', 'rejected'):
                    break
                status = self.tool(proxy, name, {'action': 'status', 'operationId': status['id'],
                    'epoch': status['epoch'], 'afterSequence': status['sequence'], 'waitMs': 25000})['structuredContent']
            return status

        def operation(name, arguments):
            status = finished(name, arguments)
            self.assertEqual(status['state'], 'succeeded', status)
            return status['result']
        # A model is built by its script's call, never by a tool: a bare model, held in memory alone.
        folder = (self.root / 'tool-models').resolve()
        folder.mkdir()
        script = folder / 'http_part.py'
        script.write_text('from build123d import Box\nfrom cadgen import model\n\n\n@model\n'
                          'def http_part():\n    return Box(2, 3, 4)\n', encoding='utf-8')
        from cadgen.engine.api import build_script
        built = build_script(script, ['http_part'])
        self.assertTrue(built.ok)
        ident = built.models[0]['id']  # what `python http_part.py` prints, `id:`
        self.assertNotIn('cad_build', {tool['name'] for tool in self.call(proxy, 'tools/list')['tools']})
        facts = operation('cad_inspect', {'requestId': 'inspect-request-01', 'source': f'{ident}#face 1'})
        self.assertEqual(facts['inspection']['kind'], 'face')
        target = (self.root / 'tool-export.step').resolve()
        written = operation('cad_export', {'requestId': 'export-request-001', 'source': ident, 'destinations': [str(target)]})
        # A script is never a source, whatever names it: each tool refuses it as it refuses any
        # file that is no document, and nothing is built or written.
        for at, named in enumerate((str(script), f'{script}::http_part')):
            for name, arguments in (('cad_export', {'destinations': [str(self.root / 'refused.step')]}),
                                    ('cad_snapshot', {'output': str(self.root / 'refused.png')}),
                                    ('cad_inspect', {})):
                with self.subTest(tool=name, source=named):
                    status = finished(name, {'requestId': f'refused-{name}-{at:02d}-request', 'source': named, **arguments})
                    self.assertIn(status['state'], ('failed', 'rejected'), status)
                    self.assertRegex(status.get('error', ''), 'is no document|is neither a document')
        self.assertFalse((self.root / 'refused.step').exists() or (self.root / 'refused.png').exists())
        self.assertEqual([path.name for path in folder.iterdir()], ['http_part.py'])
        self.assertEqual(written['files'][0]['bytes'], target.stat().st_size)
        self.assertGreater(target.stat().st_size, 0)

    def test_http_transport_validation_and_session_lifecycle(self):
        client = EngineClient()
        def post(message, **headers):
            return client.call('POST', '/mcp', json.dumps(message).encode('utf-8'),
                               {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', **headers})
        self.assertEqual(client.call('GET', '/mcp')[0], 405)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})[0], 400)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, **{'Mcp-Session-Id': 'unknown'})[0], 404)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': INIT}, Origin='https://evil.example')[0], 403)
        self.assertEqual(post([])[0], 400)
        self.assertEqual(post({}, Accept='application/json')[0], 406)
        proxy = self.proxy()
        headers = {'Mcp-Session-Id': proxy.session}
        self.assertEqual(post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, **headers)[0], 202)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}, **headers, **{'MCP-Protocol-Version': 'bogus'})[0], 400)
        with self.assertRaises(RpcError) as failure:
            self.call(proxy, 'does/not/exist')
        self.assertEqual(failure.exception.code, -32601)
        self.assertEqual(client.call('DELETE', '/mcp', headers=headers)[0], 200)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}, **headers)[0], 404)

    def test_shim_opens_a_new_session_when_the_engine_session_ends(self):
        # A host initializes once: an expired session or a restarted engine must not leave the
        # server answering every later call with an error until the host reconnects it.
        proxy = self.proxy()
        proxy.notify('notifications/initialized', {})
        first = proxy.session
        self.assertEqual(EngineClient().call('DELETE', '/mcp', headers={'Mcp-Session-Id': first})[0], 200)
        status = self.tool(proxy, 'cad_http', {'method': 'GET', 'url': '/__cad/analytics'})
        self.assertEqual(status['structuredContent']['status'], 200)
        second = proxy.session
        self.assertNotEqual(second, first)
        from cadgen.engine.api import stop
        pid = request({'op': 'status'})['pid']
        self.assertTrue(stop())
        self.assertEqual(self.call(proxy, 'ping'), {})
        self.assertNotEqual(proxy.session, second)
        self.assertNotEqual(request({'op': 'status'})['pid'], pid)
        self.assertIn('cad_open', [tool['name'] for tool in self.call(proxy, 'tools/list')['tools']])

    def test_stdio_shim_serves_resource_and_exits_without_stopping_engine(self):
        process = subprocess.Popen([sys.executable, '-m', 'cadgen.cli', 'mcp'],
                    env={**self.env, 'CADGEN_MCP_APP_DIR': str(self.page)},
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def close():
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=20)
        self.addCleanup(close)
        def rpc(ident, method, params):
            process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})+'\n')
            process.stdin.flush()
            result = json.loads(process.stdout.readline())
            self.assertEqual(result['id'], ident)
            self.assertNotIn('error', result)
            return result['result']
        self.assertEqual(rpc(1, 'initialize', INIT)['protocolVersion'], '2025-11-25')
        resources = rpc(2, 'resources/list', {})['resources']
        document = rpc(3, 'resources/read', {'uri': resources[0]['uri']})['contents'][0]['text']
        self.assertIn('<title>test app</title>', document)
        tools = rpc(4, 'tools/list', {})['tools']
        self.assertIn('cad_open', [tool['name'] for tool in tools])
        process.stdin.close()
        process.stdin = None
        self.assertEqual(process.wait(timeout=20), 0)
        self.assertTrue(request({'op': 'status'})['ok'])

    def test_shim_imports_no_tool_server_or_viewer_application(self):
        code = "import sys; from cadgen.mcp.shim import Proxy; assert not {'cadgen.mcp.server', 'cadgen.mcp.ui', 'cadgen.viewer.http_app', 'OCP', 'build123d'} & sys.modules.keys()"
        done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == '__main__':
    unittest.main()
